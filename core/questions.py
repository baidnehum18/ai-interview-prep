"""Picks interview questions from the question bank by role, skill level and interview type."""
import json
import random
from functools import lru_cache

from core.config import BASE_DIR


@lru_cache
def load_bank() -> dict:
    return json.loads((BASE_DIR / "data" / "question_bank.json").read_text(encoding="utf-8"))


def pick_questions(role: str, level: str, interview_type: str, n: int, avoid: set = frozenset()) -> list[dict]:
    """HR questions first (a warm-up), then technical ones for the role.

    Questions the student saw recently go last; technical questions closest to the
    chosen level come first. A mixed interview is about one-third HR.
    """
    bank, levels = load_bank()["questions"], load_bank()["levels"]
    n_hr = {"technical": 0, "hr": n}.get(interview_type, max(1, n // 3))

    def best_first(pool):
        random.shuffle(pool)
        distance = lambda q: abs(levels.index(q["level"]) - levels.index(level)) if q["level"] in levels else 0
        return sorted(pool, key=lambda q: (q["id"] in avoid, distance(q)))

    hr = best_first([q for q in bank if q["type"] == "hr"])
    tech = best_first([q for q in bank if q["type"] == "technical" and q["role"] == role])
    return hr[:n_hr] + tech[:n - n_hr]
