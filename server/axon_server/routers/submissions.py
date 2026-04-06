import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from axon_server.auth import get_current_user
from axon_server.database import get_db
from axon_server.eval.engine import evaluate
from axon_server.models import Submission, Task, Transaction, User
from axon_server.rewards import process_reward
from axon_server.schemas import BestSubmissionOut, SubmissionCreate, SubmissionDetail, SubmissionOut
from axon_server.ws import broadcast_improvement

router = APIRouter(prefix="/api/tasks/{task_id}/submissions", tags=["submissions"])

# --- Security constants ---
SUBMIT_COOLDOWN_SECONDS = 1        # Min seconds between submissions (per task)
MAX_CONCURRENT_EVALS = 1           # Max simultaneous evals per user
MAX_GPU_SUBMISSIONS_PER_DAY = 50   # Daily GPU submission cap per user
CONSECUTIVE_FAIL_LIMIT = 5         # After N consecutive fails, double cooldown
GPU_STAKE_AMOUNT = 10              # OS coins staked per GPU submission (refunded on success)
GLOBAL_RATE_WINDOW = 60            # Sliding window in seconds for global per-user limit
GLOBAL_RATE_MAX = 30               # Max submissions across ALL tasks per window

# Track in-flight evals per user (in-memory, resets on restart)
_active_evals: dict[str, int] = {}


def _is_gpu_task(task: Task) -> bool:
    """Check if task requires GPU execution."""
    return task.eval_config.get("gpu") is not None


@router.post("", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED)
async def create_submission(
    task_id: uuid.UUID,
    body: SubmissionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # --- Phase 1: Validation (no locks) ---
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in ("open", "completed"):
        raise HTTPException(status_code=400, detail=f"Task is {task.status}, not accepting submissions")

    is_gpu = _is_gpu_task(task)
    user_key = str(user.id)

    # 1. Concurrent eval limit
    active = _active_evals.get(user_key, 0)
    if active >= MAX_CONCURRENT_EVALS:
        raise HTTPException(status_code=429, detail="You already have an eval running. Wait for it to finish.")

    # 2. Global per-user rate limit (across all tasks)
    global_cutoff = datetime.now(timezone.utc) - timedelta(seconds=GLOBAL_RATE_WINDOW)
    global_recent = await db.execute(
        select(func.count()).select_from(Submission).where(
            Submission.miner_id == user.id,
            Submission.created_at > global_cutoff,
        )
    )
    if global_recent.scalar() >= GLOBAL_RATE_MAX:
        raise HTTPException(status_code=429, detail=f"Too many submissions. Max {GLOBAL_RATE_MAX} per {GLOBAL_RATE_WINDOW}s across all tasks.")

    # 3. Per-task rate limit (with failure penalty)
    consecutive_fails = await _count_consecutive_fails(db, task_id, user.id)
    cooldown = SUBMIT_COOLDOWN_SECONDS * (2 ** min(consecutive_fails // CONSECUTIVE_FAIL_LIMIT, 4))
    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown)
    recent = await db.execute(
        select(func.count()).select_from(Submission).where(
            Submission.task_id == task_id,
            Submission.miner_id == user.id,
            Submission.created_at > cooldown_cutoff,
        )
    )
    if recent.scalar() > 0:
        raise HTTPException(status_code=429, detail=f"Too fast. Wait {cooldown}s between submissions.")

    # 4. Answer dedup
    answer_hash = hashlib.sha256(body.answer.encode()).hexdigest()
    dup = await db.execute(
        select(Submission.id).where(
            Submission.task_id == task_id,
            Submission.answer_hash == answer_hash,
        ).limit(1)
    )
    if dup.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Duplicate answer already submitted for this task")

    # 5. GPU-specific checks
    if is_gpu:
        # Daily GPU submission limit
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        gpu_today = await db.execute(
            select(func.count()).select_from(Submission).where(
                Submission.miner_id == user.id,
                Submission.created_at > day_start,
            )
        )
        if gpu_today.scalar() >= MAX_GPU_SUBMISSIONS_PER_DAY:
            raise HTTPException(status_code=429, detail=f"Daily GPU submission limit reached ({MAX_GPU_SUBMISSIONS_PER_DAY}/day)")

        # GPU stake: lock OS coins (refunded on success)
        result = await db.execute(select(User).where(User.id == user.id).with_for_update())
        staking_user = result.scalar_one()
        if staking_user.balance < GPU_STAKE_AMOUNT:
            raise HTTPException(status_code=400, detail=f"Need {GPU_STAKE_AMOUNT} OS stake for GPU submission, have {staking_user.balance}")
        staking_user.balance -= GPU_STAKE_AMOUNT
        db.add(Transaction(
            user_id=user.id, amount=-GPU_STAKE_AMOUNT, type="gpu_stake",
            description=f"GPU eval stake for task: {task.title[:50]}",
        ))
        await db.flush()

    # --- Phase 2: Eval OUTSIDE lock (may take minutes for GPU tasks) ---
    _active_evals[user_key] = _active_evals.get(user_key, 0) + 1
    try:
        eval_result = await evaluate(body.answer, task.eval_type, task.eval_config)
    finally:
        _active_evals[user_key] = max(0, _active_evals.get(user_key, 1) - 1)

    # --- Phase 3: Lock task + miner, compare score, award reward (fast) ---
    result = await db.execute(select(Task).where(Task.id == task_id).with_for_update())
    task = result.scalar_one()
    result = await db.execute(select(User).where(User.id == user.id).with_for_update())
    miner = result.scalar_one()

    if task.status not in ("open", "completed"):
        raise HTTPException(status_code=400, detail=f"Task is now {task.status}")

    submission = Submission(
        task_id=task_id,
        miner_id=user.id,
        answer=body.answer,
        answer_hash=answer_hash,
        thinking=body.thinking,
        llm_model_used=body.llm_model_used,
        parent_submission_id=body.parent_submission_id,
    )
    db.add(submission)

    submission.eval_details = eval_result.details

    eval_success = False
    if eval_result.error:
        submission.eval_status = "failed"
        submission.eval_error = eval_result.error
        submission.score = None
        submission.is_improvement = False
    else:
        submission.eval_status = "completed"
        submission.score = eval_result.score
        eval_success = True
        await process_reward(db, task, submission, miner)

    # GPU stake settlement
    if is_gpu:
        if eval_success:
            # Refund stake on successful eval
            miner.balance += GPU_STAKE_AMOUNT
            db.add(Transaction(
                user_id=user.id, amount=GPU_STAKE_AMOUNT, type="gpu_stake_refund",
                reference_id=submission.id,
                description="GPU eval stake refunded (eval success)",
            ))
        # If failed, stake is kept (already deducted)

    await db.commit()
    await db.refresh(submission)

    # Broadcast improvement
    if submission.is_improvement and submission.score is not None:
        await broadcast_improvement(str(task_id), {
            "event": "improvement",
            "task_id": str(task_id),
            "score": submission.score,
            "miner": miner.address,
            "reward": submission.reward_earned,
            "is_completion": submission.is_completion,
        })

    return submission


async def _count_consecutive_fails(db: AsyncSession, task_id: uuid.UUID, miner_id: uuid.UUID) -> int:
    """Count consecutive recent failures for this miner on this task."""
    result = await db.execute(
        select(Submission.eval_status)
        .where(Submission.task_id == task_id, Submission.miner_id == miner_id)
        .order_by(Submission.created_at.desc())
        .limit(10)
    )
    count = 0
    for (eval_status,) in result:
        if eval_status == "failed":
            count += 1
        else:
            break
    return count


@router.get("", response_model=list[SubmissionOut])
async def list_submissions(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    result = await db.execute(
        select(Submission)
        .where(Submission.task_id == task_id)
        .order_by(Submission.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.get("/best", response_model=BestSubmissionOut)
async def get_best(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    miner_address = None
    if task.best_submission_id:
        sub_result = await db.execute(
            select(Submission).where(Submission.id == task.best_submission_id)
        )
        sub = sub_result.scalar_one_or_none()
        if sub:
            miner_address = sub.miner.address

    return BestSubmissionOut(
        score=task.best_score,
        submission_id=task.best_submission_id,
        miner_address=miner_address,
    )


leaderboard_router = APIRouter(prefix="/api/tasks/{task_id}/leaderboard", tags=["leaderboard"])


@leaderboard_router.get("", response_model=list[SubmissionOut])
async def leaderboard(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    order = Submission.score.desc() if task.direction == "maximize" else Submission.score.asc()
    result = await db.execute(
        select(Submission)
        .where(Submission.task_id == task_id, Submission.score.isnot(None))
        .order_by(order)
        .limit(limit)
    )
    return result.scalars().all()
