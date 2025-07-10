
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Ensure Base is imported correctly
import sys
import os
import inspect

# Calculate project_root (should be /app inside container)
project_root = os.path.abspath(os.path.join(os.path.dirname(inspect.getfile(inspect.currentframe())), '..'))
if project_root not in sys.path: # Avoid adding duplicate paths
    sys.path.insert(0, project_root)

# Import Base from your application's database module
from app.database import Base # This is confirmed to work now!


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
# Ensure this is defined AT THE TOP LEVEL of the script
config = context.config # <--- This line is critical and must be globally accessible


# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata # Assign your imported Base's metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url") # Uses config
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}), # Uses config
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True
        )

        with context.begin_transaction():
            context.run_migrations()

# This conditional block ensures either online or offline migration runs
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()