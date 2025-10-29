# models.py
from sqlalchemy import Table, Column, Integer, String, Float, DateTime, MetaData
from pydantic import BaseModel
from datetime import datetime

metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String, unique=True, nullable=False),
    Column("password_hash", String, nullable=False),
    Column("created_at", DateTime)
)

qr_lots = Table(
    "qr_lots", metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String),
    Column("price", Float),
    Column("currency", String),  # TRC20 or BEP20
    Column("token_contract", String, nullable=True),
    Column("receive_address", String),
    Column("filename", String),
    Column("seller", String),
    Column("reserved_to", String, nullable=True),
    Column("status", String),  # available, awaiting_payment, paid
    Column("created_at", DateTime),
    Column("updated_at", DateTime, nullable=True)
)

class UserCreate(BaseModel):
    username: str
    password: str

class UserPublic(BaseModel):
    id: int
    username: str
    created_at: datetime

class QRCreate(BaseModel):
    title: str
    price: float
    currency: str
    token_contract: str | None
    receive_address: str

class QRPublic(BaseModel):
    id: int
    title: str
    price: float
    currency: str
    status: str
    seller: str
