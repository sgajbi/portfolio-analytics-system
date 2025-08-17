# src/services/calculators/performance_calculator_service/app/web.py
from fastapi import FastAPI
from portfolio_common.health import create_health_router

app = FastAPI(title="Performance Calculator - Health")

# This service will depend on the database.
health_router = create_health_router('db')
app.include_router(health_router)