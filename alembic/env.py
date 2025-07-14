from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from common.db import Base
from common import models 
from alembic import context

import sys
import os
import inspect

# Calculate project_root (should be /app inside container)
# Adjust project_root calculation if necessary to point to the base of the 'common' module
# Given the Dockerfile COPY ./common /app/common, project_root should be the parent of /app/common
# Let's make it more robust for local runs and container runs
current_file_dir = os.path.dirname(inspect.getfile(inspect.currentframe()))
# Assuming alembic/ is at project_root/alembic/
project_root = os.path.abspath(os.path.join(current_file_dir, '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


from common.database_models import Base 

config = context.config


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

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()