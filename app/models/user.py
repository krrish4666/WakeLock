from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, Time, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    wallet = relationship("Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan")
    plans = relationship("AccountabilityPlan", back_populates="user", cascade="all, delete-orphan")
    preferences = relationship("UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")

class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, unique=True)
    
    # 05:00:00 style time objects
    default_alarm_time = Column(Time, nullable=True) 
    weekend_alarm_time = Column(Time, nullable=True)
    
    # Buffer and drop windows in minutes
    buffer_duration_minutes = Column(Integer, default=20)
    otp_window_duration_minutes = Column(Integer, default=10)
    
    timezone = Column(String, default="Asia/Kolkata")
    
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="preferences")
