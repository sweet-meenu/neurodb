from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("invalid email address")
        return v.lower().strip()


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class ProjectResponse(BaseModel):
    id: str
    name: str
    created_at: float
    api_key_prefix: str


class ProjectCreatedResponse(ProjectResponse):
    api_key: str
    connection_string: str


class ConnectionInfoResponse(BaseModel):
    id: str
    name: str
    connection_string: str
    api_key_prefix: str
