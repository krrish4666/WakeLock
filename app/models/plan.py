from sqlalchemy import Column, Integer, BigInteger, ForeignKey, String, Enum, DateTime, Numeric, Boolean, Time
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.core.database import Base

class PlanStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    WITHDRAWN = "WITHDRAWN"

class SessionStatus(str, enum.Enum):
    PENDING = "PENDING"
    ALARM_SENT = "ALARM_SENT"
    OTP_ACTIVE = "OTP_ACTIVE"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"

class AccountabilityPlan(Base):
    __tablename__ = "accountability_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), nullable=False, index=True)
    
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    
    total_amount_locked = Column(Numeric(10, 2), nullable=False)
    per_day_penalty = Column(Numeric(10, 2), nullable=False)
    remaining_balance = Column(Numeric(10, 2), nullable=False)
    
    days_verified = Column(Integer, default=0)
    days_missed = Column(Integer, default=0)
    
    
    status = Column(Enum(PlanStatus), default=PlanStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="plans")
    wake_sessions = relationship("WakeSession", back_populates="plan", cascade="all, delete-orphan")

class WakeSession(Base):
    __tablename__ = "wake_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    plan_id = Column(Integer, ForeignKey("accountability_plans.id"), nullable=False, index=True)
    
    date = Column(DateTime(timezone=True), nullable=False)
    status = Column(Enum(SessionStatus), default=SessionStatus.PENDING)
    
    attempts = Column(Integer, default=0)
    otp_expiry_time = Column(DateTime(timezone=True), nullable=True)
    
    processed_flag = Column(Boolean, default=False) # Idempotency lock
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    plan = relationship("AccountabilityPlan", back_populates="wake_sessions")
    otp_token = relationship("OTPToken", uselist=False, back_populates="wake_session", cascade="all, delete-orphan")

class OTPToken(Base):
    __tablename__ = "otp_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("wake_sessions.id"), nullable=False, unique=True)
    
    token_hash = Column(String, nullable=False)
    drop_time = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    wake_session = relationship("WakeSession", back_populates="otp_token")
