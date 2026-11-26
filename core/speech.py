"""Speech-to-text with Whisper, then speaking rate, pauses, duration and filler words."""
from functools import lru_cache

from core import config
from core.evaluator import count_fillers, tokenize

IDEAL_WPM = (110, 160)
PAUSE, LONG_PAUSE = 0.5, 2.0   # seconds of silence between words
# Whisper usually deletes "um"/"uh"; a disfluent prompt makes it keep them.
VERBATIM_PROMPT = "Umm, let me think, uh... like, hmm. Okay, so, I mean, here's what I, uh, think."


@lru_cache
def _whisper():
    import whisper
    return whisper.load_model(config.WHISPER_MODEL)


def transcribe(path: str):
    """Returns (transcript, words with start/end times, duration in seconds)."""
    import whisper
    audio = whisper.load_audio(path)   # needs ffmpeg
    result = _whisper().transcribe(audio, word_timestamps=True, initial_prompt=VERBATIM_PROMPT,
                                   condition_on_previous_text=False, fp16=False)
    words = [w for seg in result["segments"] for w in seg.get("words", [])]
    return result["text"].strip(), words, len(audio) / 16000


def analyze(text: str, words: list[dict], duration: float) -> dict:
    n = len(tokenize(text))
    gaps = [b["start"] - a["end"] for a, b in zip(words, words[1:]) if b["start"] - a["end"] >= PAUSE]
    span = max(words[-1]["end"] - words[0]["start"], 0.1) if words else max(duration, 0.1)
    wpm = n / span * 60 if n else 0.0
    long_pauses = sum(g >= LONG_PAUSE for g in gaps)
    fillers = count_fillers(text)
    filler_rate = 100 * sum(fillers.values()) / n if n else 0.0   # per 100 words

    lo, hi = IDEAL_WPM
    pace = 1.0 if lo <= wpm <= hi else max(0.0, (wpm - 60) / (lo - 60)) if wpm < lo else max(0.0, 1 - (wpm - hi) / 70)
    filler_score = max(0.0, 1 - max(0.0, filler_rate - 2) / 10)
    pause_score = max(0.0, 1 - max(0.0, sum(gaps) / span - 0.2) * 2.5
                      - max(0.0, long_pauses / max(span / 60, 0.25) - 1) * 0.15)
    duration_score = min(1.0, duration / 20) if duration < 150 else max(0.5, 1 - (duration - 150) / 180)

    tips = []
    if not lo <= wpm <= hi:
        tips.append(f"You spoke at {wpm:.0f} words/min - aim for {lo}-{hi}.")
    if filler_rate > 3:
        tips.append(f"Filler words were {filler_rate:.1f}% of your speech - pause silently instead.")
    if long_pauses:
        tips.append(f"{long_pauses} long pause(s) over {LONG_PAUSE:.0f}s - outline the answer before speaking.")
    if duration < 20:
        tips.append(f"Only {duration:.0f}s long - expand with an explanation and an example.")
    elif duration > 150:
        tips.append(f"{duration:.0f}s long - keep answers under about 2 minutes.")

    return {
        "duration_sec": round(duration, 1), "word_count": n, "wpm": round(wpm, 1),
        "pace": "good" if lo <= wpm <= hi else "slow" if wpm < lo else "fast",
        "pause_count": len(gaps), "long_pauses": long_pauses, "fillers": fillers,
        "filler_count": sum(fillers.values()), "filler_rate": round(filler_rate, 2),
        "communication_score": round(100 * (0.30 * pace + 0.30 * filler_score + 0.25 * pause_score
                                            + 0.15 * duration_score), 1),
        "tips": tips or ["Great delivery - steady pace, few fillers, well-controlled pauses."],
    }
