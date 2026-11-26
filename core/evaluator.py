"""Scores an answer from 0 to 100 on relevance, completeness, correctness and communication.

1. NLP layer (always): Sentence-Transformer similarity to the question and to the model
   answer, coverage of the key concepts, answer length, and STAR structure for HR answers.
2. LLM layer (when configured): an LLM grades the answer against the model answer;
   its scores are blended with the NLP scores and it writes the feedback.
3. Communication: speech metrics for voice answers, writing clarity for typed ones.
"""
import json
import re
from functools import lru_cache

import numpy as np

from core import config, llm

# Raw cosine values measured with all-MiniLM-L6-v2, mapped to 0 and 1.
QUESTION_ANCHORS = (0.15, 0.55)
REFERENCE_ANCHORS = (0.45, 0.95)

STOPWORDS = set("a an the and or but of to in on at for by with from as is are was were be been "
                "it its this that these those i you we they my our your".split())
FILLERS = ["um", "umm", "uh", "uhm", "er", "erm", "hmm", "you know", "i mean", "basically",
           "actually", "literally", "sort of", "kind of"]
STAR_CUES = {
    "situation": r"\b(when i|during|in my|project|internship|last (year|semester)|there was)\b",
    "task": r"\b(my (task|role|job|goal)|i was responsible|needed to|had to|the goal)\b",
    "action": r"\b(i (decided|built|created|led|organi[sz]ed|proposed|designed|set up|talked|"
              r"learned|analy[sz]ed|coordinated)|so i|then i)\b",
    "result": r"\b(as a result|result(ed)?|outcome|improved|increased|reduced|achieved|"
              r"successfully|i learned|delivered)\b|\d+\s?%",
}


# ---------------------------------------------------------------- text helpers
def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", re.sub(r"[()'’]", "", text.lower()))


def stem(word: str) -> str:
    """Tiny stemmer so 'regularisation', 'regularization' and 'regularize' match."""
    word = re.sub(r"is(e|ed|es|ing|ation)$", r"iz\1", word)
    for suffix in ("ization", "ation", "ments", "ment", "ness", "ing", "ed"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)]
            break
    else:
        if word.endswith("ies"):
            word = word[:-3] + "y"
        elif re.search(r"(ss|x|ch|sh)es$", word):
            word = word[:-2]
        elif word.endswith("s") and not word.endswith(("ss", "us")) and len(word) > 3:
            word = word[:-1]
    return word.rstrip("e") if len(word) > 4 else word


def count_fillers(text: str) -> dict[str, int]:
    low = " " + " ".join(tokenize(text)) + " "
    counts = {f: low.count(f" {f} ") for f in FILLERS}
    return {f: c for f, c in counts.items() if c}


# ---------------------------------------------------------------- NLP scores
@lru_cache
def _embedder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(config.EMBEDDING_MODEL)


def similarity(a: str, b: str, anchors: tuple) -> float:
    """Cosine similarity of two texts' embeddings, rescaled to 0-1."""
    emb = _embedder().encode([a, b], normalize_embeddings=True)
    low, high = anchors
    return float(np.clip((float(emb[0] @ emb[1]) - low) / (high - low), 0, 1))


def keyword_coverage(answer: str, keywords: list[str]):
    """Share of key concepts mentioned (half credit if half of a phrase's words appear)."""
    words = {stem(t) for t in tokenize(answer)}
    covered, missing, total = [], [], 0.0
    for kw in keywords:
        parts = [stem(t) for t in tokenize(kw) if t not in STOPWORDS] or [stem(t) for t in tokenize(kw)]
        hit = sum(p in words for p in parts) / len(parts) if parts else 1.0
        total += 1.0 if hit == 1 else 0.5 if hit >= 0.5 else 0.0
        (covered if hit >= 0.5 else missing).append(kw)
    return total / max(1, len(keywords)), covered, missing


def length_factor(n_words: int, qtype: str) -> float:
    """0 for a one-liner, 1 once the answer is long enough (70 words technical, 100 HR)."""
    low, ideal = (25, 70) if qtype == "technical" else (40, 100)
    if n_words <= 3:
        return 0.0
    if n_words < low:
        return 0.5 * n_words / low
    return min(1.0, 0.5 + 0.5 * (n_words - low) / (ideal - low))


def specificity(answer: str) -> float:
    """Concrete detail in HR answers: numbers, first-person ownership, named things."""
    has_number = bool(re.search(r"\d", answer))
    first_person = len(re.findall(r"\b(i|my)\b", answer.lower()))
    names = len(re.findall(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-zA-Z]+", answer))
    return 0.35 * has_number + 0.35 * min(1, first_person / 4) + 0.3 * min(1, names / 3)


def writing_score(answer: str) -> float:
    """Clarity of a typed answer: sentence length, filler words, vague words."""
    n = len(tokenize(answer))
    sentences = max(1, len(re.findall(r"[.!?](\s|$)", answer)))
    avg = n / sentences
    sentence_score = 1.0 if 8 <= avg <= 28 else max(0.3, 1 - abs(avg - (8 if avg < 8 else 28)) / 30)
    filler_score = max(0.0, 1 - sum(count_fillers(answer).values()) / max(1, n) * 20)
    vague = len(re.findall(r"\b(stuff|things?|etc|something|somehow|whatever)\b", answer.lower()))
    return 100 * (0.45 * sentence_score + 0.35 * filler_score + 0.20 * max(0.4, 1 - vague * 0.12))


# ---------------------------------------------------------------- LLM judge
def llm_judge(q: dict, answer: str) -> dict | None:
    correctness = ("technical accuracy: are the statements correct?" if q["question_type"] == "technical"
                   else "quality: is it a specific, well-structured STAR answer?")
    data = llm.ask_json(
        "You are a strict but encouraging interview coach. Grade content, not grammar. Reply with JSON only.",
        f"Question: {q['question']}\nReference answer: {q['ideal_answer']}\n"
        f"Key concepts: {json.dumps(q['keywords'])}\nCandidate answer: \"\"\"{answer}\"\"\"\n\n"
        f"Score 0-10: relevance (answers the question?), completeness (covers the reference's "
        f"points?), correctness ({correctness}).\nReturn JSON with keys relevance, completeness, "
        f"correctness, strengths (max 3), improvements (max 3), missing_points (max 4), verdict (one sentence).")
    try:
        return {**data, **{k: min(10.0, max(0.0, float(data[k]))) for k in ("relevance", "completeness", "correctness")}}
    except (TypeError, KeyError, ValueError):
        return None


# ---------------------------------------------------------------- main entry
def evaluate_answer(q: dict, answer: str, speech: dict | None = None) -> dict:
    """q is a session question (question, ideal_answer, keywords, question_type, topic)."""
    answer, qtype = (answer or "").strip(), q["question_type"]
    n_words = len(tokenize(answer))
    if n_words < 3:
        return {"relevance": 0, "completeness": 0, "correctness": 0, "communication": 0, "score": 0,
                "speech_metrics": speech,
                "feedback": {"strengths": [], "improvements": ["No answer given - even a partial answer earns credit."],
                             "missing_points": q["keywords"][:5], "covered_keywords": [], "verdict": "Unanswered."}}

    # NLP layer
    sim_q = similarity(answer, q["question"], QUESTION_ANCHORS)
    sim_ref = similarity(answer, q["ideal_answer"], REFERENCE_ANCHORS)
    coverage, covered, missing = keyword_coverage(answer, q["keywords"])
    length = length_factor(n_words, qtype)
    star = {part: bool(re.search(cue, answer.lower())) for part, cue in STAR_CUES.items()}
    if qtype == "hr":
        star_share = sum(star.values()) / 4
        scores = {"relevance": max(sim_q, 0.85 * sim_ref, min(1, 1.6 * coverage)),
                  "completeness": 0.4 * star_share + 0.3 * coverage + 0.3 * length,
                  "correctness": 0.45 * star_share + 0.35 * specificity(answer) + 0.20 * sim_ref}
    else:
        scores = {"relevance": max(sim_q, 0.85 * sim_ref),
                  "completeness": (0.6 * coverage + 0.4 * sim_ref) * (0.4 + 0.6 * length),
                  "correctness": (0.6 * sim_ref + 0.4 * coverage) * (0.6 + 0.4 * length)}
    scores = {k: 100 * v for k, v in scores.items()}

    # LLM layer: 60% LLM for relevance and completeness, 70% for correctness
    judge = llm_judge(q, answer)
    if judge:
        for dim, weight in (("relevance", 0.6), ("completeness", 0.6), ("correctness", 0.7)):
            scores[dim] = (1 - weight) * scores[dim] + weight * 10 * judge[dim]

    communication = speech["communication_score"] if speech else writing_score(answer)
    weights = (0.30, 0.35, 0.35) if qtype == "hr" else (0.25, 0.30, 0.45)
    content = sum(w * scores[d] for w, d in zip(weights, ("relevance", "completeness", "correctness")))
    # Delivery only earns full credit when there is real content behind it.
    overall = 0.85 * content + 0.15 * communication * min(1, content / 50)

    feedback = _feedback(qtype, scores, covered, missing, n_words, star, judge)
    return {**{k: round(v, 1) for k, v in scores.items()}, "communication": round(communication, 1),
            "score": round(overall, 1), "speech_metrics": speech, "feedback": feedback}


def _feedback(qtype, scores, covered, missing, n_words, star, judge) -> dict:
    strengths, improvements = [], []
    if covered:
        strengths.append("Covered key concepts: " + ", ".join(covered[:5]) + ".")
    if missing:
        improvements.append("Also explain: " + ", ".join(missing[:4]) + ".")
    if scores["relevance"] < 45:
        improvements.append("The answer drifts from the question - answer it directly first.")
    if n_words < (25 if qtype == "technical" else 40):
        improvements.append(f"Too short ({n_words} words) - add an explanation and an example.")
    if qtype == "hr":
        absent = [part for part, found in star.items() if not found]
        if absent:
            improvements.append("Use the STAR method - add the " + ", ".join(absent) + ".")
        else:
            strengths.append("Clear STAR structure.")
    avg = sum(scores.values()) / 3
    verdict = ("Strong answer." if avg >= 75 else "Good attempt - add more depth." if avg >= 55
               else "Partial answer - revisit this topic." if avg >= 35 else "Weak answer - practise this topic.")
    if judge:  # the LLM's feedback first, then our most useful line
        strengths = [str(s) for s in judge.get("strengths", [])][:3] + strengths[:1]
        improvements = [str(s) for s in judge.get("improvements", [])][:3] + improvements[:1]
        missing = [str(s) for s in judge.get("missing_points", [])][:4] or missing
        verdict = judge.get("verdict") or verdict
    return {"strengths": strengths, "improvements": improvements, "missing_points": missing[:5],
            "covered_keywords": covered, "verdict": verdict}
