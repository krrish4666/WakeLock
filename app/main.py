from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.bot import application
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    # For local development with FastAPI, we MUST use piecemeal polling 
    # because application.run_polling() tries to hijack the main event loop.
    await application.initialize()
    await application.start()
    if application.updater is not None:
        await application.updater.start_polling()
    yield
    if application.updater is not None:
        await application.updater.stop()
    await application.stop()
    await application.shutdown()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend Accountability Engine integrating with Telegram via OTP and Financial Penalties.",
    version="4.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    return {"message": "WakeLock API is running", "docs": "/docs"}

@app.get("/health")
async def health_check():
    # Basic health check endpoint
    return {"status": "healthy"}
