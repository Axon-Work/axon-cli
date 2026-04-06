"""Wallet-based authentication — no passwords, just ETH signatures."""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from eth_account.messages import encode_defunct
from eth_account import Account
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from axon_server.config import settings
from axon_server.database import get_db
from axon_server.models import User

security = HTTPBearer()


def generate_nonce() -> str:
    return secrets.token_hex(32)


def verify_signature(address: str, nonce: str, signature: str) -> bool:
    """Verify that signature was produced by the claimed address."""
    try:
        message = encode_defunct(text=f"Sign in to Axon: {nonce}")
        recovered = Account.recover_message(message, signature=signature)
        return recovered.lower() == address.lower()
    except Exception:
        return False


def create_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
