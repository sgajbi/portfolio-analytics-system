# src/services/calculators/cost_calculator_service/Dockerfile

FROM python:3.11-slim-bookworm AS python-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser
RUN python -m venv /opt/venv && chown -R appuser:appuser /opt/venv

WORKDIR /app

FROM python-base AS builder

# Install shared libs (NON-editable to avoid egg-links)
COPY src/libs/portfolio-common/ /app/src/libs/portfolio-common/
RUN pip install /app/src/libs/portfolio-common

# Install the financial calculator engine (NON-editable)
COPY src/libs/financial-calculator-engine/ /app/src/libs/financial-calculator-engine/
RUN pip install /app/src/libs/financial-calculator-engine

# Install the service
COPY src/services/calculators/cost_calculator_service/pyproject.toml /app/src/services/calculators/cost_calculator_service/pyproject.toml
COPY src/services/calculators/cost_calculator_service/app /app/src/services/calculators/cost_calculator_service/app
RUN pip install /app/src/services/calculators/cost_calculator_service

FROM python-base AS final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/src/services/calculators/cost_calculator_service/app /app/app

USER appuser
EXPOSE 8083
CMD ["python", "-m", "app.main"]
