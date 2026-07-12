from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_name = Column(String(255), nullable=False)
    page_count = Column(Integer, default=0)
    file_path = Column(String(512), nullable=False)
    upload_time = Column(DateTime, default=datetime.utcnow)

    messages = relationship("Message", back_populates="document", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(64), nullable=False, index=True)
    sender = Column(String(10), nullable=False)   # 'user' or 'bot'
    content = Column(Text, nullable=False)
    language = Column(String(10), default="en")
    citations = Column(Text, nullable=True)       # JSON string of citations
    timestamp = Column(DateTime, default=datetime.utcnow)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    document = relationship("Document", back_populates="messages")
