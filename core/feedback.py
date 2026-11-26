"""End-of-interview report: overall score, grade, weak areas and what to practise next."""
import json
from statistics import mean

from core import llm

WEAK = 60   # topics or skills averaging below this are weak areas


def grade(score: float) -> str:
    return ("Excellent" if score >= 85 else "Good" if score >= 70
            else "Average" if score >= 55 else "Needs Improvement")


def summarize(questions: list[dict], role: str) -> dict:
    answered = [q for q in questions if q["score"] is not None]
    if not answered:
        return {"overall_score": 0, "grade": "Not attempted", "technical_score": None,
                "communication_score": None, "weak_areas": [], "recommendations": []}

    def avg(key, items=answered):
        values = [q[key] for q in items if q[key] is not None]
        return round(mean(values), 1) if values else None

    technical = [q for q in answered if q["question_type"] == "technical"]
    hr = [q for q in answered if q["question_type"] == "hr"]
    dimensions = {d: avg(d) for d in ("relevance", "completeness", "correctness", "communication")}
    topics = {t: round(mean(q["score"] for q in answered if q["topic"] == t), 1)
              for t in dict.fromkeys(q["topic"] for q in answered)}
    weak_topics = sorted((t for t, s in topics.items() if s < WEAK), key=topics.get)

    recommendations = []
    for topic in weak_topics:
        q = next(q for q in answered if q["topic"] == topic)
        if q["question_type"] == "hr":
            recommendations.append(f"{topic}: prepare a STAR story (situation, task, action, result) and rehearse it aloud.")
        else:
            gaps = (q["feedback"] or {}).get("missing_points") or q["keywords"][:4]
            recommendations.append(f"{topic}: revise {', '.join(gaps[:4])}.")
    if dimensions["communication"] is not None and dimensions["communication"] < WEAK:
        tips = {t for q in answered for t in (q["speech_metrics"] or {}).get("tips", [])}
        recommendations += sorted(tips)[:3] or ["Practise answering aloud in 1-2 minutes with clear sentences."]
    if not weak_topics and avg("score") >= 75:
        recommendations.append(f"Try the next skill level or a mixed {role} interview.")

    summary = {
        "overall_score": avg("score"), "grade": grade(avg("score")),
        "technical_score": avg("score", technical) if technical else None,
        "hr_score": avg("score", hr) if hr else None,
        "communication_score": dimensions["communication"],
        "dimension_scores": dimensions, "topic_scores": topics,
        "weak_areas": weak_topics + [f"Answer {d}" for d, v in dimensions.items() if v is not None and v < WEAK],
        "strong_topics": [t for t, s in topics.items() if s >= 75],
        "recommendations": recommendations,
    }
    summary["overall_feedback"] = _overall_feedback(summary, answered, role)
    return summary


def _overall_feedback(summary: dict, answered: list[dict], role: str) -> str:
    results = [{"topic": q["topic"], "score": q["score"], "verdict": (q["feedback"] or {}).get("verdict")}
               for q in answered]
    text = llm.ask("You are a supportive interview coach writing a short review for a student.",
                   f"Mock interview for a {role} role. Overall {summary['overall_score']}/100. "
                   f"Results: {json.dumps(results)}. Write 4-5 sentences: what went well, what to improve, "
                   f"and a plan for next week. Plain text.", max_tokens=400)
    if text:
        return text.strip()
    lines = [f"You scored {summary['overall_score']}/100 ({summary['grade']})."]
    if summary["strong_topics"]:
        lines.append("You did well on " + ", ".join(summary["strong_topics"][:3]) + ".")
    if summary["weak_areas"]:
        lines.append("Focus next on " + ", ".join(summary["weak_areas"][:3]) + ".")
    return " ".join(lines + ["Retake an interview after revising to track your progress."])
