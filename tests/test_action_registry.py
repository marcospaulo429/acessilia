"""Testes do registro de ações (ação PDDL -> capability@provider) e do executor Toolbox."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from backend.core.execution.action_registry import (
    ActionBinding,
    ActionRegistry,
    ToolboxActionExecutor,
    default_registry,
)
from backend.tools.toolbox_client import ToolboxClient

BASE = "http://localhost:8002"


@pytest.fixture
def client() -> ToolboxClient:
    return ToolboxClient(base_url=BASE, provider="docling", timeout_seconds=5)


@pytest.fixture
def registry() -> ActionRegistry:
    return ActionRegistry(
        [
            ActionBinding("parse-table", "table.recognize", "mineru", cost=3),
            ActionBinding("parse-table", "table.recognize", "docling", cost=1),
            ActionBinding("parse-formula", "formula.recognize", "unimernet", cost=2),
        ]
    )


@pytest.fixture
def image(tmp_path: Path) -> Path:
    p = tmp_path / "page_1.jpg"
    p.write_bytes(b"\xff\xd8\xff\xd9")
    return p


def test_registry_resolves_cheapest_and_by_provider(registry: ActionRegistry) -> None:
    assert registry.actions() == ["parse-formula", "parse-table"]
    assert registry.resolve("parse-table").provider == "docling"
    assert registry.resolve("parse-table", "mineru").cost == 3
    assert registry.resolve("parse-table", "surya") is None
    assert registry.resolve("unknown") is None
    assert registry.providers() == {"mineru", "docling", "unimernet"}
    assert registry.action_costs_pddl()["table.recognize@mineru"] == 3
    assert registry.resolve("parse-formula").method == "formula.recognize@unimernet"


def test_registry_rejects_incomplete_binding() -> None:
    with pytest.raises(ValueError):
        ActionRegistry([ActionBinding("", "x", "y")])


def test_default_registry_covers_core_actions() -> None:
    reg = default_registry()
    for action in ("extract-structure", "parse-table", "parse-formula", "describe-figure", "critique-block"):
        assert reg.resolve(action) is not None


@pytest.mark.asyncio
async def test_execute_success_produces_candidate_facts(respx_mock, client, registry, image) -> None:
    route = respx_mock.post(f"{BASE}/v1/capabilities/table.recognize:execute")
    route.return_value = httpx.Response(
        200,
        json={
            "status": "succeeded",
            "capability": "table.recognize",
            "provider": "mineru",
            "result": {"html": "<table></table>"},
            "provenance": {"duration_ms": 120},
        },
    )
    executor = ToolboxActionExecutor(client, registry)
    binding = registry.resolve("parse-table", "mineru")

    outcome = await executor.execute(binding, file_path=image, parameters={"language": "en"})

    assert outcome.succeeded
    assert outcome.duration_ms == 120
    assert outcome.result["result"]["html"] == "<table></table>"
    assert outcome.facts("b7") == ["(candidate b7 mineru)", "(tried b7 mineru)"]
    sent = route.calls.last.request
    assert b'name="provider"\r\n\r\nmineru' in sent.content
    assert b'name="language"\r\n\r\nen' in sent.content


@pytest.mark.asyncio
async def test_execute_by_artifact_sends_json(respx_mock, client, registry) -> None:
    route = respx_mock.post(f"{BASE}/v1/capabilities/formula.recognize:execute")
    route.return_value = httpx.Response(200, json={"status": "succeeded", "provider": "unimernet"})
    executor = ToolboxActionExecutor(client, registry)

    outcome = await executor.execute(registry.resolve("parse-formula"), artifact_id="sha256:abc")

    assert outcome.succeeded
    body = route.calls.last.request.content
    assert b'"artifact_id": "sha256:abc"' in body
    assert b'"provider": "unimernet"' in body


@pytest.mark.asyncio
async def test_execute_unavailable_is_observed_not_raised(respx_mock, client, registry, image) -> None:
    respx_mock.post(f"{BASE}/v1/capabilities/table.recognize:execute").return_value = httpx.Response(
        503, json={"detail": "mineru offline"}
    )
    executor = ToolboxActionExecutor(client, registry)

    outcome = await executor.execute(registry.resolve("parse-table", "mineru"), file_path=image)

    assert not outcome.succeeded
    assert outcome.failure_kind == "unavailable"
    assert "mineru offline" in (outcome.message or "")
    assert outcome.facts("b1") == [
        "(tried b1 mineru)",
        "(rejected b1 mineru)",
        "(not (provider-available mineru))",
    ]


@pytest.mark.asyncio
async def test_execute_failed_status_is_contract_failure(respx_mock, client, registry, image) -> None:
    respx_mock.post(f"{BASE}/v1/capabilities/table.recognize:execute").return_value = httpx.Response(
        200, json={"status": "failed"}
    )
    executor = ToolboxActionExecutor(client, registry)

    outcome = await executor.execute(registry.resolve("parse-table"), file_path=image)

    assert outcome.failure_kind == "contract"
    assert outcome.facts("b1")[:2] == ["(tried b1 docling)", "(rejected b1 docling)"]


@pytest.mark.asyncio
async def test_execute_timeout(respx_mock, client, registry, image) -> None:
    respx_mock.post(f"{BASE}/v1/capabilities/table.recognize:execute").side_effect = httpx.ReadTimeout("slow")
    executor = ToolboxActionExecutor(client, registry)

    outcome = await executor.execute(registry.resolve("parse-table"), file_path=image)

    assert outcome.failure_kind == "timeout"


@pytest.mark.asyncio
async def test_provider_availability_facts(respx_mock, client, registry) -> None:
    respx_mock.get(f"{BASE}/v1/providers/docling/health").return_value = httpx.Response(
        200, json={"provider": "docling", "healthy": True}
    )
    respx_mock.get(f"{BASE}/v1/providers/mineru/health").return_value = httpx.Response(
        200, json={"provider": "mineru", "healthy": False, "detail": "down"}
    )
    respx_mock.get(f"{BASE}/v1/providers/unimernet/health").return_value = httpx.Response(404)
    executor = ToolboxActionExecutor(client, registry)

    facts = await executor.availability_facts()

    assert facts == [
        "(provider-available docling)",
        "(not (provider-available mineru))",
        "(not (provider-available unimernet))",
    ]


@pytest.mark.asyncio
async def test_planning_endpoints_return_text(respx_mock, client) -> None:
    respx_mock.get(f"{BASE}/v1/planning/domain").return_value = httpx.Response(200, text="(define (domain x))")
    respx_mock.get(f"{BASE}/v1/planning/capabilities/table.recognize").return_value = httpx.Response(
        200, text="(:action parse-table)"
    )
    assert (await client.planning_domain()).startswith("(define")
    assert (await client.planning_capability("table.recognize")).startswith("(:action")
