from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from axon_server.database import engine, get_db
from axon_server.models import Base, User, Task, Submission
from axon_server.routers.submissions import leaderboard_router, router as submissions_router
from axon_server.routers.tasks import router as tasks_router
from axon_server.routers.users import router as users_router, transactions_router
from axon_server.ws import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (for dev; use Alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Axon",
    description="Autonomous research bounty platform powered by LLM agents",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(users_router)
app.include_router(transactions_router)
app.include_router(tasks_router)
app.include_router(submissions_router)
app.include_router(leaderboard_router)
app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/stats")
async def platform_stats(db: AsyncSession = Depends(get_db)):
    miners = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    tasks_open = (await db.execute(select(func.count()).select_from(Task).where(Task.status == "open"))).scalar() or 0
    tasks_total = (await db.execute(select(func.count()).select_from(Task))).scalar() or 0
    submissions = (await db.execute(select(func.count()).select_from(Submission))).scalar() or 0
    return {"miners": miners, "tasks_open": tasks_open, "tasks_total": tasks_total, "submissions": submissions}
