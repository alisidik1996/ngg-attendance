from pydantic import BaseModel, BeforeValidator
from typing import Annotated

def coerce_to_str(v) -> str:
    if v is None:
        raise ValueError("no_order wajib diisi")
    if isinstance(v, (dict, list, bool)):
        raise ValueError("no_order tidak valid")
    s = str(v).strip()
    if not s:
        raise ValueError("no_order wajib diisi")
    return s

class CheckInRequest(BaseModel):
    no_order: Annotated[str, BeforeValidator(coerce_to_str)]

class AttendanceRequest(BaseModel):
    no_order: Annotated[str, BeforeValidator(coerce_to_str)]
