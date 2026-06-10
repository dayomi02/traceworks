from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str
    role: str


class UserMe(BaseModel):
    user_id: str
    email: str
    name: str
    role: str
    is_active: bool
