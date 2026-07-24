"""Gold-set evaluation: run the pure extractor over hand-labeled documents
and score it. Runs in CI on every commit — extractor changes that regress
below thresholds fail the build. Entirely pure (taxonomy from YAML, no
database), so it needs nothing but the repo checkout."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.extraction.core import extract_document
from app.extraction.matcher import TechnologyMatcher
from app.extraction.taxonomy import TaxonomyIndex, load_index

GOLD_SET_PATH = Path(__file__).resolve().parents[2] / "tests" / "gold" / "gold_set.yaml"


@dataclass
class CategoryScore:
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 1.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 1.0


@dataclass
class GoldReport:
    documents: int = 0
    overall: CategoryScore = field(default_factory=CategoryScore)
    per_category: dict[str, CategoryScore] = field(default_factory=dict)
    level_correct: int = 0
    level_total: int = 0
    title_correct: int = 0
    title_total: int = 0
    experience_correct: int = 0
    experience_total: int = 0
    arrangement_correct: int = 0
    arrangement_total: int = 0
    salary_correct: int = 0
    salary_total: int = 0
    mistakes: list[str] = field(default_factory=list)

    @property
    def skills_precision(self) -> float:
        return self.overall.precision

    @property
    def skills_recall(self) -> float:
        return self.overall.recall


def evaluate_gold_set(
    gold_path: Path = GOLD_SET_PATH, index: TaxonomyIndex | None = None
) -> GoldReport:
    index = index or load_index()
    matcher = TechnologyMatcher(index)
    docs = yaml.safe_load(gold_path.read_text())["documents"]

    report = GoldReport(documents=len(docs))
    for doc in docs:
        result = extract_document(
            description_html=doc["text"],
            raw_title=doc["title"],
            index=index,
            matcher=matcher,
        )
        predicted = {t.tech_slug: t for t in result.technologies}
        truth: dict[str, str] = doc.get("technologies") or {}

        for slug in predicted.keys() - truth.keys():
            _score_for(report, index, slug).false_positives += 1
            report.overall.false_positives += 1
            report.mistakes.append(f"{doc['id']}: false positive {slug!r}")
        for slug in truth.keys() - predicted.keys():
            _score_for(report, index, slug).false_negatives += 1
            report.overall.false_negatives += 1
            report.mistakes.append(f"{doc['id']}: missed {slug!r}")
        for slug in predicted.keys() & truth.keys():
            _score_for(report, index, slug).true_positives += 1
            report.overall.true_positives += 1
            report.level_total += 1
            if predicted[slug].requirement_level == truth[slug]:
                report.level_correct += 1

        if doc.get("canonical_title") is not None or (result.title and result.title.canonical_slug):
            report.title_total += 1
            predicted_slug = result.title.canonical_slug if result.title else None
            if predicted_slug == doc.get("canonical_title"):
                report.title_correct += 1
            else:
                report.mistakes.append(
                    f"{doc['id']}: title {predicted_slug!r} != {doc.get('canonical_title')!r}"
                )

        _score_scalar(report, doc, "experience_level", result.experience_level)
        _score_scalar(report, doc, "arrangement", result.arrangement)

        truth_min, truth_max = doc.get("salary_annual_min"), doc.get("salary_annual_max")
        if truth_min is not None:
            report.salary_total += 1
            got = result.salary
            if (
                got is not None
                and int(got.annual_min) == truth_min
                and int(got.annual_max) == truth_max
            ):
                report.salary_correct += 1
            else:
                got_desc = (int(got.annual_min), int(got.annual_max)) if got else None
                report.mistakes.append(
                    f"{doc['id']}: salary {got_desc} != {(truth_min, truth_max)}"
                )
    return report


def _score_for(report: GoldReport, index: TaxonomyIndex, slug: str) -> CategoryScore:
    tech = index.technologies.get(slug)
    category = tech.category if tech else "unknown"
    return report.per_category.setdefault(category, CategoryScore())


def _score_scalar(report: GoldReport, doc: dict, key: str, predicted: str | None) -> None:
    truth = doc.get(key)
    if truth is None and predicted is None:
        return
    total_attr = {"experience_level": "experience", "arrangement": "arrangement"}[key]
    setattr(report, f"{total_attr}_total", getattr(report, f"{total_attr}_total") + 1)
    if truth == predicted:
        setattr(report, f"{total_attr}_correct", getattr(report, f"{total_attr}_correct") + 1)
    else:
        report.mistakes.append(f"{doc['id']}: {key} {predicted!r} != {truth!r}")


def format_report(report: GoldReport) -> str:
    lines = [
        f"gold documents: {report.documents}",
        f"skills:      precision={report.skills_precision:.3f} recall={report.skills_recall:.3f} "
        f"(tp={report.overall.true_positives} fp={report.overall.false_positives} "
        f"fn={report.overall.false_negatives})",
        f"req levels:  {report.level_correct}/{report.level_total} correct on true positives",
        f"titles:      {report.title_correct}/{report.title_total}",
        f"experience:  {report.experience_correct}/{report.experience_total}",
        f"arrangement: {report.arrangement_correct}/{report.arrangement_total}",
        f"salary:      {report.salary_correct}/{report.salary_total}",
        "",
        "per category:",
    ]
    for category, score in sorted(report.per_category.items()):
        lines.append(
            f"  {category:18s} precision={score.precision:.3f} recall={score.recall:.3f}"
        )
    if report.mistakes:
        lines.append("\nmistakes:")
        lines.extend(f"  {m}" for m in report.mistakes[:40])
    return "\n".join(lines)
