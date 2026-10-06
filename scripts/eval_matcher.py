import sys
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.resume_analyzer.matcher import VacancyMatcher


def evaluate_matcher(golden_path: str = "tests/golden/matcher_golden.json") -> Dict[str, float]:
    path = Path(golden_path)
    if not path.is_file():
        raise FileNotFoundError(f"Golden dataset not found at {path}")

    with open(path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    precisions_10: List[float] = []
    recalls_10: List[float] = []
    precisions_5: List[float] = []
    recalls_5: List[float] = []

    now = datetime.datetime.now(datetime.timezone.utc)

    for case in cases:
        candidate = case["candidate"]
        cand_skills = candidate.get("skills", [])
        cand_grade = candidate.get("grade", "Middle")
        cand_role = candidate.get("role", "")
        cand_exp = float(candidate.get("experience_years", 2.0))

        scored_vacancies = []
        for vac in case["vacancies"]:
            days_ago = vac.get("published_days_ago", 1)
            pub_date = now - datetime.timedelta(days=days_ago)

            res = VacancyMatcher.match(
                candidate_skills=cand_skills,
                candidate_grade=cand_grade,
                candidate_role=cand_role,
                candidate_experience=cand_exp,
                vacancy_title=vac.get("title", ""),
                vacancy_description=vac.get("title", ""),
                vacancy_requirements=vac.get("skills", []),
                risk_level="safe",
                vacancy_min_exp=vac.get("experience_years"),
                vacancy_grade=vac.get("grade"),
                grade_confidence=vac.get("grade_confidence", 1.0),
                published_at=pub_date
            )

            scored_vacancies.append({
                "id": vac["id"],
                "score": res["score"],
                "is_relevant": vac.get("is_relevant", False)
            })

        # Rank vacancies by score descending
        scored_vacancies.sort(key=lambda x: x["score"], reverse=True)

        total_relevant = sum(1 for v in scored_vacancies if v["is_relevant"])
        if total_relevant == 0:
            continue

        # Top 10 evaluation
        top_10 = scored_vacancies[:10]
        rel_in_top_10 = sum(1 for v in top_10 if v["is_relevant"])
        prec_10 = rel_in_top_10 / len(top_10) if top_10 else 0.0
        rec_10 = rel_in_top_10 / total_relevant
        precisions_10.append(prec_10)
        recalls_10.append(rec_10)

        # Top 5 evaluation
        top_5 = scored_vacancies[:5]
        rel_in_top_5 = sum(1 for v in top_5 if v["is_relevant"])
        prec_5 = rel_in_top_5 / len(top_5) if top_5 else 0.0
        rec_5 = rel_in_top_5 / total_relevant
        precisions_5.append(prec_5)
        recalls_5.append(rec_5)

    mean_p10 = sum(precisions_10) / len(precisions_10) if precisions_10 else 0.0
    mean_r10 = sum(recalls_10) / len(recalls_10) if recalls_10 else 0.0
    mean_p5 = sum(precisions_5) / len(precisions_5) if precisions_5 else 0.0
    mean_r5 = sum(recalls_5) / len(recalls_5) if recalls_5 else 0.0

    return {
        "cases_evaluated": len(cases),
        "mean_precision_at_10": round(mean_p10, 4),
        "mean_recall_at_10": round(mean_r10, 4),
        "mean_precision_at_5": round(mean_p5, 4),
        "mean_recall_at_5": round(mean_r5, 4),
    }


if __name__ == "__main__":
    metrics = evaluate_matcher()
    print("=" * 50)
    print("Matcher Golden Dataset Evaluation Results:")
    print("=" * 50)
    for k, v in metrics.items():
        print(f"  {k}: {v}")
    print("=" * 50)

    assert metrics["mean_recall_at_10"] >= 0.85, f"Recall@10 {metrics['mean_recall_at_10']} < 0.85"
    assert metrics["mean_precision_at_10"] >= 0.45, f"Precision@10 {metrics['mean_precision_at_10']} < 0.45"
    print("ALL EVALUATION THRESHOLDS PASSED!")
