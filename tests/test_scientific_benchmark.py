from scripts.benchmark_scientific_corpus import aggregate_reports


def _report(legacy_score: float, pddl_score: float) -> dict:
    def engine(score: float, elapsed_ms: int) -> dict:
        return {
            "status": "ok",
            "elapsed_ms": elapsed_ms,
            "quality": {
                "score": score,
                "dimensions": {
                    "headings": {"score": score / 100, "applicable": True}
                },
            },
        }

    return {"engines": {"legacy": engine(legacy_score, 100), "pddl": engine(pddl_score, 150)}}


def test_aggregate_reports_compares_quality_and_time():
    result = aggregate_reports([_report(60, 80), _report(70, 90)])

    assert result["paired_success_count"] == 2
    assert result["engines"]["legacy"]["quality_mean"] == 65
    assert result["engines"]["pddl"]["quality_mean"] == 85
    assert result["quality_score_delta_pddl_minus_legacy_mean"] == 20
    assert result["verdict"] == "pddl"
    assert result["engines"]["pddl"]["elapsed_ms_mean"] == 150


def test_aggregate_reports_marks_unpaired_failure_inconclusive():
    report = _report(60, 80)
    report["engines"]["pddl"] = {"status": "error", "error": "failed"}

    result = aggregate_reports([report])

    assert result["paired_success_count"] == 0
    assert result["engines"]["pddl"]["failure_count"] == 1
    assert result["verdict"] == "inconclusive"