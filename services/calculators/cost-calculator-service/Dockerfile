# services/calculators/cost-calculator-service/Dockerfile

# Stage 1: Base image setup
FROM python:3.11-slim-bookworm as python-base

ENV POETRY_VIRTUALENVS_CREATE=false \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home appuser
RUN python -m venv /opt/venv && \
    chown -R appuser:appuser /opt/venv

WORKDIR /app

# Stage 2: Builder stage
FROM python-base as builder

ENV PYTHONPATH="/app/libs/portfolio-common:/app/libs/financial-calculator-engine:/app/services/calculators/cost-calculator-service"

COPY libs/portfolio-common/ /app/libs/portfolio-common/
COPY libs/financial-calculator-engine/ /app/libs/financial-calculator-engine/
RUN pip install -e /app/libs/portfolio-common && \
    pip install -e /app/libs/financial-calculator-engine

COPY services/calculators/cost-calculator-service/pyproject.toml /app/services/calculators/cost-calculator-service/pyproject.toml
COPY services/calculators/cost-calculator-service/app /app/services/calculators/cost-calculator-service/app
RUN pip install /app/services/calculators/cost-calculator-service

# Stage 3: Final production stage
FROM python-base as final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/services/calculators/cost-calculator-service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/libs /app/libs

USER appuser
CMD ["python", "app/main.py"]