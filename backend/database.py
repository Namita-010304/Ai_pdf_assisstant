from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()

# ─── Database URL auto-detection ───
# Default: SQLite (zero setup, works everywhere)
# Also supports PostgreSQL and MySQL if DATABASE_URL is provided
_raw_url = os.getenv("DATABASE_URL", "sqlite:///./pdf_assistant.db")

# Auto-fix common URL formats from cloud providers
if _raw_url.startswith("postgres://"):
    _raw_url = _raw_url.replace("postgres://", "postgresql://", 1)
elif _raw_url.startswith("mysql://"):
    _raw_url = _raw_url.replace("mysql://", "mysql+mysqlconnector://", 1)

DATABASE_URL = _raw_url

# SQLite needs check_same_thread=False for FastAPI
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    from models import Document, Message  # noqa: F401
    Base.metadata.create_all(bind=engine)
