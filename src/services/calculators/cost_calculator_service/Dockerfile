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

# 1. Copy local library source code first
COPY src/libs/portfolio-common/ /app/src/libs/portfolio-common/
COPY src/libs/financial-calculator-engine/ /app/src/libs/financial-calculator-engine/

# 2. Copy service app code
COPY src/services/calculators/cost_calculator_service/pyproject.toml /app/src/services/calculators/cost_calculator_service/pyproject.toml
COPY src/services/calculators/cost_calculator_service/app /app/src/services/calculators/cost_calculator_service/app

# 3. Install all packages together. This is more reliable than installing them one by one in separate layers
#    when they have local path dependencies on each other.
RUN pip install /app/src/libs/portfolio-common
RUN pip install /app/src/libs/financial-calculator-engine
RUN pip install /app/src/services/calculators/cost_calculator_service


FROM python-base AS final

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
# We only need the service's own app code in the final image, as dependencies are in venv
COPY --from=builder --chown=appuser:appuser /app/src/services/calculators/cost_calculator_service/app /app/app

USER appuser
EXPOSE 8083
CMD ["python", "-m", "app.main"]