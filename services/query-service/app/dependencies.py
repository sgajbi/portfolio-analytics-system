from fastapi import Query
from typing import Dict

def pagination_params(
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return")
) -> Dict[str, int]:
    """
    A dependency that provides standardized pagination query parameters.
    - skip: The starting offset.
    - limit: The number of items to return.
    """
    return {"skip": skip, "limit": limit}