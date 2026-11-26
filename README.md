# AI-Based Interview Preparation and Mock Interview System

**Team:** Nehum Baid (S24CSEU1952) · Amarjeet Kumar (S24CSEU1968) · Harsh Vardhan Singh (S24CSEU1965)  
**Mentor:** Neeraj Jain, Lab Faculty · Bennett University, CSET312 Mini Project

Students take mock technical and HR interviews for a chosen job role and skill level, answer by
typing or speaking, and get scored feedback on every answer plus a progress dashboard.

## Run

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt                        # also install ffmpeg for voice answers
streamlit run app.py
```

On a Mac you can instead double-click **Start Interview App.command**. Settings (MySQL, LLM) go in
a `.env` file - see `.env.example`. Without one, the app uses a local SQLite file and NLP-only scoring.

## Code

| File | What it does |
| --- | --- |
| `app.py` | Streamlit web app: sign-in, mock interview (text or voice), report, dashboard |
| `core/questions.py` | Picks questions from `data/question_bank.json` by role, level and type |
| `core/evaluator.py` | Scores answers: Sentence-Transformer similarity, key-concept coverage, STAR check, optional LLM judge |
| `core/speech.py` | Whisper speech-to-text; speaking rate, pauses, duration, filler words |
| `core/feedback.py` | Interview summary: grade, weak areas, what to practise |
| `core/llm.py` | Optional LLM through any OpenAI-compatible API (OpenAI, Claude, Groq, Ollama) |
| `core/database.py` | SQLAlchemy tables (users, interview_sessions, session_questions) and queries |
| `core/config.py` | Settings from `.env` |
| `database/schema.sql` | The same tables as plain MySQL |

## How an answer is scored

* **Relevance, completeness, correctness** (0-100) from cosine similarity of all-MiniLM-L6-v2 embeddings
  (answer vs question, answer vs model answer), share of key concepts covered, and answer length.
  HR answers are also checked for STAR structure (situation, task, action, result) and specific detail.
* With an LLM configured, the LLM's 0-10 grades are blended in (60% for relevance and completeness,
  70% for correctness) and it writes the feedback.
* **Communication**: for voice, 30% pace (ideal 110-160 words/min) + 30% filler words + 25% pauses
  + 15% duration; for text, sentence length, filler and vague words.
* **Question score** = 0.85 × content + 0.15 × communication (scaled down when content is weak).
  Content weights: technical 25% relevance, 30% completeness, 45% correctness; HR 30/35/35.
* **Grade**: Excellent ≥ 85, Good ≥ 70, Average ≥ 55; topics below 60 are weak areas.
