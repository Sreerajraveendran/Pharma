import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import config as app_config
from app.db.tables import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Tests (and tooling) can point Alembic at another database via the -x url=... option
URL = context.get_x_argument(as_dictionary=True).get("url") or app_config.DATABASE_URL


def run_migrations_offline():
    context.configure(url=URL, target_metadata=metadata, literal_binds=True,
                      dialect_opts={"paramstyle": "named"}, compare_server_default=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection):
    context.configure(connection=connection, target_metadata=metadata, compare_server_default=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    engine = create_async_engine(URL)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
