from datetime import datetime, timezone

from backend.core.manifest.models import (
    ExtractorRun,
    ManifestElement,
    ManifestSummary,
    PageDescriptor,
    ProcessingManifest,
    SourceDocument,
)
from backend.pipeline.scientific.enricher import enrich_scientific_manifest


def _manifest() -> ProcessingManifest:
    now = datetime(2026, 8, 10, tzinfo=timezone.utc)
    elements = [
        ManifestElement(
            id="element-000001",
            type="heading",
            raw_label="section_header",
            reading_order=1,
            hierarchy_level=1,
            text="Resultados",
            page_number=1,
        ),
        ManifestElement(
            id="element-000002",
            type="picture",
            raw_label="picture",
            reading_order=2,
            hierarchy_level=1,
            page_number=1,
        ),
        ManifestElement(
            id="element-000003",
            type="caption",
            raw_label="caption",
            reading_order=3,
            hierarchy_level=1,
            text="Figura 1: Comparação dos resultados por método.",
            page_number=1,
        ),
    ]
    return ProcessingManifest(
        manifest_id="manifest-scientific",
        created_at=now,
        source=SourceDocument(
            document_id="document-scientific",
            filename="paper.pdf",
            path="/tmp/paper.pdf",
            media_type="application/pdf",
            byte_size=1,
            sha256="a" * 64,
        ),
        extractor=ExtractorRun(
            version="test",
            started_at=now,
            completed_at=now,
            duration_ms=1,
        ),
        title="Paper",
        language="pt-BR",
        pages=[PageDescriptor(page_number=1, element_ids=[item.id for item in elements])],
        elements=elements,
        summary=ManifestSummary(
            page_count=1,
            element_count=3,
            observation_count=0,
            obligation_count=0,
            element_types={"heading": 1, "picture": 1, "caption": 1},
        ),
    )


def test_links_figure_to_caption_and_current_section():
    manifest = _manifest()

    enrich_scientific_manifest(manifest)

    picture = manifest.elements[1]
    caption = manifest.elements[2]
    assert picture.metadata["scientific_caption"]["element_id"] == caption.id
    assert picture.metadata["scientific_section"]["title"] == "Resultados"
    assert caption.metadata["scientific_target"]["element_id"] == picture.id


def test_creates_caption_obligation_and_dependency_before_description():
    manifest = _manifest()
    from backend.core.manifest.builder import _derive_processing_needs

    observations, obligations = _derive_processing_needs(manifest.elements)
    manifest.observations = observations
    manifest.obligations = obligations
    manifest.summary.observation_count = len(observations)
    manifest.summary.obligation_count = len(obligations)

    enrich_scientific_manifest(manifest)

    by_id = {item.id: item for item in manifest.obligations}
    link_id = "obligation-link-caption-000002"
    describe = by_id["obligation-describe-image-000002"]
    assert link_id in by_id
    assert link_id in describe.dependencies