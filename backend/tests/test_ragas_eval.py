from evaluation.dataset import load_gold_cases
from evaluation.ragas_eval import _extract_score, run_ragas_evaluation
from evaluation.run_eval import main


def test_extract_score_from_json_and_float():
    assert _extract_score('{"score": 0.75, "reason": "ok"}') == 0.75
    assert _extract_score("Score: 0.5") == 0.5
    assert 0.0 <= _extract_score("no number here") <= 1.0


def test_gold_dataset_has_ragas_fields():
    cases = load_gold_cases()
    assert len(cases) >= 3
    assert all(c.question and c.answer and c.reference_answer for c in cases)
    # At least one grounded and one refusal case
    assert any(c.contexts for c in cases)
    assert any(c.should_refuse for c in cases)


def test_ragas_heuristic_runs():
    report = run_ragas_evaluation(force_heuristic=True)
    assert report["mode"] == "heuristic"
    metrics = report["metrics"]
    for key in (
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
        "answer_correctness",
    ):
        assert key in metrics
        assert 0.0 <= metrics[key] <= 1.0
    assert len(report["per_case"]) == report["n_cases"]


def test_run_eval_both_modes(tmp_path):
    out = tmp_path / "eval.json"
    report = main(["--mode", "both", "--force-heuristic", "--out", str(out)])
    assert "classic" in report
    assert "ragas" in report
    assert out.exists()
    assert "precision@k" in report["classic"]["metrics"]
    assert "faithfulness" in report["ragas"]["metrics"]
