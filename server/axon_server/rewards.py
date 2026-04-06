"""AXN tokenomics — pure staking/pool model (no mint).

All rewards come from the task pool (Publisher's staked $AXN).
No system minting. $AXN total supply is fixed at 333,333,333.
"""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from axon_server.models import Submission, Task, Transaction, User

# --- Constants ---
MIN_IMPROVEMENT_RATIO = 0.001  # 0.1% minimum to count
MAX_IMPROVEMENT_RATIO = 1.0    # cap at 100%


def is_better(new_score: float, old_score: float | None, direction: str) -> bool:
    if old_score is None:
        return True
    if direction == "maximize":
        return new_score > old_score
    return new_score < old_score


def meets_threshold(score: float, threshold: float, direction: str) -> bool:
    if direction == "maximize":
        return score >= threshold
    return score <= threshold


def compute_improvement_ratio(
    old_score: float,
    new_score: float,
    baseline: float,
    threshold: float,
    direction: str,
) -> float:
    score_range = abs(threshold - baseline)
    if score_range < 1e-12:
        return 0.0

    delta = abs(new_score - old_score)

    if direction == "maximize":
        progress = (old_score - baseline) / score_range
    else:
        progress = (baseline - old_score) / score_range

    progress = max(0.0, min(progress, 0.999))
    difficulty_bonus = 1.0 / (1.0 - progress)
    ratio = (delta / score_range) * difficulty_bonus

    return min(ratio, MAX_IMPROVEMENT_RATIO)


async def process_reward(
    db: AsyncSession,
    task: Task,
    submission: Submission,
    miner: User,
) -> tuple[int, bool]:
    """All rewards come from task pool. No minting."""
    if submission.score is None:
        return 0, False

    # First submission sets baseline
    if task.baseline_score is None:
        task.baseline_score = submission.score
        task.best_score = submission.score
        task.best_submission_id = submission.id
        submission.is_improvement = True
        submission.reward_earned = 0
        return 0, False

    if not is_better(submission.score, task.best_score, task.direction):
        submission.is_improvement = False
        submission.reward_earned = 0
        return 0, False

    submission.is_improvement = True

    ratio = compute_improvement_ratio(
        old_score=task.best_score,
        new_score=submission.score,
        baseline=task.baseline_score,
        threshold=task.completion_threshold,
        direction=task.direction,
    )

    if ratio < MIN_IMPROVEMENT_RATIO:
        submission.is_improvement = False
        submission.reward_earned = 0
        return 0, False

    # Pool payout — only source of reward
    pool_payout = int(task.pool_balance * ratio)
    pool_payout = min(pool_payout, task.pool_balance)
    total_reward = pool_payout

    if pool_payout > 0:
        task.pool_balance -= pool_payout
        miner.balance += pool_payout
        db.add(Transaction(
            user_id=miner.id,
            amount=pool_payout,
            type="pool_reward",
            reference_id=submission.id,
            description=f"Reward for improving: {task.title}",
        ))

    task.best_score = submission.score
    task.best_submission_id = submission.id
    submission.reward_earned = total_reward

    # Completion check
    is_completion = False
    if task.status != "completed" and meets_threshold(submission.score, task.completion_threshold, task.direction):
        completion_pool = task.pool_balance
        if completion_pool > 0:
            task.pool_balance = 0
            miner.balance += completion_pool
            total_reward += completion_pool
            db.add(Transaction(
                user_id=miner.id,
                amount=completion_pool,
                type="completion_reward",
                reference_id=submission.id,
                description=f"Completed task: {task.title}",
            ))

        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        submission.is_completion = True
        submission.reward_earned = total_reward
        is_completion = True

    if task.pool_balance <= 0 and task.status == "open":
        task.status = "paused"

    return total_reward, is_completion
