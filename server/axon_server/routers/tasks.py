import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from axon_server.auth import get_current_user
from axon_server.database import get_db
from axon_server.eval.engine import list_eval_types
from axon_server.models import Task, Transaction, User
from axon_server.schemas import TaskCreate, TaskListOut, TaskOut

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(body: TaskCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user.id).with_for_update())
    user = result.scalar_one()
    if user.balance < body.task_burn:
        raise HTTPException(status_code=400, detail=f"Insufficient balance. Need {body.task_burn} $AXN, have {user.balance}")

    # Pool = publisher's staked $AXN (no system match — $AXN cannot be minted)
    task = Task(
        publisher_id=user.id,
        title=body.title,
        description=body.description,
        eval_type=body.eval_type,
        eval_config=body.eval_config,
        direction=body.direction,
        completion_threshold=body.completion_threshold,
        task_burn=body.task_burn,
        pool_balance=body.task_burn,  # pool = exactly what publisher stakes
    )

    user.balance -= body.task_burn
    db.add(task)
    await db.flush()
    db.add(Transaction(
        user_id=user.id,
        amount=-body.task_burn,
        type="task_stake",
        reference_id=task.id,
        description=f"Staked for task: {body.title}",
    ))

    await db.commit()
    await db.refresh(task)
    return task


@router.get("", response_model=list[TaskListOut])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    task_status: str = "open",
    limit: int = 50,
    offset: int = 0,
):
    query = select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)
    if task_status != "all":
        query = query.where(Task.status == task_status)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/eval-types")
async def get_eval_types():
    return list_eval_types()


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def close_task(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Task).where(Task.id == task_id).with_for_update())
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.publisher_id != user.id:
        raise HTTPException(status_code=403, detail="Not your task")
    if task.status == "closed":
        raise HTTPException(status_code=400, detail="Task already closed")

    # Refund remaining pool back to publisher
    refund = task.pool_balance
    if refund > 0:
        result = await db.execute(select(User).where(User.id == user.id).with_for_update())
        publisher = result.scalar_one()
        publisher.balance += refund
        task.pool_balance = 0
        db.add(Transaction(
            user_id=user.id,
            amount=refund,
            type="task_refund",
            reference_id=task.id,
            description=f"Refund from closed task: {task.title}",
        ))
    task.status = "closed"
    await db.commit()
    await db.refresh(task)
    return task
