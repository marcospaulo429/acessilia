from __future__ import annotations

from importlib.util import find_spec

import pytest

from backend.core.execution.executor import ExecutorAgent, MethodRegistry
from backend.core.execution.models import MethodResult
from backend.core.manifest.models import Obligation
from tests.test_pddl_planning import make_manifest

pytestmark = pytest.mark.skipif(
    find_spec("agno") is None, reason="Agno não instalado"
)


def _ok(_manifest, _obligation) -> MethodResult:
    return MethodResult(success=True, validated=True)


def _fail(_manifest, _obligation) -> MethodResult:
    return MethodResult(success=False, validated=False, message="falha controlada")


def _orchestrator(registry: MethodRegistry, **kwargs):
    from backend.agents.pddl_orchestrator import PddlAccessibilityOrchestrator
    from backend.core.planning.domain_bundle import DomainBundle

    orchestrator = PddlAccessibilityOrchestrator(
        extractor_backend="pymupdf",
        execute_live=True,
        **kwargs,
    )
    orchestrator.executor = ExecutorAgent(registry, domain=DomainBundle.load())
    return orchestrator


def test_replanning_loop_recovers_with_alternative_method():
    manifest = make_manifest()
    registry = MethodRegistry()
    registry.register("docling", _ok)
    registry.register("vision", _fail)
    registry.register("human-review", _ok)

    orchestrator = _orchestrator(registry)
    (
        updated,
        plan,
        _comparison,
        report,
        stats,
    ) = orchestrator._execute_with_replanning(manifest)

    assert stats["failure"] is None
    assert report.status == "completed"
    assert stats["replans"] == 1
    # Custos rastreados: plano inicial (vision=10) vs final (human-review=100).
    assert stats["initial_expected_cost"] < stats["final_expected_cost"]
    described = next(o for o in updated.obligations if o.id == "o-describe")
    assert described.status == "satisfied"
    assert [a.method for a in described.attempts] == [
        "vision",
        "human-review",
    ]
    assert [a.status for a in described.attempts] == ["failed", "succeeded"]
    # O plano final (replanejado) usa o método alternativo, não repete o tentado.
    methods = [
        step.method for step in plan.steps if step.obligation_id == "o-describe"
    ]
    assert methods == ["human-review"]
    assert updated.status == "completed"


def test_replanning_loop_exhausts_methods_gracefully():
    manifest = make_manifest()
    registry = MethodRegistry()
    registry.register("docling", _ok)
    registry.register("vision", _fail)
    registry.register("human-review", _fail)

    orchestrator = _orchestrator(registry)
    (
        updated,
        _plan,
        _comparison,
        report,
        stats,
    ) = orchestrator._execute_with_replanning(manifest)

    assert stats["failure"] is not None
    assert report.status == "failed"
    assert stats["replans"] == 1
    described = next(o for o in updated.obligations if o.id == "o-describe")
    assert described.status == "failed"
    assert len(described.attempts) == 2
    assert updated.status == "failed"


def test_replanning_loop_respects_max_replans():
    manifest = make_manifest()
    manifest.obligations[1] = Obligation(
        id="o-describe",
        kind="describe-image",
        target_ids=["element-1"],
        dependencies=["o-extract"],
        admissible_methods=["m-a", "m-b", "m-c"],
        method_costs={"m-a": 10, "m-b": 20, "m-c": 30},
        rationale="Descrever a imagem",
    )
    registry = MethodRegistry()
    registry.register("docling", _ok)
    for method in ("m-a", "m-b", "m-c"):
        registry.register(method, _fail)

    orchestrator = _orchestrator(registry, max_replans=1)
    (
        updated,
        _plan,
        _comparison,
        report,
        stats,
    ) = orchestrator._execute_with_replanning(manifest)

    assert stats["failure"] is not None
    assert "Limite de replanejamentos" in stats["failure"]
    assert stats["replans"] == 1
    assert report.status == "replan-required"
    described = next(o for o in updated.obligations if o.id == "o-describe")
    # Duas tentativas (m-a e m-b); m-c nunca roda porque o limite interrompe.
    assert [a.method for a in described.attempts] == ["m-a", "m-b"]
    assert updated.status == "failed"


def test_execution_metrics_capture_recovery_and_costs():
    from backend.agents.pddl_orchestrator import (
        _execution_metrics_from_manifest,
    )

    manifest = make_manifest()
    registry = MethodRegistry()
    registry.register("docling", _ok)
    registry.register("vision", _fail)
    registry.register("human-review", _ok)

    orchestrator = _orchestrator(registry)
    updated, *_ = orchestrator._execute_with_replanning(manifest)

    metrics = _execution_metrics_from_manifest(updated)
    assert metrics["recovered_obligations"] == 1
    assert metrics["human_review_obligations"] == 1
    assert metrics["winner_by_method"] == {"docling": 1, "human-review": 1}
    assert metrics["failed_attempts"] == 1
    assert metrics["wasted_cost"] == 10  # custo do vision que falhou
    assert metrics["executed_cost"] == 105  # docling(5) + human-review(100)
    assert metrics["by_kind"]["describe-image"] == {
        "total": 1,
        "satisfied": 1,
    }


def test_replanning_second_problem_excludes_tried_and_satisfied():
    manifest = make_manifest()
    registry = MethodRegistry()
    registry.register("docling", _ok)
    registry.register("vision", _fail)
    registry.register("human-review", _ok)

    orchestrator = _orchestrator(registry)
    updated, *_ = orchestrator._execute_with_replanning(manifest)

    # Recompilar o manifesto mutado deve proibir o par tentado e
    # preservar as obrigações já satisfeitas.
    updated.status = "processing"
    compiled = orchestrator.planner.compile_problem(updated)
    assert "(tried o-describe vision)" in compiled.text
    assert "(satisfied o-extract)" in compiled.text
    assert "(satisfied o-describe)" in compiled.text


def test_replanning_formula_cascade_falls_back_to_llm_then_human():
    manifest = make_manifest()
    manifest.elements[0].type = "formula"
    manifest.elements[0].raw_label = "formula"
    manifest.obligations[1] = Obligation(
        id="o-describe",
        kind="verbalize-formula",
        target_ids=["element-1"],
        dependencies=["o-extract"],
        admissible_methods=[
            "mathml",
            "latex-verbalizer",
            "llm-verbalizer",
            "human-review",
        ],
        method_costs={
            "mathml": 10,
            "latex-verbalizer": 20,
            "llm-verbalizer": 60,
            "human-review": 100,
        },
        rationale="Fórmula deve ser acessível",
    )
    registry = MethodRegistry()
    registry.register("docling", _ok)
    registry.register("mathml", _fail)
    registry.register("latex-verbalizer", _fail)
    registry.register("llm-verbalizer", _ok)
    registry.register("human-review", _ok)

    orchestrator = _orchestrator(registry)
    updated, _plan, _c, report, stats = (
        orchestrator._execute_with_replanning(manifest)
    )

    assert stats["failure"] is None
    assert report.status == "completed"
    assert stats["replans"] == 2
    formula = next(o for o in updated.obligations if o.id == "o-describe")
    assert formula.status == "satisfied"
    # Ordem da cascata guiada pelos custos: 10 -> 20 -> 60; humano nunca roda.
    assert [a.method for a in formula.attempts] == [
        "mathml",
        "latex-verbalizer",
        "llm-verbalizer",
    ]
