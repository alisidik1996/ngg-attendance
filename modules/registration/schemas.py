from pydantic import BaseModel, BeforeValidator
from typing import Annotated

def coerce_to_str(v) -> str:
    return str(v)

class CheckInRequest(BaseModel):
    no_order: Annotated[str, BeforeValidator(coerce_to_str)]

class AttendanceRequest(BaseModel):
    no_order: Annotated[str, BeforeValidator(coerce_to_str)]
