# src/services/recalculation_service/Dockerfile
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

COPY src/libs/portfolio-common/ /app/src/libs/portfolio-common/
RUN pip install -e /app/src/libs/portfolio-common

# Copy and install the financial calculator engine, as this service will use its logic
COPY src/libs/financial-calculator-engine/ /app/src/libs/financial-calculator-engine/
RUN pip install /app/src/libs/financial-calculator-engine

COPY src/services/recalculation_service/pyproject.toml /app/src/services/recalculation_service/pyproject.toml
COPY src/services/recalculation_service/app /app/src/services/recalculation_service/app
RUN pip install /app/src/services/recalculation_service

FROM python-base AS final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
COPY --from=builder --chown=appuser:appuser /app/src/services/recalculation_service/app /app/app
COPY --from=builder --chown=appuser:appuser /app/src/libs /app/src/libs

USER appuser
EXPOSE 8086
CMD ["python", "-m", "app.main"]