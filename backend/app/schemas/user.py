import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    role: Literal["ADMIN", "DISPATCHER", "OFFICER", "EXECUTIVE"]
    responsible_province: str | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: Literal["ADMIN", "DISPATCHER", "OFFICER", "EXECUTIVE"] | None = None
    responsible_province: str | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None
    role: str
    responsible_province: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
    pages: int
