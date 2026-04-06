"""Wallet-based auth endpoints: nonce → sign → verify → JWT."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from axon_server.auth import create_token, generate_nonce, get_current_user, verify_signature
from axon_server.database import get_db
from axon_server.models import Transaction, User
from axon_server.schemas import TokenOut, TransactionOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


class NonceResponse(BaseModel):
    nonce: str
    message: str  # the message to sign


class VerifyRequest(BaseModel):
    address: str
    signature: str


# --- Nonce: get a challenge to sign ---

@router.get("/nonce")
async def get_nonce(address: str, db: AsyncSession = Depends(get_db)):
    """Get a nonce for the given address. Creates user if first time."""
    address = address.lower()
    result = await db.execute(select(User).where(User.address == address))
    user = result.scalar_one_or_none()

    if user is None:
        # Auto-create user on first interaction
        nonce = generate_nonce()
        user = User(address=address, nonce=nonce, balance=1000)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # Rotate nonce
        nonce = generate_nonce()
        user.nonce = nonce
        await db.commit()

    return NonceResponse(
        nonce=user.nonce,
        message=f"Sign in to Axon: {user.nonce}",
    )


# --- Verify: check signature, return JWT ---

@router.post("/verify", response_model=TokenOut)
async def verify(body: VerifyRequest, db: AsyncSession = Depends(get_db)):
    """Verify wallet signature and return JWT."""
    address = body.address.lower()
    result = await db.execute(select(User).where(User.address == address))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="Request nonce first: GET /api/auth/nonce?address=...")

    if not verify_signature(address, user.nonce, body.signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Rotate nonce after successful verify (prevents replay)
    user.nonce = generate_nonce()
    await db.commit()

    return TokenOut(access_token=create_token(user.id))


# --- Me: get current user profile ---

@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


# --- Transactions ---

transactions_router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@transactions_router.get("", response_model=list[TransactionOut])
async def list_transactions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()
