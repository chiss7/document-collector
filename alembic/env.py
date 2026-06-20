import re
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from app.db.base import Base
from app.core.config import settings

# Import all models so Alembic can detect them for autogenerate
import app.models.publication  # noqa: F401
import app.models.subject  # noqa: F401
import app.models.contributor  # noqa: F401
import app.models.excluded_publication  # noqa: F401
import app.models.social_media_record  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _make_sync_url(async_url: str) -> str:
    """Convert postgresql+asyncpg:// → postgresql+psycopg:// for sync migrations."""
    return re.sub(r"postgresql\+asyncpg://", "postgresql+psycopg://", async_url)


def run_migrations_offline() -> None:
    url = _make_sync_url(settings.DATABASE_URL)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    sync_url = _make_sync_url(settings.DATABASE_URL)
    config.set_main_option("sqlalchemy.url", sync_url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
