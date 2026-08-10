from backend.core.execution.executor import MethodRegistry
from backend.core.execution.scientific_handlers import register_scientific_handlers
from backend.core.manifest.models import ManifestElement, Obligation

from tests.test_pddl_orchestrator import _sample_manifest


def test_caption_handler_validates_bidirectional_relation():
    manifest = _sample_manifest()
    manifest.elements.extend(
        [
            ManifestElement(
                id="el-picture",
                type="picture",
                raw_label="picture",
                reading_order=3,
                hierarchy_level=1,
                metadata={
                    "scientific_caption": {
                        "element_id": "el-caption",
                        "label": "Figura 1",
                        "text": "Figura 1: resultado.",
                    }
                },
            ),
            ManifestElement(
                id="el-caption",
                type="caption",
                raw_label="caption",
                reading_order=4,
                hierarchy_level=1,
                text="Figura 1: resultado.",
                metadata={
                    "scientific_target": {
                        "element_id": "el-picture",
                        "type": "picture",
                    }
                },
            ),
        ]
    )
    obligation = Obligation(
        id="o-caption",
        kind="link-scientific-caption",
        target_ids=["el-picture", "el-caption"],
        admissible_methods=["deterministic-caption-link"],
        method_costs={"deterministic-caption-link": 1},
        rationale="teste",
    )
    manifest.obligations.append(obligation)
    registry = MethodRegistry()
    register_scientific_handlers(registry)

    result = registry.get("deterministic-caption-link")(manifest, obligation.id)  # type: ignore[misc]

    assert result.success is True
    assert result.validated is True


def test_latex_handler_preserves_source_and_adds_verbalization():
    manifest = _sample_manifest()
    formula = ManifestElement(
        id="el-formula",
        type="formula",
        raw_label="formula",
        reading_order=3,
        hierarchy_level=1,
        text=r"E = \frac{m c^2}{2}",
    )
    obligation = Obligation(
        id="o-formula",
        kind="verbalize-formula",
        target_ids=[formula.id],
        admissible_methods=["latex-verbalizer"],
        method_costs={"latex-verbalizer": 1},
        rationale="teste",
    )
    manifest.elements.append(formula)
    manifest.obligations.append(obligation)
    registry = MethodRegistry()
    register_scientific_handlers(registry)

    result = registry.get("latex-verbalizer")(manifest, obligation.id)  # type: ignore[misc]

    assert result.success is True
    assert formula.metadata["formula_source"] == r"E = \frac{m c^2}{2}"
    assert "igual a" in formula.metadata["formula_verbalization"]
    assert "fração" in formula.metadata["formula_verbalization"]


def test_human_review_is_not_reported_as_automatic_success():
    registry = MethodRegistry()
    register_scientific_handlers(registry)

    result = registry.get("human-review")(_sample_manifest(), "o-1")  # type: ignore[misc]

    assert result.success is False
    assert result.validated is False