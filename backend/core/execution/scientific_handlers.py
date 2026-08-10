from __future__ import annotations

import re

from backend.core.execution.executor import MethodRegistry
from backend.core.execution.models import MethodResult
from backend.core.manifest.models import Obligation, ProcessingManifest
from backend.pipeline.table_ast import normalize_table_ast, table_ast_from_rows
from backend.tools.code_tools import normalize_code_text


def register_scientific_handlers(registry: MethodRegistry) -> None:
    registry.register("deterministic-caption-link", _link_caption)
    registry.register("docling-table", _validate_docling_table)
    registry.register("pandoc-table", _build_table_from_text)
    registry.register("mathml", _preserve_formula_source)
    registry.register("latex-verbalizer", _verbalize_latex)
    registry.register("pandoc-code", _preserve_code)
    registry.register("human-review", _require_human_review)


def _link_caption(manifest: ProcessingManifest, obligation_id: str) -> MethodResult:
    obligation = _obligation(manifest, obligation_id)
    if len(obligation.target_ids) != 2:
        return _failure("A ligação de legenda exige elemento e caption.")
    target = _element(manifest, obligation.target_ids[0])
    caption = _element(manifest, obligation.target_ids[1])
    relation = target.metadata.get("scientific_caption")
    reverse = caption.metadata.get("scientific_target")
    valid = (
        isinstance(relation, dict)
        and relation.get("element_id") == caption.id
        and isinstance(reverse, dict)
        and reverse.get("element_id") == target.id
    )
    if not valid:
        return _failure("Relação bidirecional entre elemento e legenda não foi validada.")
    return MethodResult(
        success=True,
        validated=True,
        message="Legenda científica ligada e validada.",
    )


def _validate_docling_table(
    manifest: ProcessingManifest,
    obligation_id: str,
) -> MethodResult:
    target = _single_target(manifest, obligation_id)
    table_ast = normalize_table_ast(target.metadata.get("table_ast"))
    if table_ast is None:
        return _failure("Docling não forneceu estrutura tabular validável.")
    target.metadata["table_ast"] = table_ast
    target.metadata["table_accessibility_method"] = "docling-table"
    return MethodResult(
        success=True,
        validated=True,
        message="Estrutura tabular do Docling normalizada e validada.",
    )


def _build_table_from_text(
    manifest: ProcessingManifest,
    obligation_id: str,
) -> MethodResult:
    target = _single_target(manifest, obligation_id)
    rows = _table_rows(target.text or "")
    caption = target.metadata.get("scientific_caption")
    caption_text = str(caption.get("text", "")) if isinstance(caption, dict) else None
    table_ast = table_ast_from_rows(rows, caption=caption_text)
    if table_ast is None or len(rows) < 2:
        return _failure("O texto da tabela não contém linhas suficientes.")
    target.metadata["table_ast"] = table_ast
    target.metadata["table_accessibility_method"] = "pandoc-table"
    return MethodResult(
        success=True,
        validated=True,
        message="Tabela reconstruída deterministicamente a partir do texto.",
    )


def _preserve_formula_source(
    manifest: ProcessingManifest,
    obligation_id: str,
) -> MethodResult:
    target = _single_target(manifest, obligation_id)
    source = (target.text or "").strip()
    if not source:
        return _failure("Fórmula sem representação de origem.")
    target.metadata["formula_source"] = source
    target.metadata["formula_format"] = "latex" if _looks_like_latex(source) else "text"
    return MethodResult(
        success=True,
        validated=True,
        message="Representação original da fórmula preservada.",
    )


def _verbalize_latex(
    manifest: ProcessingManifest,
    obligation_id: str,
) -> MethodResult:
    target = _single_target(manifest, obligation_id)
    source = str(target.metadata.get("formula_source") or target.text or "").strip()
    if not source:
        return _failure("Fórmula sem conteúdo para verbalização.")
    verbalization = _basic_latex_verbalization(source)
    if not verbalization or verbalization == source:
        return _failure("A fórmula requer verbalização especializada ou revisão humana.")
    target.metadata["formula_source"] = source
    target.metadata["formula_verbalization"] = verbalization
    return MethodResult(
        success=True,
        validated=True,
        message="Fórmula verbalizada com regras determinísticas básicas.",
    )


def _preserve_code(manifest: ProcessingManifest, obligation_id: str) -> MethodResult:
    target = _single_target(manifest, obligation_id)
    normalized = normalize_code_text(target.text or "")
    if not normalized.strip():
        return _failure("Bloco de código vazio.")
    target.text = normalized
    target.metadata["code_semantics_preserved"] = True
    return MethodResult(success=True, validated=True, message="Código normalizado.")


def _require_human_review(
    _manifest: ProcessingManifest,
    _obligation_id: str,
) -> MethodResult:
    return _failure("Obrigação encaminhada para revisão humana.")


def _obligation(manifest: ProcessingManifest, obligation_id: str) -> Obligation:
    for obligation in manifest.obligations:
        if obligation.id == obligation_id:
            return obligation
    raise ValueError(f"Obrigação inexistente: {obligation_id}")


def _element(manifest: ProcessingManifest, element_id: str):
    for element in manifest.elements:
        if element.id == element_id:
            return element
    raise ValueError(f"Elemento inexistente: {element_id}")


def _single_target(manifest: ProcessingManifest, obligation_id: str):
    obligation = _obligation(manifest, obligation_id)
    if len(obligation.target_ids) != 1:
        raise ValueError(f"Obrigação {obligation_id} exige exatamente um alvo")
    return _element(manifest, obligation.target_ids[0])


def _failure(message: str) -> MethodResult:
    return MethodResult(success=False, validated=False, message=message)


def _table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip().strip("|")
        if not stripped:
            continue
        cells = [cell.strip() for cell in re.split(r"\s*\|\s*|\t+", stripped)]
        if len(cells) >= 2 and not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            rows.append(cells)
    return rows


def _looks_like_latex(source: str) -> bool:
    return bool(re.search(r"\\[a-zA-Z]+|[_^{}]", source))


def _basic_latex_verbalization(source: str) -> str:
    text = source.strip().strip("$")
    replacements = {
        r"\times": " vezes ",
        r"\cdot": " vezes ",
        r"\pm": " mais ou menos ",
        r"\leq": " menor ou igual a ",
        r"\geq": " maior ou igual a ",
        r"\neq": " diferente de ",
        r"\sum": " somatório ",
        r"\int": " integral ",
    }
    for token, spoken in replacements.items():
        text = text.replace(token, spoken)
    text = re.sub(
        r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}",
        r" fração com numerador \1 e denominador \2 ",
        text,
    )
    text = re.sub(r"([A-Za-z0-9)]+)\^\{?([^{}\s]+)\}?", r"\1 elevado a \2", text)
    text = re.sub(r"([A-Za-z0-9)]+)_\{?([^{}\s]+)\}?", r"\1 índice \2", text)
    text = text.replace("=", " igual a ").replace("+", " mais ")
    text = re.sub(r"\s+", " ", text).strip()
    return text