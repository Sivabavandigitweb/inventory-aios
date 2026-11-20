from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import get_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata stays empty until approved SQLAlchemy models are introduced.
target_metadata = Base.metadata


def configured_database_url() -> str:
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError(
            "INVENTORY_DATABASE_URL must be configured before running Alembic. "
            "Use only the dedicated Inventory AIOS development database."
        )
    return database_url


def run_migrations_offline() -> None:
    url = configured_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # The URL is supplied from application settings in memory; credentials are not
    # stored in alembic.ini or printed by this module.
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = configured_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        hide_parameters=True,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()