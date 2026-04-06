from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from axon_server.config import settings
from axon_server.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Sync URL for Alembic (asyncpg -> plain postgresql)
sync_url = settings.database_url.replace("+asyncpg", "")


def run_migrations_offline() -> None:
    context.configure(url=sync_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        {"sqlalchemy.url": sync_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
