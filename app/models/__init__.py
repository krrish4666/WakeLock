from app.core.database import Base

# Import all models here so Alembic can discover them during `target_metadata = Base.metadata`
from app.models.user import User
from app.models.wallet import Wallet, WalletTransaction, PlatformRevenue
from app.models.plan import AccountabilityPlan, WakeSession, OTPToken

__all__ = [
    "Base", "User", "Wallet", "WalletTransaction", "PlatformRevenue",
    "AccountabilityPlan", "WakeSession", "OTPToken"
]
