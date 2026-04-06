import getpass

from pydantic_settings import BaseSettings

_user = getpass.getuser()


class Settings(BaseSettings):
    database_url: str = f"postgresql+asyncpg://{_user}@localhost:5432/axon"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days
    starter_coins: int = 0  # No free coins — buy $AXN with USDC

    model_config = {"env_prefix": "AXON_"}


settings = Settings()
