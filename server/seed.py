"""Seed script — create test users and tasks for local development."""
import asyncio
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from axon_server.database import engine, async_session
from axon_server.models import Base, User, Task, Transaction

# Test wallets (deterministic addresses for dev convenience)
TEST_USERS = [
    {
        "address": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",  # Hardhat #0
        "balance": 10_000,
    },
    {
        "address": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",  # Hardhat #1
        "balance": 5_000,
    },
    {
        "address": "0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc",  # Hardhat #2
        "balance": 1_000,
    },
]


async def seed():
    # Recreate all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("ψ Tables recreated")

    async with async_session() as db:
        # Create users
        users = []
        for u in TEST_USERS:
            user = User(
                address=u["address"],
                nonce=secrets.token_hex(32),
                balance=u["balance"],
            )
            db.add(user)
            users.append(user)
        await db.flush()

        # Record initial balance as transactions
        for user, u in zip(users, TEST_USERS):
            db.add(Transaction(
                user_id=user.id,
                amount=u["balance"],
                type="seed",
                description="Dev seed funding",
            ))

        publisher = users[0]

        # Text compression task
        task_burn = 2_000
        publisher.balance -= task_burn
        task = Task(
            publisher_id=publisher.id,
            title="Compress this paragraph",
            description=(
                "Compress the following text to under 50 words while preserving all key facts:\n\n"
                "The Earth orbits the Sun at an average distance of about 93 million miles "
                "(150 million kilometers). This journey takes approximately 365.25 days to "
                "complete, which is why we have a leap year every four years. The Earth's "
                "orbital speed is about 67,000 miles per hour (107,000 km/h). The orbit is "
                "not a perfect circle but an ellipse, with the closest point (perihelion) "
                "occurring in early January and the farthest point (aphelion) in early July."
            ),
            eval_type="contains",
            eval_config={
                "keywords": ["93 million", "365.25", "ellipse", "perihelion", "aphelion"],
                "word_limit": 50,
            },
            direction="maximize",
            completion_threshold=1.0,
            task_burn=task_burn,
            pool_balance=task_burn,
        )
        db.add(task)

        db.add(Transaction(
            user_id=publisher.id,
            amount=-task_burn,
            type="task_burn",
            description=f"Burn for task: {task.title}",
        ))

        await db.commit()

        print(f"ψ Created {len(users)} users")
        for user, u in zip(users, TEST_USERS):
            print(f"  {u['address'][:10]}... — {user.balance} $AXN")
        print(f"ψ Created task: '{task.title}' (pool: {task.pool_balance} $AXN)")
        print("\nDone! Start server with: uvicorn axon_server.main:app --port 8000")


if __name__ == "__main__":
    asyncio.run(seed())
