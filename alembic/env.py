# alembic/env.py
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_as_existing_filename:
    fileConfig(config.config_file_as_existing_filename)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import Base
# target_metadata = Base.metadata
from common.database_models import Base # Import your Base
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an actual DBAPI connection.

    Calls to context.execute() here send SQL statements to the compiler
    (implicitly or explicitly) for later output to the given file handle.

    """
    url = config.get_main_option("sqlalchemy.url")
    if url is None: # Fallback to DATABASE_URL env var if not in alembic.ini
        import os
        url = os.environ.get("DATABASE_URL")
        if url is None:
            raise Exception("DATABASE_URL environment variable is not set and sqlalchemy.url is not in alembic.ini")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create a connection
    to the database truly.

    """
    import os
    connectable = None # Initialize connectable

    # Get the configuration section
    configuration = config.get_section(config.config_ini_section)

    # NEW: Explicitly set sqlalchemy.url in the configuration dictionary
    # using the DATABASE_URL environment variable.
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        configuration["sqlalchemy.url"] = db_url
    else:
        # Fallback if DATABASE_URL is not set (shouldn't happen with docker-compose)
        # This will make engine_from_config fail with 'url' KeyError if not present
        # This mirrors Alembic's default behavior if no url is given.
        pass

    try:
        connectable = engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata
            )

            with context.run_migrations():
                pass
    finally:
        if connectable is not None:
            connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()