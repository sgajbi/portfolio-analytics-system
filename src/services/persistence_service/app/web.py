# services/persistence_service/app/web.py
import logging
import asyncio
from fastapi import FastAPI, status, HTTPException
from sqlalchemy import text
from confluent_kafka.admin import AdminClient

from portfolio_common.db import AsyncSessionLocal
from portfolio_common.config import KAFKA_BOOTSTRAP_SERVERS
from .monitoring import setup_metrics

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Persistence Service - Health",
    description="Provides health and readiness probes for the Persistence Service.",
    version="1.0.0",
)

# Setup and expose the /metrics endpoint
setup_metrics(app)

async def check_db_health():
    """Checks if a valid asynchronous connection can be established with the database."""
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        # Log only the error message for health checks to avoid spamming tracebacks
        logger.error(f"Health Check: Database connection failed: {e}", exc_info=False)
        return False

async def check_kafka_health():
    """Checks if a connection can be established with Kafka."""
    try:
        admin_client = AdminClient({'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS})
        # list_topics is a lightweight way to check broker connectivity
        await asyncio.to_thread(admin_client.list_topics, timeout=5)
        return True
    except Exception as e:
        logger.error(f"Health Check: Kafka connection failed: {e}", exc_info=False)
        return False

@app.get("/health/live", status_code=status.HTTP_200_OK, tags=["Health"])
async def liveness_probe():
    """
    Liveness probe: A simple check to confirm the service process is running.
    """
    return {"status": "alive"}

@app.get("/health/ready", status_code=status.HTTP_200_OK, tags=["Health"])
async def readiness_probe():
    """
    Readiness probe: Checks if the service can connect to its dependencies
    (PostgreSQL and Kafka) and is ready to process messages.
    """
    db_ok, kafka_ok = await asyncio.gather(
        check_db_health(),
        check_kafka_health()
    )

    if db_ok and kafka_ok:
        return {"status": "ready", "dependencies": {"database": "ok", "kafka": "ok"}}
    
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "status": "not_ready",
            "dependencies": {
                "database": "ok" if db_ok else "unavailable",
                "kafka": "ok" if kafka_ok else "unavailable",
            },
        },
    )