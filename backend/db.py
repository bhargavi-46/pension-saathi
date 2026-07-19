"""SQLite persistence layer (SQLAlchemy 2.0)."""

import json
import os
from datetime import datetime, timezone

from sqlalchemy import (
    Integer,
    String,
    Text,
    create_engine,
    text,
    ForeignKey,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "pension_saathi.db")

# check_same_thread=False + a single engine keeps SQLite happy on Render's
# single-worker free tier (see playbook troubleshooting notes).
engine = create_engine(
    f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Widow(Base):
    __tablename__ = "widows"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    district: Mapped[str | None] = mapped_column(String, nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    children_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_income: Mapped[int | None] = mapped_column(Integer, nullable=True)
    husband_occupation: Mapped[str | None] = mapped_column(String, nullable=True)
    husband_death_date: Mapped[str | None] = mapped_column(String, nullable=True)
    onboarding_step: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String, default="en-IN")
    # Information-gap fields: facts a scheme depends on that the 5 intake
    # questions never asked. None = unknown, 1 = yes, 0 = no.
    has_daughter_under_10: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Which clarifying question the agent is currently waiting on (e.g.
    # "daughter_under_10") — the conversation is halted until she answers.
    pending_question: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "state": self.state,
            "district": self.district,
            "age": self.age,
            "children_count": self.children_count,
            "monthly_income": self.monthly_income,
            "husband_occupation": self.husband_occupation,
            "husband_death_date": self.husband_death_date,
            "onboarding_step": self.onboarding_step,
            "language": self.language,
            "has_daughter_under_10": self.has_daughter_under_10,
            "pending_question": self.pending_question,
            "created_at": self.created_at,
        }


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    widow_id: Mapped[str] = mapped_column(String, ForeignKey("widows.id"), index=True)
    role: Mapped[str] = mapped_column(String)  # "user" | "agent"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "widow_id": self.widow_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at,
        }


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    widow_id: Mapped[str] = mapped_column(String, ForeignKey("widows.id"), index=True)
    scheme_id: Mapped[str] = mapped_column(String)
    scheme_name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="discovered")
    # discovered -> filed -> tracking -> received | rejected
    tracking_id: Mapped[str | None] = mapped_column(String, nullable=True)
    filed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_annual_value: Mapped[int] = mapped_column(Integer, default=0)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "widow_id": self.widow_id,
            "scheme_id": self.scheme_id,
            "scheme_name": self.scheme_name,
            "status": self.status,
            "tracking_id": self.tracking_id,
            "filed_at": self.filed_at,
            "notes": self.notes,
            "estimated_annual_value": self.estimated_annual_value,
            "reasoning": self.reasoning,
            "created_at": self.created_at,
        }


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    widow_id: Mapped[str] = mapped_column(String, ForeignKey("widows.id"), index=True)
    doc_type: Mapped[str] = mapped_column(String)  # death_certificate | aadhaar | bank_passbook
    storage_path: Mapped[str | None] = mapped_column(String, nullable=True)
    extracted_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    uploaded_at: Mapped[str] = mapped_column(String, default=utcnow)

    def to_dict(self) -> dict:
        # extracted_data is AES-GCM-encrypted at rest by document_agent when
        # the crypto module is enabled. Decrypt transparently for callers.
        from services import crypto as _crypto  # local import: avoids startup cycle

        blob = self.extracted_data
        if blob:
            if _crypto.is_encrypted(blob):
                blob = _crypto.decrypt(blob)
            try:
                extracted = json.loads(blob) if blob else None
            except json.JSONDecodeError:
                extracted = None
        else:
            extracted = None
        return {
            "id": self.id,
            "widow_id": self.widow_id,
            "doc_type": self.doc_type,
            "storage_path": self.storage_path,
            "extracted_data": extracted,
            "uploaded_at": self.uploaded_at,
        }


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    widow_id: Mapped[str] = mapped_column(String, index=True)
    agent_name: Mapped[str] = mapped_column(String)  # discovery | document | filing | tracking | voice
    action: Mapped[str] = mapped_column(Text)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, default=utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "widow_id": self.widow_id,
            "agent_name": self.agent_name,
            "action": self.action,
            "details": json.loads(self.details_json) if self.details_json else None,
            "created_at": self.created_at,
        }


def init_db() -> None:
    Base.metadata.create_all(engine)
    # create_all never ALTERs existing tables — add columns introduced after
    # the first release so an old pension_saathi.db keeps working.
    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(widows)"))}
        if "has_daughter_under_10" not in cols:
            conn.execute(text("ALTER TABLE widows ADD COLUMN has_daughter_under_10 INTEGER"))
        if "pending_question" not in cols:
            conn.execute(text("ALTER TABLE widows ADD COLUMN pending_question VARCHAR"))
        conn.commit()


def uploaded_doc_types(widow_id: str) -> set[str]:
    with SessionLocal() as db:
        return {d.doc_type for d in db.query(Document).filter_by(widow_id=widow_id).all()}


def has_payment_docs(widow_id: str) -> bool:
    """DBT can only pay out with identity + account proof: Aadhaar AND bank
    passbook must be on file before any claim may reach 'received'."""
    with SessionLocal() as db:
        types = {d.doc_type for d in db.query(Document).filter_by(widow_id=widow_id).all()}
    return "aadhaar" in types and "bank_passbook" in types


def log_action(widow_id: str, agent_name: str, action: str, details: dict | None = None) -> dict:
    """Insert an agent action; the SSE stream picks it up by polling this table."""
    with SessionLocal() as db:
        row = AgentAction(
            widow_id=widow_id,
            agent_name=agent_name,
            action=action,
            details_json=json.dumps(details, ensure_ascii=False) if details else None,
        )
        db.add(row)
        db.commit()
        return row.to_dict()
