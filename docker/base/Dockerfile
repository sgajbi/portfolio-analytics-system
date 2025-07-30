# This is the base image for all Python services in the project.
# It prepares the Python version, virtual environment, and a non-root user.
FROM python:3.11-slim-bookworm

# Set environment variables to ensure consistent behavior
ENV POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Set the PATH to include the virtual environment's bin directory
    PATH="/opt/venv/bin:$PATH"

# Create a non-root user for security
RUN useradd --create-home appuser

# Create the virtual environment
RUN python -m venv /opt/venv && \
    # chown the venv to the new user so it can manage packages
    chown -R appuser:appuser /opt/venv

WORKDIR /app