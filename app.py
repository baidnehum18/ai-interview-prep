"""AI-Based Interview Preparation and Mock Interview System.

Run:  streamlit run app.py
"""
import os
import tempfile

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import database as db
from core import llm
from core.evaluator import evaluate_answer
from core.feedback import summarize
from core.questions import load_bank, pick_questions

st.set_page_config(page_title="AI Mock Interview", page_icon="🎤", layout="wide")
db.init_db()
bank = load_bank()
state = st.session_state
for key in ("user", "session_id", "q_index", "report_id"):
    state.setdefault(key, None)
PAGES = ["🎤 Mock interview", "📄 Results", "📈 Dashboard"]
if "goto" in state:   # switch page from code
    state.page = state.pop("goto")


def color(score):
    return "#16A34A" if score >= 75 else "#2563EB" if score >= 60 else "#D97706" if score >= 45 else "#DC2626"


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🎤 AI Mock Interview")
    if state.user is None:
        with st.form("login"):
            name = st.text_input("Username", placeholder="e.g. nehum_baid")
            if st.form_submit_button("Sign in", type="primary") and name.strip():
                state.user = {"id": db.get_or_create_user(name.strip()), "name": name.strip()}
                st.rerun()
    else:
        st.success(f"Signed in as **{state.user['name']}**")
        if st.button("Sign out"):
            state.clear()
            st.rerun()
        st.radio("Go to", PAGES, key="page", label_visibility="collapsed")
    st.caption(f"LLM feedback: {'on' if llm.enabled() else 'off (NLP scoring only)'}")

if state.user is None:
    st.title("AI-Based Interview Preparation & Mock Interview System")
    st.write("Practise technical and HR interviews for your target role. Answer by typing or speaking "
             "and get instant feedback on relevance, completeness, correctness and delivery.")
    st.info("👈 Sign in with a username to start.")
    st.stop()


# ---------------------------------------------------------------- shared view
def show_feedback(q):
    fb = q["feedback"] or {}
    labels = [("Score", "score"), ("Relevance", "relevance"), ("Completeness", "completeness"),
              ("Correctness" if q["question_type"] == "technical" else "Structure", "correctness"),
              ("Communication", "communication")]
    for col, (label, key) in zip(st.columns(5), labels):
        col.metric(label, f"{q[key]:.0f}")
    st.markdown(f"**Verdict:** {fb.get('verdict', '')}")
    if q["answer_text"]:
        st.info(q["answer_text"])
    left, right = st.columns(2)
    left.markdown("**✅ Strengths**\n\n" + "\n".join(f"- {s}" for s in fb.get("strengths") or ["—"]))
    right.markdown("**🛠️ To improve**\n\n" + "\n".join(f"- {s}" for s in fb.get("improvements") or ["—"]))
    if sm := q["speech_metrics"]:
        cols = st.columns(4)
        cols[0].metric("Pace", f"{sm['wpm']:.0f} wpm", sm["pace"], delta_color="off")
        cols[1].metric("Duration", f"{sm['duration_sec']:.0f} s")
        cols[2].metric("Filler words", sm["filler_count"])
        cols[3].metric("Long pauses", sm["long_pauses"])
        st.markdown("\n".join(f"- {tip}" for tip in sm["tips"]))
    with st.expander("📘 Model answer"):
        st.write(q["ideal_answer"])
        st.caption("Key concepts: " + ", ".join(q["keywords"]))


# ---------------------------------------------------------------- interview
def transcribe(audio):
    from core import speech   # imported here so Whisper only loads when needed
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio.getvalue())
    try:
        text, words, duration = speech.transcribe(f.name)
    finally:
        os.remove(f.name)
    return text, speech.analyze(text, words, duration)


def setup_page():
    st.header("Start a mock interview")
    with st.form("setup"):
        c1, c2 = st.columns(2)
        role = c1.selectbox("Job role", bank["roles"])
        level = c2.selectbox("Skill level", bank["levels"], index=1, format_func=str.title)
        itype = c1.radio("Interview type", ["technical", "hr", "mixed"], horizontal=True,
                         format_func=lambda t: {"technical": "Technical", "hr": "HR", "mixed": "Mixed"}[t])
        mode = c2.radio("Answer by", ["text", "voice"], horizontal=True,
                        format_func=lambda m: "⌨️ Typing" if m == "text" else "🎙️ Speaking")
        n = c1.slider("Number of questions", 3, 8, 5)
        if st.form_submit_button("Start interview", type="primary"):
            recent = db.list_sessions(state.user["id"])[-3:]   # avoid repeating recent questions
            seen = {q["question_key"] for s in recent for q in s["questions"]}
            questions = pick_questions(role, level, itype, n, seen)
            state.session_id = db.create_session(state.user["id"], role, level, itype, mode, questions)
            state.q_index = 0
            st.rerun()


def finish_interview(session):
    summary = summarize(session["questions"], session["job_role"])
    db.complete_session(session["id"], summary)
    state.report_id, state.session_id, state.goto = session["id"], None, PAGES[1]
    st.rerun()


def interview_page():
    if state.session_id is None:
        return setup_page()
    session = db.get_session(state.session_id)
    questions, i = session["questions"], state.q_index
    q = questions[i]
    answered = sum(x["score"] is not None for x in questions)
    st.caption(f"{session['job_role']} · {session['skill_level'].title()} · {session['interview_type'].upper()}")
    st.progress(answered / len(questions), text=f"Question {i + 1} of {len(questions)}")
    st.subheader(f"{q['question_type'].upper()} · {q['topic']}")
    st.markdown(f"### {q['question']}")

    if q["score"] is None:
        audio = st.audio_input("Record your answer", key=f"rec{q['id']}") if session["answer_mode"] == "voice" else None
        text = st.text_area("Your answer" if audio is None else "…or type it instead", key=f"txt{q['id']}", height=200)
        c1, c2, c3 = st.columns([1, 1, 4])
        if c1.button("Submit", type="primary", disabled=not (text.strip() or audio)):
            with st.spinner("Evaluating your answer..."):
                speech = None
                if audio is not None and not text.strip():
                    text, speech = transcribe(audio)
                result = evaluate_answer(q, text, speech)
                db.save_answer(q["id"], text, "voice" if speech else "text", result)
            st.rerun()
        if c2.button("Skip"):
            db.save_answer(q["id"], "", "text", evaluate_answer(q, ""))
            st.rerun()
        if c3.button("End interview"):
            finish_interview(session)
    else:
        show_feedback(q)
        if i + 1 < len(questions):
            if st.button("Next question →", type="primary"):
                state.q_index += 1
                st.rerun()
        elif st.button("Finish & see report →", type="primary"):
            finish_interview(session)


# ---------------------------------------------------------------- results
def results_page():
    sessions = db.list_sessions(state.user["id"], completed_only=True)[::-1]
    if not sessions:
        return st.info("Finish a mock interview to see your report here.")
    ids = [s["id"] for s in sessions]
    label = {s["id"]: f"{s['started_at']:%d %b %Y %H:%M} · {s['job_role']} · {s['overall_score']:.0f}/100"
             for s in sessions}
    chosen = st.selectbox("Interview", ids, index=ids.index(state.report_id) if state.report_id in ids else 0,
                          format_func=label.get)
    s = next(s for s in sessions if s["id"] == chosen)
    summ = s["summary"]

    st.title("📄 Interview report")
    left, right = st.columns(2)
    gauge = go.Figure(go.Indicator(mode="gauge+number", value=summ["overall_score"],
                                   title={"text": summ["grade"]},
                                   gauge={"axis": {"range": [0, 100]}, "bar": {"color": color(summ["overall_score"])}}))
    left.plotly_chart(gauge.update_layout(height=260, margin=dict(t=50, b=0)), use_container_width=True)
    dims = {k.title(): v for k, v in summ["dimension_scores"].items() if v is not None}
    radar = px.line_polar(r=list(dims.values()), theta=list(dims), line_close=True, range_r=[0, 100])
    right.plotly_chart(radar.update_traces(fill="toself").update_layout(height=280), use_container_width=True)

    st.subheader("Feedback")
    st.write(summ["overall_feedback"])
    c1, c2 = st.columns(2)
    c1.markdown("**⚠️ Weak areas**\n\n" + ("\n".join(f"- {w}" for w in summ["weak_areas"]) or "None below 60 - well done!"))
    c2.markdown("**📚 Practise next**\n\n" + "\n".join(f"- {r}" for r in summ["recommendations"]))

    st.subheader("Question by question")
    for q in s["questions"]:
        if q["score"] is None:
            continue
        with st.expander(f"Q{q['position']}. {q['question']} — {q['score']:.0f}/100"):
            show_feedback(q)


# ---------------------------------------------------------------- dashboard
def dashboard_page():
    sessions = db.list_sessions(state.user["id"], completed_only=True)
    if not sessions:
        return st.info("Complete an interview to unlock the dashboard.")
    st.title("📈 Progress dashboard")
    scores = [s["overall_score"] for s in sessions]
    k = st.columns(4)
    k[0].metric("Interviews", len(sessions))
    k[1].metric("Average score", f"{sum(scores) / len(scores):.1f}")
    k[2].metric("Best score", f"{max(scores):.1f}")
    k[3].metric("Change since first", f"{scores[-1] - scores[0]:+.1f}")

    history = pd.DataFrame([{"Interview": n, "Date": f"{s['completed_at']:%d %b %H:%M}", "Role": s["job_role"],
                             "Type": s["interview_type"], "Overall": s["overall_score"],
                             "Technical": s["technical_score"], "Communication": s["communication_score"]}
                            for n, s in enumerate(sessions, start=1)])
    trend = px.line(history, x="Interview", y=["Overall", "Technical", "Communication"], markers=True,
                    range_y=[0, 100], title="Scores over time")
    st.plotly_chart(trend.add_hline(y=60, line_dash="dot").update_xaxes(dtick=1), use_container_width=True)

    answers = [q for s in sessions for q in s["questions"] if q["score"] is not None]
    topics = (pd.DataFrame(answers).groupby("topic")["score"].mean().round(1).sort_values().reset_index())
    bars = px.bar(topics, x="score", y="topic", orientation="h", range_x=[0, 100], title="Average score by topic",
                  color="score", range_color=[0, 100], color_continuous_scale=["#DC2626", "#D97706", "#2563EB", "#16A34A"])
    st.plotly_chart(bars.add_vline(x=60, line_dash="dot"), use_container_width=True)
    st.dataframe(history, hide_index=True, use_container_width=True)


{PAGES[0]: interview_page, PAGES[1]: results_page, PAGES[2]: dashboard_page}[state.get("page", PAGES[0])]()
