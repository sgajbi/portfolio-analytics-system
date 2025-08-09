from pydantic import BaseModel, Field, ConfigDict
from typing import List

class InstrumentRecord(BaseModel):
    """
    Represents a single, detailed instrument record for API responses.
    """
    security_id: str
    name: str
    isin: str
    currency: str
    product_type: str
    
    model_config = ConfigDict(
        from_attributes=True
    )

class PaginatedInstrumentResponse(BaseModel):
    """
    Represents the paginated API response for an instrument query.
    """
    total: int = Field(..., description="The total number of instruments matching the query.")
    skip: int = Field(..., description="The number of records skipped (offset).")
    limit: int = Field(..., description="The maximum number of records returned.")
    instruments: List[InstrumentRecord] = Field(..., description="The list of instrument records for the current page.")