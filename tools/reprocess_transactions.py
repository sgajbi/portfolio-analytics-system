# tools/reprocess_transactions.py
import argparse
import asyncio
import logging
import sys
import os
from typing import List

# Ensure the script can find the portfolio-common library
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from portfolio_common.logging_utils import setup_logging, correlation_id_var, generate_correlation_id
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.db import get_async_db_session
from portfolio_common.reprocessing_repository import ReprocessingRepository

setup_logging()
logger = logging.getLogger(__name__)

async def main(transaction_ids: List[str]):
    """
    Main async function to orchestrate the reprocessing task.
    """
    if not transaction_ids:
        logger.warning("No transaction IDs provided. Exiting.")
        return

    # Set a correlation ID for this entire batch operation for traceability
    correlation_id = generate_correlation_id("REPROCESS_TOOL")
    token = correlation_id_var.set(correlation_id)
    
    logger.info(
        f"Starting reprocessing tool for {len(transaction_ids)} transaction(s).",
        extra={"correlation_id": correlation_id}
    )

    kafka_producer = get_kafka_producer()
    
    try:
        async for db_session in get_async_db_session():
            async with db_session.begin():
                repo = ReprocessingRepository(db=db_session, kafka_producer=kafka_producer)
                reprocessed_count = await repo.reprocess_transactions_by_ids(
                    transaction_ids=transaction_ids
                )
                logger.info(f"Completed reprocessing. Republished {reprocessed_count} events.")
    finally:
        kafka_producer.flush(timeout=10)
        correlation_id_var.reset(token)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="A tool to reprocess specific transactions by re-publishing them to the 'raw_transactions_completed' topic."
    )
    parser.add_argument(
        "--transaction-ids",
        nargs='+',  # accepts one or more arguments
        required=True,
        help="A space-separated list of transaction_id values to reprocess."
    )
    
    args = parser.parse_args()
    
    asyncio.run(main(transaction_ids=args.transaction_ids))