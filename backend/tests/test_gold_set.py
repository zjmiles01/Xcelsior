"""CI gate: the extractor must clear precision/recall thresholds on the
hand-labeled gold set. A change that regresses below these fails the build.
Thresholds are deliberately below current performance — they define the
floor we refuse to sink under, not the score we happen to have."""

from app.extraction.evaluation import evaluate_gold_set, format_report

MIN_SKILLS_PRECISION = 0.90
MIN_SKILLS_RECALL = 0.80
MIN_TITLE_ACCURACY = 0.80


def test_gold_set_thresholds():
    report = evaluate_gold_set()

    assert report.documents >= 30
    detail = format_report(report)
    assert report.skills_precision >= MIN_SKILLS_PRECISION, detail
    assert report.skills_recall >= MIN_SKILLS_RECALL, detail
    title_accuracy = report.title_correct / report.title_total if report.title_total else 1.0
    assert title_accuracy >= MIN_TITLE_ACCURACY, detail
