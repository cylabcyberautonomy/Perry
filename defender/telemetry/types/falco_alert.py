from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


class FalcoAlert(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
    )

    hostname: str
    output: str
    priority: str
    rule: str
    source: str
    tags: List[str]
    time: datetime

    # Falco's detailed output fields, kept as a dict because keys contain dots.
    output_fields: Dict[str, Any] = Field(..., alias="output_fields")

    id: Optional[str] = Field(None, alias="_id")
