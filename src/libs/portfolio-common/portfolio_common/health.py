# src/libs/portfolio-common/portfolio_common/health.py
import logging
import asyncio
from typing import List, Callable, Awaitable

from fastapi import APIRouter, status, HTTPException
from sqlalchemy import text
from confluent_kafka.admin import AdminClient

from .db import AsyncSessionLocal
from .config import KAFKA_BOOTSTRAP_SERVERS

logger = logging.getLogger(__name__)

DependencyCheck = Callable[[], Awaitable[bool]]

async def check_db_health() -> bool:
    """Checks if a valid async connection can be established with the database."""
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Health Check: Database connection failed: {e}", exc_info=False)
        return False

async def check_kafka_health() -> bool:
    """Checks if a connection can be established with Kafka."""
    try:
        admin_client = AdminClient({'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS})
        await asyncio.to_thread(admin_client.list_topics, timeout=5)
        return True
    except Exception as e:
        logger.error(f"Health Check: Kafka connection failed: {e}", exc_info=False)
        return False

def create_health_router(*dependencies: str) -> APIRouter:
    """
    Creates a standardized health check router.
    
    Args:
        *dependencies: A list of strings ('db', 'kafka') specifying which
                       dependencies to check for the readiness probe.
    
    Returns:
        A FastAPI APIRouter with /live and /ready endpoints.
    """
    router = APIRouter(tags=["Health"])
    
    dep_map = {
        'db': ('database', check_db_health),
        'kafka': ('kafka', check_kafka_health)
    }

    @router.get("/health/live", status_code=status.HTTP_200_OK)
    async def liveness_probe():
        return {"status": "alive"}

    @router.get("/health/ready", status_code=status.HTTP_200_OK)
    async def readiness_probe():
        checks_to_run = [dep_map[dep][1] for dep in dependencies if dep in dep_map]
        
        results = await asyncio.gather(*[check() for check in checks_to_run])
        
        all_ok = all(results)
        
        dep_status = {
            dep_map[dep][0]: "ok" if results[i] else "unavailable"
            for i, dep in enumerate(dependencies) if dep in dep_map
        }
        
        if all_ok:
            return {"status": "ready", "dependencies": dep_status}
        
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "dependencies": dep_status},
        )
        
    return router