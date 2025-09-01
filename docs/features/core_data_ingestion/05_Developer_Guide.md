
# Developer's Guide: Ingestion Service

This guide provides developers with instructions for working on the `ingestion_service`.

## 1. Local Development & Setup

The service can be run locally as part of the full system using Docker Compose. Please refer to the main `README.md` file for detailed instructions on initial setup, installing dependencies, and running the system.

* **Service Location:** `src/services/ingestion_service/`
* **Running Tests:** The integration tests for this service verify the API contract and the interaction with the Kafka producer mock. Run them from the project root:
    ```bash
    pytest tests/integration/services/ingestion_service/
    ```

## 2. Adding a New Ingestion Endpoint

Follow these steps to add a new data entity to the ingestion service. Let's use a hypothetical "AdvisoryNote" entity as an example.

1.  **Define the DTO:** Create a new file `src/services/ingestion_service/app/DTOs/advisory_note_dto.py` with Pydantic models for the new entity.

    ```python
    # advisory_note_dto.py
    from pydantic import BaseModel
    from typing import List

    class AdvisoryNote(BaseModel):
        note_id: str
        portfolio_id: str
        content: str

    class AdvisoryNoteIngestionRequest(BaseModel):
        notes: List[AdvisoryNote]
    ```

2.  **Add a New Kafka Topic:** The new entity will need its own topic. Add it to the list in `tools/kafka_setup.py`.

    ```python
    # tools/kafka_setup.py
    TOPICS_TO_CREATE = [
        # ... existing topics
        "raw_advisory_notes",
    ]
    ```

3.  **Create the Router:** Create a new file `src/services/ingestion_service/app/routers/advisory_notes.py`. This will define the API endpoint.

    ```python
    # advisory_notes.py
    from fastapi import APIRouter, Depends
    from app.DTOs.advisory_note_dto import AdvisoryNoteIngestionRequest
    from app.services.ingestion_service import IngestionService, get_ingestion_service

    router = APIRouter()

    @router.post("/ingest/advisory-notes", status_code=202)
    async def ingest_notes(
        request: AdvisoryNoteIngestionRequest,
        service: IngestionService = Depends(get_ingestion_service)
    ):
        await service.publish_advisory_notes(request.notes)
        return {"message": "Notes queued."}
    ```

4.  **Update the Ingestion Service:** Add the publishing logic to `src/services/ingestion_service/app/services/ingestion_service.py`.

    ```python
    # ingestion_service.py
    from app.DTOs.advisory_note_dto import AdvisoryNote
    from portfolio_common.config import KAFKA_RAW_ADVISORY_NOTES_TOPIC # Add to config

    class IngestionService:
        # ... existing methods ...
        async def publish_advisory_notes(self, notes: List[AdvisoryNote]):
            headers = self._get_headers()
            for note in notes:
                self._kafka_producer.publish_message(
                    topic=KAFKA_RAW_ADVISORY_NOTES_TOPIC,
                    key=note.portfolio_id,
                    value=note.model_dump(mode='json'),
                    headers=headers
                )
    ```

5.  **Register the Router:** In `src/services/ingestion_service/app/main.py`, import and register the new router.

    ```python
    # main.py
    from .routers import advisory_notes # import new router

    # ...
    app.include_router(advisory_notes.router) # register it
    ```

