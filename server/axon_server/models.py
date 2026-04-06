import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey,
    Index, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    address: Mapped[str] = mapped_column(String(42), unique=True, nullable=False)  # ETH address 0x...
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)  # random nonce for signature auth
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_users_balance_nonneg"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    publisher_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    eval_type: Mapped[str] = mapped_column(String(20), nullable=False)
    eval_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False, default="maximize")
    completion_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    # Tokenomics
    task_burn: Mapped[int] = mapped_column(BigInteger, nullable=False)  # OS burned by publisher
    pool_balance: Mapped[int] = mapped_column(BigInteger, nullable=False)  # burn + match, decreases as miners earn
    baseline_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # first submission's score
    # State
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    best_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_submission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    publisher = relationship("User", lazy="selectin")

    __table_args__ = (
        Index("idx_tasks_status", "status"),
    )


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    miner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    parent_submission_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("submissions.id"), nullable=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    answer_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # sha256 for dedup
    thinking: Mapped[str] = mapped_column(Text, nullable=False)
    llm_model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_improvement: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_completion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reward_earned: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    eval_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    eval_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    eval_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # stdout, stderr, parsed values
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    miner = relationship("User", lazy="selectin")

    __table_args__ = (
        Index("idx_submissions_task", "task_id", "created_at"),
        Index("idx_submissions_miner", "miner_id"),
        Index("idx_submissions_answer_hash", "task_id", "answer_hash"),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (
        Index("idx_transactions_user", "user_id", "created_at"),
    )
