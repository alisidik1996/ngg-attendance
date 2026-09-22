from pydantic import BaseModel, Field
from typing import Optional


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=200)
    role: str = Field(default="staff")


class UpdateUserRequest(BaseModel):
    password: Optional[str] = Field(default=None, min_length=6, max_length=200)
    role: Optional[str] = None
    is_active: Optional[bool] = None
