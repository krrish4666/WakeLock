from sqlalchemy import Column, Integer, BigInteger, ForeignKey, Enum, DateTime, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.core.database import Base

class TransactionType(str, enum.Enum):
    DEPOSIT = "DEPOSIT"
    PLAN_LOCK = "PLAN_LOCK"
    PENALTY = "PENALTY"
    REFUND = "REFUND"
    WITHDRAWAL = "WITHDRAWAL"

class Wallet(Base):
    __tablename__ = "wallets"

    user_id = Column(BigInteger, ForeignKey("users.telegram_id"), primary_key=True)
    total_balance = Column(Numeric(10, 2), default=0.0)
    locked_balance = Column(Numeric(10, 2), default=0.0)
    available_balance = Column(Numeric(10, 2), default=0.0)
    
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="wallet")
    transactions = relationship("WalletTransaction", back_populates="wallet", cascade="all, delete-orphan")

class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_id = Column(BigInteger, ForeignKey("wallets.user_id"), nullable=False, index=True)
    type = Column(Enum(TransactionType), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    balance_after = Column(Numeric(10, 2), nullable=False)
    reference_id = Column(Integer, nullable=True) # ID of the Plan or WakeSession
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    wallet = relationship("Wallet", back_populates="transactions")

class PlatformRevenue(Base):
    __tablename__ = "platform_revenue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    total_collected = Column(Numeric(10, 2), default=0.0)
    date = Column(DateTime(timezone=True), server_default=func.now())
    source_plan_id = Column(Integer, nullable=True) # Linked logically, not hard FK for auditing isolation
