from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name_last: str = Field(min_length=1, max_length=100)
    name_first: str = Field(min_length=1, max_length=100)


class VerifyEmailRequest(BaseModel):
    user_id: int
    code: str = Field(min_length=6, max_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class AuthResponse(BaseModel):
    message: str
    user_id: Optional[int] = None
    csrf_token: Optional[str] = None


class UserInfo(BaseModel):
    id: int
    member_no: str
    email: str
    name_last: str
    name_first: str
    role: str
    email_verified: bool

    model_config = {"from_attributes": True}
