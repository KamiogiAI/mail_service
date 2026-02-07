import re
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional


def validate_password_strength(password: str) -> str:
    """
    パスワード強度チェック
    - 8文字以上
    - 大文字、小文字、数字、記号のうち3種類以上を含む
    """
    if len(password) < 8:
        raise ValueError("パスワードは8文字以上で入力してください")

    categories = 0
    if re.search(r"[A-Z]", password):
        categories += 1
    if re.search(r"[a-z]", password):
        categories += 1
    if re.search(r"[0-9]", password):
        categories += 1
    if re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?~`]", password):
        categories += 1

    if categories < 3:
        raise ValueError(
            "パスワードは大文字・小文字・数字・記号のうち3種類以上を含めてください"
        )

    return password


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name_last: str = Field(min_length=1, max_length=100)
    name_first: str = Field(min_length=1, max_length=100)

    @field_validator("password")
    @classmethod
    def check_password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


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

    @field_validator("new_password")
    @classmethod
    def check_password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def check_password_strength(cls, v: str) -> str:
        return validate_password_strength(v)


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
