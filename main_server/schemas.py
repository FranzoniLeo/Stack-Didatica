from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DlqReprocessBody(BaseModel):
    """Reprocessar entrada DLQ: preferir dlq_entry_id; job_id só para registos antigos sem id."""

    dlq_entry_id: str | None = Field(None, min_length=4, max_length=64)
    job_id: str | None = Field(None, min_length=4, max_length=64)

    @model_validator(mode="after")
    def require_one_key(self):
        if not (self.dlq_entry_id or "").strip() and not (self.job_id or "").strip():
            raise ValueError("Informe dlq_entry_id ou job_id")
        return self
