"""Shared schema utilities."""
from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str


class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
