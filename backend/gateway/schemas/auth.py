"""Auth API request / response schemas (OpenAPI-aligned)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    organization_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str
    role: str
    organization_id: UUID


class TokenPair(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access token expires
    user: UserOut
