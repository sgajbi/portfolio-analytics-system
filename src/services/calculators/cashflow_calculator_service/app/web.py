# services/calculators/cashflow_calculator_service/app/web.py
import logging
import asyncio
from fastapi import FastAPI, status, HTTPException
from sqlalchemy import text

from portfolio_common.db import AsyncSessionLocal

logger = logging.getLogger(__name__)
app = FastAPI(title="Cashflow Calculator - Health")

async def check_db_health():
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Health Check: Database connection failed: {e}", exc_info=False)
        return False

@app.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness_probe():
    return {"status": "alive"}

@app.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness_probe():
    db_ok = await check_db_health()
    if db_ok:
        return {"status": "ready", "dependencies": {"database": "ok"}}
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)