from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal

import httpx

from backend.config.settings import settings
from backend.tools.logger import logger


class ToolboxError(Exception):
    """Erro base para falhas de comunicação com a Acessilia Toolbox."""


class ToolboxProviderUnavailable(ToolboxError):
    """Provedor da Toolbox está offline ou não respondeu."""


class ToolboxTimeout(ToolboxError):
    """A requisição excedeu o timeout configurado."""


class ToolboxUnsupportedMediaType(ToolboxError):
    """Tipo de mídia não suportado pela capacidade solicitada."""


class ToolboxArtifactNotFound(ToolboxError):
    """Artefato requisitado não foi encontrado na Toolbox."""


class ToolboxContractViolation(ToolboxError):
    """Resposta da Toolbox violou o contrato esperado."""


class ToolboxCapabilityError(ToolboxError):
    """Capacidade inválida ou não disponível na Toolbox."""


class ToolboxClient:
    """Cliente HTTP para a Acessilia Toolbox (REST API na porta 8002).

    Encapsula os endpoints documentados em:
    https://github.com/A11yDevs/acessilia-toolbox/blob/main/docs/api.md
    """

    def __init__(
        self,
        base_url: str | None = None,
        provider: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.toolbox_base_url).rstrip("/")
        self.provider = provider or settings.toolbox_provider
        self.timeout_seconds = timeout_seconds or settings.toolbox_timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout_seconds),
        )

    async def health(self) -> dict[str, Any]:
        """GET /v1/health — verifica se a Toolbox está operacional."""
        return await self._get("/v1/health")

    async def capabilities(self) -> list[dict[str, Any]]:
        """GET /v1/capabilities — lista capacidades disponíveis."""
        data = await self._get("/v1/capabilities")
        if isinstance(data, list):
            return data
        return data.get("capabilities", [])

    async def upload_artifact(self, file_path: Path) -> str:
        """POST /v1/artifacts — faz upload de um arquivo e retorna o artifact_id."""
        url = f"{self.base_url}/v1/artifacts"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                with open(file_path, "rb") as f:
                    response = await client.post(
                        url,
                        files={"file": (file_path.name, f, _media_type(file_path))},
                    )
                _raise_for_error(response, "artifact.store")
                data = response.json()
                artifact_id = data.get("artifact_id") or data.get("id")
                if not artifact_id:
                    raise ToolboxContractViolation(
                        "Resposta de artifact.store sem artifact_id"
                    )
                logger.info(
                    "Toolbox: artifact {} armazenado ({})",
                    artifact_id,
                    file_path.name,
                )
                return str(artifact_id)
        except httpx.TimeoutException as e:
            raise ToolboxTimeout(
                f"Timeout ao fazer upload para Toolbox: {e}"
            ) from e
        except httpx.RequestError as e:
            raise ToolboxProviderUnavailable(
                f"Toolbox indisponível em {self.base_url}: {e}"
            ) from e

    async def retrieve_artifact(self, artifact_id: str, output_path: Path) -> None:
        """GET /v1/artifacts/{id} — baixa um artefato da Toolbox."""
        url = f"{self.base_url}/v1/artifacts/{artifact_id}"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                response = await client.get(url)
            _raise_for_error(response, "artifact.retrieve")
            output_path.write_bytes(response.content)
            logger.info(
                "Toolbox: artifact {} recuperado -> {}",
                artifact_id,
                output_path,
            )
        except httpx.TimeoutException as e:
            raise ToolboxTimeout(
                f"Timeout ao recuperar artifact {artifact_id}: {e}"
            ) from e
        except httpx.RequestError as e:
            raise ToolboxProviderUnavailable(
                f"Toolbox indisponível em {self.base_url}: {e}"
            ) from e

    async def providers(self) -> list[dict[str, Any]]:
        """GET /v1/providers — lista provedores registrados."""
        data = await self._get("/v1/providers")
        if isinstance(data, list):
            return data
        return data.get("providers", [])

    async def provider_health(self, provider_id: str) -> dict[str, Any]:
        """GET /v1/providers/{id}/health — saúde técnica de um provedor.

        Nunca lança: indisponibilidade vira ``{"healthy": False, "detail": ...}``
        para que o planejador trate como fato (``provider-available``).
        """
        try:
            data = await self._get(f"/v1/providers/{provider_id}/health")
        except ToolboxError as e:
            return {"provider": provider_id, "healthy": False, "detail": str(e)}
        if isinstance(data, dict):
            data.setdefault("provider", provider_id)
            return data
        return {"provider": provider_id, "healthy": bool(data)}

    async def planning_domain(self) -> str:
        """GET /v1/planning/domain — fragmento PDDL publicado pela Toolbox."""
        return await self._get_text("/v1/planning/domain")

    async def planning_capability(self, capability_id: str) -> str:
        """GET /v1/planning/capabilities/{id} — ação PDDL de uma capability."""
        return await self._get_text(f"/v1/planning/capabilities/{capability_id}")

    async def execute(
        self,
        capability_id: str,
        *,
        file_path: Path | None = None,
        artifact_id: str | None = None,
        provider: str | None = None,
        parameters: dict[str, Any] | None = None,
        use_remote_cache: bool | None = None,
    ) -> dict[str, Any]:
        """POST /v1/capabilities/{capability_id}:execute (qualquer capability).

        Aceita upload direto (``file_path``) ou referência a artifact já
        armazenado (``artifact_id``). ``parameters`` são repassados ao provedor
        (form fields no upload; JSON quando por artifact). Retorna o JSON
        completo da resposta, cujo ``status`` deve ser ``succeeded``.
        """
        if file_path is None and artifact_id is None:
            raise ValueError("Forneça file_path ou artifact_id")

        use_cache = (
            use_remote_cache
            if use_remote_cache is not None
            else settings.toolbox_use_remote_cache
        )
        provider_id = provider or self.provider
        url = f"{self.base_url}/v1/capabilities/{capability_id}:execute"
        payload: dict[str, Any] = {"provider": provider_id, **(parameters or {})}
        if not use_cache:
            payload["no_cache"] = True

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_seconds)) as client:
                if artifact_id:
                    response = await client.post(url, json={"artifact_id": artifact_id, **payload})
                else:
                    assert file_path is not None
                    with open(file_path, "rb") as f:
                        files = {"file": (file_path.name, f, _media_type(file_path))}
                        response = await client.post(url, files=files, data=payload)

            _raise_for_error(response, capability_id)
            result = response.json()

            if result.get("status") != "succeeded":
                raise ToolboxContractViolation(
                    f"Extração/execução de {capability_id} falhou na Toolbox: "
                    f"status={result.get('status')}"
                )

            logger.info(
                "Toolbox: {} concluída ({} ms, provider={})",
                capability_id,
                result.get("provenance", {}).get("duration_ms", "?"),
                result.get("provider", provider_id),
            )
            return result

        except httpx.TimeoutException as e:
            raise ToolboxTimeout(
                f"Timeout em {capability_id} via Toolbox: {e}"
            ) from e
        except httpx.RequestError as e:
            raise ToolboxProviderUnavailable(
                f"Toolbox indisponível em {self.base_url}: {e}"
            ) from e

    async def extract_structure(
        self,
        file_path: Path | None = None,
        artifact_id: str | None = None,
        *,
        language: str = "pt-BR",
        use_remote_cache: bool | None = None,
    ) -> dict[str, Any]:
        """POST /v1/capabilities/document.structure.extract:execute.

        Aceita upload direto (file_path) ou referência a artifact já armazenado
        (artifact_id). Retorna o JSON completo da resposta.
        """
        return await self.execute(
            "document.structure.extract",
            file_path=file_path,
            artifact_id=artifact_id,
            parameters={"language": language},
            use_remote_cache=use_remote_cache,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get_text(self, path: str) -> str:
        try:
            response = await self._client.get(path)
            _raise_for_error(response, path)
            return response.text
        except httpx.TimeoutException as e:
            raise ToolboxTimeout(f"Timeout em GET {path}: {e}") from e
        except httpx.RequestError as e:
            raise ToolboxProviderUnavailable(
                f"Toolbox indisponível em {self.base_url}: {e}"
            ) from e

    async def _get(self, path: str) -> Any:
        try:
            response = await self._client.get(path)
            _raise_for_error(response, path)
            return response.json()
        except httpx.TimeoutException as e:
            raise ToolboxTimeout(f"Timeout em GET {path}: {e}") from e
        except httpx.RequestError as e:
            raise ToolboxProviderUnavailable(
                f"Toolbox indisponível em {self.base_url}: {e}"
            ) from e


def _media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    mapping = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".bmp": "image/bmp",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".html": "text/html",
        ".txt": "text/plain",
    }
    return mapping.get(suffix, "application/octet-stream")


def _raise_for_error(response: httpx.Response, context: str) -> None:
    """Converte códigos HTTP em exceções Toolbox específicas."""
    if response.is_success:
        return

    status = response.status_code
    try:
        body = response.json()
        detail = body.get("detail", body.get("message", ""))
    except Exception:
        detail = response.text[:500]

    if status == 503:
        raise ToolboxProviderUnavailable(
            f"Provedor indisponível ({context}): {detail}"
        )
    if status == 504:
        raise ToolboxTimeout(
            f"Timeout do provedor ({context}): {detail}"
        )
    if status == 415:
        raise ToolboxUnsupportedMediaType(
            f"Tipo de mídia não suportado ({context}): {detail}"
        )
    if status == 404:
        raise ToolboxArtifactNotFound(
            f"Artefato não encontrado ({context}): {detail}"
        )
    if status == 422:
        raise ToolboxContractViolation(
            f"Requisição inválida ({context}): {detail}"
        )
    if status == 400:
        raise ToolboxCapabilityError(
            f"Capacidade inválida ({context}): {detail}"
        )

    raise ToolboxError(
        f"Erro HTTP {status} na Toolbox ({context}): {detail}"
    )