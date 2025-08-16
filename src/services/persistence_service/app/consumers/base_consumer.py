# src/services/persistence_service/app/consumers/base_consumer.py
import logging
import json
import sys
from typing import Type, Optional, Dict, Any
from abc import ABC, abstractmethod
from pydantic import BaseModel, ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from tenacity import retry, stop_after_delay, wait_exponential, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.db import get_async_db_session
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)

class GenericPersistenceConsumer(BaseConsumer, ABC):
    """
    An abstract base class for persistence consumers that handles common boilerplate:
    - JSON Deserialization and Pydantic Validation
    - Idempotency checks
    - Database transaction and session management
    - Error handling, retries, and DLQ publishing
    - Optional outbox event creation on success
    """

    @property
    @abstractmethod
    def event_model(self) -> Type[BaseModel]:
        """The Pydantic event model for validating the incoming message."""
        pass

    @property
    @abstractmethod
    def service_name(self) -> str:
        """The unique name of the service for idempotency tracking."""
        pass

    @abstractmethod
    async def handle_persistence(self, db_session, event: BaseModel) -> Any:
        """
        The core persistence logic to be implemented by subclasses.
        This method is responsible for calling the appropriate repository method.
        It should return the persisted database object if an outbox event is needed.
        """
        pass

    def get_outbox_event(self, persisted_object: Any) -> Optional[Dict[str, Any]]:
        """
        Subclasses can override this to create an outbox event upon successful persistence.
        Return a dictionary with kwargs for OutboxRepository.create_outbox_event.
        """
        return None

    async def process_message(self, msg: Message):
        """Processes a single message with retries and error handling."""
        try:
            await self._process_message_with_retry(msg)
        except (OperationalError, DBAPIError):
            logger.critical(f"Unrecoverable DB error for {self.service_name}. Shutting down.", exc_info=True)
            sys.exit(1)
        except Exception as e:
            logger.error(f"Fatal error for {self.service_name} after retries. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_delay(300),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError, OperationalError)),
        reraise=True
    )
    async def _process_message_with_retry(self, msg: Message):
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()
        event = None

        try:
            event_data = json.loads(msg.value().decode('utf-8'))
            event = self.event_model.model_validate(event_data)
            
            # Use a specific attribute for idempotency key if available (e.g., transaction_id), else use the Kafka coordinates.
            idempotency_key = getattr(event, 'transaction_id', event_id)

            async for db in get_async_db_session():
                async with db.begin():
                    idempotency_repo = IdempotencyRepository(db)

                    if await idempotency_repo.is_event_processed(idempotency_key, self.service_name):
                        logger.warning(f"Event {idempotency_key} already processed. Skipping.")
                        return

                    persisted_object = await self.handle_persistence(db, event)
                    
                    outbox_details = self.get_outbox_event(persisted_object)
                    if outbox_details:
                        outbox_repo = OutboxRepository(db)
                        await outbox_repo.create_outbox_event(correlation_id=correlation_id, **outbox_details)

                    await idempotency_repo.mark_event_processed(
                        event_id=idempotency_key,
                        portfolio_id=getattr(event, 'portfolio_id', 'N/A'),
                        service_name=self.service_name,
                        correlation_id=correlation_id
                    )

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("Message validation failed. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except (DBAPIError, IntegrityError, OperationalError):
            logger.warning(f"DB error for {self.service_name}. Retrying...", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error in {self.service_name}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)