# db.py
from sqlalchemy import create_engine, MetaData
from databases import Database

DB_URL = "sqlite:///./data/qr_market.db"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
database = Database(DB_URL)
metadata = MetaData()
