"""Registro determinístico: ação PDDL -> capability da Toolbox (+ provedor).

Princípio (docs/drdocbench/PLANO.md §2.2): o plano nunca é interpretado por LLM.
Cada ação do domínio mapeia sem ambiguidade para ``capability@provider`` e é
executada via :class:`ToolboxClient`. Falhas viram observações estruturadas para
o replanejamento (nunca exceções para o chamador do pipeline).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.tools.logger import logger
from backend.tools.toolbox_client import (
    ToolboxClient,
    ToolboxContractViolation,
    ToolboxError,
    ToolboxProviderUnavailable,
    ToolboxTimeout,
)


@dataclass(frozen=True)
class ActionBinding:
    """Vínculo entre uma ação PDDL e uma capability da Toolbox."""

    action: str
    capability: str
    provider: str
    cost: int = 1
    parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def method(self) -> str:
        """Nome do método no sentido do domínio v2.2 (``capability@provider``)."""
        return f"{self.capability}@{self.provider}"


@dataclass
class ActionOutcome:
    """Resultado observável de uma ação: candidato produzido, não validado."""

    binding: ActionBinding
    succeeded: bool
    result: dict[str, Any] | None = None
    failure_kind: str | None = None  # unavailable | timeout | contract | error
    message: str | None = None
    duration_ms: int | None = None

    def facts(self, block_id: str) -> list[str]:
        """Predicados PDDL derivados da observação (sem decidir plano)."""
        prov = self.binding.provider
        if self.succeeded:
            return [f"(candidate {block_id} {prov})", f"(tried {block_id} {prov})"]
        facts = [f"(tried {block_id} {prov})", f"(rejected {block_id} {prov})"]
        if self.failure_kind == "unavailable":
            facts.append(f"(not (provider-available {prov}))")
        return facts


class ActionRegistry:
    """Tabela de despacho ação -> bindings (vários provedores por ação)."""

    def __init__(self, bindings: Iterable[ActionBinding] = ()) -> None:
        self._by_action: dict[str, list[ActionBinding]] = {}
        for b in bindings:
            self.register(b)

    def register(self, binding: ActionBinding) -> None:
        if not binding.action or not binding.capability or not binding.provider:
            raise ValueError("ActionBinding exige action, capability e provider")
        self._by_action.setdefault(binding.action, []).append(binding)

    def actions(self) -> list[str]:
        return sorted(self._by_action)

    def bindings(self, action: str) -> list[ActionBinding]:
        return sorted(self._by_action.get(action, []), key=lambda b: b.cost)

    def resolve(self, action: str, provider: str | None = None) -> ActionBinding | None:
        candidates = self.bindings(action)
        if not candidates:
            return None
        if provider is None:
            return candidates[0]
        return next((b for b in candidates if b.provider == provider), None)

    def providers(self) -> set[str]:
        return {b.provider for bs in self._by_action.values() for b in bs}

    def action_costs_pddl(self) -> dict[str, int]:
        """``method -> custo`` para o Problem Builder (``:action-costs``)."""
        return {b.method: b.cost for bs in self._by_action.values() for b in bs}


class ToolboxActionExecutor:
    """Executa bindings na Toolbox e observa disponibilidade de provedores."""

    def __init__(self, client: ToolboxClient, registry: ActionRegistry) -> None:
        self.client = client
        self.registry = registry

    async def execute(
        self,
        binding: ActionBinding,
        *,
        file_path: Path | None = None,
        artifact_id: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> ActionOutcome:
        params = {**binding.parameters, **(parameters or {})}
        try:
            result = await self.client.execute(
                binding.capability,
                file_path=file_path,
                artifact_id=artifact_id,
                provider=binding.provider,
                parameters=params,
            )
        except ToolboxProviderUnavailable as e:
            return self._failure(binding, "unavailable", e)
        except ToolboxTimeout as e:
            return self._failure(binding, "timeout", e)
        except ToolboxContractViolation as e:
            return self._failure(binding, "contract", e)
        except ToolboxError as e:
            return self._failure(binding, "error", e)
        except Exception as e:  # noqa: BLE001 — nunca propagar para o pipeline
            return self._failure(binding, "error", e)

        duration = (result.get("provenance") or {}).get("duration_ms")
        return ActionOutcome(
            binding=binding,
            succeeded=True,
            result=result,
            duration_ms=int(duration) if isinstance(duration, (int, float)) else None,
        )

    def execute_sync(self, binding: ActionBinding, **kwargs: Any) -> ActionOutcome:
        return asyncio.run(self.execute(binding, **kwargs))

    async def provider_availability(self) -> dict[str, bool]:
        """Saúde técnica de cada provedor referenciado no registro."""
        result: dict[str, bool] = {}
        for provider in sorted(self.registry.providers()):
            health = await self.client.provider_health(provider)
            result[provider] = bool(health.get("healthy", False))
        return result

    async def availability_facts(self) -> list[str]:
        return [
            f"(provider-available {p})" if ok else f"(not (provider-available {p}))"
            for p, ok in (await self.provider_availability()).items()
        ]

    @staticmethod
    def _failure(binding: ActionBinding, kind: str, error: Exception) -> ActionOutcome:
        logger.warning(
            "Toolbox: ação {} via {} falhou ({}): {}",
            binding.action,
            binding.method,
            kind,
            error,
        )
        return ActionOutcome(
            binding=binding,
            succeeded=False,
            failure_kind=kind,
            message=str(error),
        )


def default_registry() -> ActionRegistry:
    """Bindings iniciais (custos uniformes; substituídos pela matriz de competência)."""
    return ActionRegistry(
        [
            ActionBinding("extract-structure", "document.structure.extract", "docling", cost=1),
            ActionBinding("extract-structure", "document.structure.extract", "mineru", cost=3),
            ActionBinding("extract-structure", "document.structure.extract", "ppstructure", cost=3),
            ActionBinding("detect-layout", "document.layout.detect", "surya", cost=1),
            ActionBinding("order-blocks", "document.reading_order", "surya", cost=1),
            ActionBinding("ocr-text", "document.ocr", "rapidocr", cost=1),
            ActionBinding("ocr-text", "document.ocr", "ppocr", cost=2),
            ActionBinding("parse-table", "table.recognize", "mineru", cost=3),
            ActionBinding("parse-table", "table.recognize", "docling", cost=1),
            ActionBinding("parse-formula", "formula.recognize", "unimernet", cost=2),
            ActionBinding("parse-formula", "formula.recognize", "codeformula", cost=1),
            ActionBinding("parse-chemistry", "chemistry.recognize", "molscribe", cost=3),
            ActionBinding("describe-figure", "vision.describe", "qwen-vl", cost=10),
            ActionBinding("critique-block", "vision.critique", "qwen-vl", cost=20),
            ActionBinding("render-page", "document.render", "pandoc", cost=2),
        ]
    )
