from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import datetime
from enum import Enum


class Role(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    SACCO_ADMIN = "SACCO_ADMIN"
    MEMBER = "MEMBER"


class SaccoCreate(BaseModel):
    name: str = Field(..., min_length=2)
    email: Optional[EmailStr]


class SaccoOut(BaseModel):
    id: int
    name: str
    email: Optional[EmailStr]
    created_at: datetime.datetime

    class Config:
        orm_mode = True


class UserCreate(BaseModel):
    full_name: Optional[str]
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: Optional[Role] = Role.MEMBER
    sacco_id: Optional[int] = None


class UserOut(BaseModel):
    id: int
    full_name: Optional[str]
    email: EmailStr
    role: Role
    sacco_id: Optional[int]
    created_at: datetime.datetime

    class Config:
        orm_mode = True
