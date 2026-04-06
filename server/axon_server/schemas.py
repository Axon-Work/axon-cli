import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# --- Auth ---

class UserOut(BaseModel):
    id: uuid.UUID
    address: str
    balance: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Tasks ---

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    eval_type: str = Field(pattern=r"^(exact_match|numeric|contains|regex|code_output|llm_judge)$")
    eval_config: dict[str, Any]
    direction: str = Field(default="maximize", pattern=r"^(maximize|minimize)$")
    completion_threshold: float
    task_burn: int = Field(gt=0)  # OS coins to burn for this task


class TaskOut(BaseModel):
    id: uuid.UUID
    publisher_id: uuid.UUID
    title: str
    description: str
    eval_type: str
    eval_config: dict[str, Any]
    direction: str
    completion_threshold: float
    task_burn: int
    pool_balance: int
    baseline_score: float | None
    status: str
    best_score: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskListOut(BaseModel):
    id: uuid.UUID
    title: str
    eval_type: str
    direction: str
    status: str
    best_score: float | None
    task_burn: int
    pool_balance: int
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Submissions ---

class SubmissionCreate(BaseModel):
    answer: str = Field(min_length=1)
    thinking: str = Field(min_length=1)
    llm_model_used: str | None = None
    parent_submission_id: uuid.UUID | None = None


class SubmissionOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    miner_id: uuid.UUID
    score: float | None
    is_improvement: bool | None
    is_completion: bool
    reward_earned: int
    eval_status: str
    eval_error: str | None
    eval_details: dict | None
    llm_model_used: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SubmissionDetail(SubmissionOut):
    answer: str
    thinking: str
    parent_submission_id: uuid.UUID | None


class BestSubmissionOut(BaseModel):
    score: float | None
    submission_id: uuid.UUID | None
    miner_address: str | None


# --- Transactions ---

class TransactionOut(BaseModel):
    id: uuid.UUID
    amount: int
    type: str
    reference_id: uuid.UUID | None
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
