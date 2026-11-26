"""Database tables (MySQL or SQLite) and the queries the app needs."""
from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from core.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
Session = sessionmaker(bind=engine, expire_on_commit=False)


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(default=now)


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_role: Mapped[str] = mapped_column(String(80))
    skill_level: Mapped[str] = mapped_column(String(20))
    interview_type: Mapped[str] = mapped_column(String(20))   # technical | hr | mixed
    answer_mode: Mapped[str] = mapped_column(String(10))      # text | voice
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    overall_score: Mapped[float | None]
    technical_score: Mapped[float | None]
    communication_score: Mapped[float | None]
    summary: Mapped[dict | None] = mapped_column(JSON)       # grade, weak areas, recommendations
    started_at: Mapped[datetime] = mapped_column(default=now)
    completed_at: Mapped[datetime | None]
    questions: Mapped[list["SessionQuestion"]] = relationship(
        cascade="all, delete-orphan", order_by="SessionQuestion.position")


class SessionQuestion(Base):
    __tablename__ = "session_questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True)
    position: Mapped[int]
    question_key: Mapped[str] = mapped_column(String(40))
    question_type: Mapped[str] = mapped_column(String(20))    # technical | hr
    topic: Mapped[str] = mapped_column(String(80))
    question: Mapped[str] = mapped_column(Text)
    ideal_answer: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list] = mapped_column(JSON)
    answer_text: Mapped[str | None] = mapped_column(Text)
    answer_mode: Mapped[str | None] = mapped_column(String(10))
    relevance: Mapped[float | None]
    completeness: Mapped[float | None]
    correctness: Mapped[float | None]
    communication: Mapped[float | None]
    score: Mapped[float | None]
    speech_metrics: Mapped[dict | None] = mapped_column(JSON)
    feedback: Mapped[dict | None] = mapped_column(JSON)
    answered_at: Mapped[datetime | None]


def init_db():
    Base.metadata.create_all(engine)


def _row(obj) -> dict:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _session_dict(s: InterviewSession) -> dict:
    return {**_row(s), "questions": [_row(q) for q in s.questions]}


def get_or_create_user(username: str) -> int:
    with Session() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(username=username)
            db.add(user)
            db.commit()
        return user.id


def create_session(user_id, role, level, interview_type, answer_mode, questions) -> int:
    with Session() as db:
        s = InterviewSession(user_id=user_id, job_role=role, skill_level=level,
                             interview_type=interview_type, answer_mode=answer_mode)
        s.questions = [
            SessionQuestion(position=i, question_key=q["id"], question_type=q["type"], topic=q["topic"],
                            question=q["question"], ideal_answer=q["ideal_answer"], keywords=q["keywords"])
            for i, q in enumerate(questions, start=1)
        ]
        db.add(s)
        db.commit()
        return s.id


def save_answer(question_id: int, answer: str, mode: str, result: dict):
    with Session() as db:
        q = db.get(SessionQuestion, question_id)
        q.answer_text, q.answer_mode, q.answered_at = answer, mode, now()
        for key in ("relevance", "completeness", "correctness", "communication", "score",
                    "speech_metrics", "feedback"):
            setattr(q, key, result.get(key))
        db.commit()


def complete_session(session_id: int, summary: dict):
    with Session() as db:
        s = db.get(InterviewSession, session_id)
        s.summary, s.status, s.completed_at = summary, "completed", now()
        s.overall_score = summary["overall_score"]
        s.technical_score = summary["technical_score"]
        s.communication_score = summary["communication_score"]
        db.commit()


def get_session(session_id: int) -> dict:
    with Session() as db:
        return _session_dict(db.get(InterviewSession, session_id))


def list_sessions(user_id: int, completed_only: bool = False) -> list[dict]:
    """A user's interviews, oldest first."""
    with Session() as db:
        query = select(InterviewSession).where(InterviewSession.user_id == user_id)
        if completed_only:
            query = query.where(InterviewSession.status == "completed")
        return [_session_dict(s) for s in db.scalars(query.order_by(InterviewSession.started_at))]
