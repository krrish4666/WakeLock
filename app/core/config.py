from pydantic_settings import BaseSettings, SettingsConfigDict
from urllib.parse import urlparse

class Settings(BaseSettings):
    PROJECT_NAME: str = "WakeLock Backend"
    
    # Security
    SECRET_KEY: str = "supersecretkeythatyoushouldchange"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/wakelock"
    
    # Redis & Celery
    REDIS_URL: str = "redis://localhost:6379/0"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = "your_telegram_bot_token_here"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
