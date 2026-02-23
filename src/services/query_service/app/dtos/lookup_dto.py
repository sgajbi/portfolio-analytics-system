from pydantic import BaseModel, Field


class LookupItem(BaseModel):
    id: str = Field(..., description="Canonical identifier used by UI selectors.")
    label: str = Field(..., description="Display label for UI selector option.")


class LookupResponse(BaseModel):
    items: list[LookupItem] = Field(
        default_factory=list,
        description="Lookup options returned for the requested catalog.",
    )
