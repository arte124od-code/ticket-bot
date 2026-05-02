"""Database models - Ticket King Charts"""
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///ticketking.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class GuildConfig(Base):
    __tablename__ = "guild_configs"
    guild_id = Column(Integer, primary_key=True)
    ticket_counter = Column(Integer, default=0)

class Panel(Base):
    __tablename__ = "panels"
    id = Column(Integer, primary_key=True)
    guild_id = Column(Integer, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    category_id = Column(Integer, nullable=False)
    staff_role_id = Column(Integer, nullable=True)
    log_channel_id = Column(Integer, nullable=True)
    panel_type = Column(String(20), default="buttons")
    color = Column(String(10), default="5865F2")
    emoji = Column(String(50), default="🎫")
    button_style = Column(String(20), default="primary")
    button_label = Column(String(80), default="Abrir Ticket")
    button_emoji = Column(String(50), nullable=True)
    welcome_message = Column(Text, default="Obrigado por entrar em contato! Um membro da equipe irá atendê-lo.")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    total_tickets = Column(Integer, default=0)

class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True)
    guild_id = Column(Integer, nullable=False, index=True)
    channel_id = Column(Integer, unique=True, nullable=False)
    user_id = Column(Integer, nullable=False, index=True)
    panel_id = Column(Integer, ForeignKey("panels.id"), nullable=True, index=True)
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    first_response_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(String(20), default="open")
    claimed_by = Column(Integer, nullable=True, index=True)
    claimed_at = Column(DateTime, nullable=True)
    transcript = Column(Text, nullable=True)
    rating = Column(Integer, nullable=True)
    rating_comment = Column(Text, nullable=True)

class StaffStats(Base):
    __tablename__ = "staff_stats"
    id = Column(Integer, primary_key=True)
    guild_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    tickets_claimed = Column(Integer, default=0)
    tickets_closed = Column(Integer, default=0)
    total_response_time = Column(Float, default=0.0)
    total_resolution_time = Column(Float, default=0.0)
    avg_rating = Column(Float, default=0.0)
    rating_count = Column(Integer, default=0)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
