from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text

from alembic import context
from app.core.config import get_migration_settings
from app.core.migration_security import require_migration_url, verify_migration_identity
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata stays empty until approved SQLAlchemy models are introduced.
target_metadata = Base.metadata


def configured_migration_url() -> str:
    return require_migration_url(get_migration_settings().migration_database_url)


def run_migrations_offline() -> None:
    # Offline SQL compilation needs a dialect, not credentials or a live database.
    url = config.get_main_option("sqlalchemy.url") or "postgresql://"
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Credentials stay in settings and are never included in a raised error.
    try:
        configuration = config.get_section(config.config_ini_section, {})
        configuration["sqlalchemy.url"] = configured_migration_url()
        connectable = engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            hide_parameters=True,
        )

        with connectable.connect() as connection:
            # The external transaction encloses role setup and all migration DDL.
            # Alembic recognizes it as externally managed; this block commits it.
            with connection.begin():
                connection.execute(text("SET ROLE inventory_aios_owner"))
                connection.execute(text("SET search_path TO public, pg_catalog"))
                session_user, current_user = connection.execute(
                    text("SELECT session_user, current_user")
                ).one()
                verify_migration_identity(session_user, current_user)
                context.configure(
                    connection=connection,
                    target_metadata=target_metadata,
                    transactional_ddl=True,
                )
                with context.begin_transaction():
                    context.run_migrations()
    except Exception:
        raise RuntimeError("Online migration failed; connection details are withheld.") from None


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()