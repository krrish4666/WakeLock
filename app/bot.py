import datetime
from decimal import Decimal
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from app.core.config import settings
from app.core.database import AsyncSessionLocal

from app.services.wallet import WalletService
from app.services.plan import PlanService
from app.services.verification import VerificationService
from app.services.preferences import PreferencesService
from telegram.ext import MessageHandler, filters

# Initialize the bot application
application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        f"Hi {user.first_name}! Welcome to WakeLock.\n\n"
        "Commands:\n"
        "/deposit [amount] - Simulate a wallet deposit\n"
        "/plan [amount] [duration_days] - Setup a new wake plan\n"
        "/alarm [HH:MM] - Set your daily alarm time (e.g. 05:00)\n"
        "/buffer [minutes] - Set your morning buffer window before dropping OTP\n"
        "/withdraw - Withdraw your unlocked funds\n"
        "/balance - Check your virtual wallet"
    )

async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /deposit [amount]")
        return
        
    try:
        amount = Decimal(context.args[0])
    except:
        await update.message.reply_text("Invalid amount.")
        return

    async with AsyncSessionLocal() as db:
        wallet = await WalletService.deposit(db, update.effective_user.id, amount)
        await update.message.reply_text(f"[SUCCESS] Deposited Rs. {amount}. New Balance: Rs. {wallet.available_balance}")

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with AsyncSessionLocal() as db:
        wallet = await WalletService.get_or_create_wallet(db, update.effective_user.id)
        await update.message.reply_text(
            f"[WALLET] Virtual Wallet\n\n"
            f"Available: Rs. {wallet.available_balance}\n"
            f"Locked: Rs. {wallet.locked_balance}\n"
            f"Total: Rs. {wallet.total_balance}"
        )

async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /plan [amount] [duration_days]\nExample: /plan 100 7")
        return

    try:
        amount = Decimal(context.args[0])
        duration_days = int(context.args[1])
    except Exception as e:
        await update.message.reply_text("Invalid format. Use: /plan 100 7")
        return

    async with AsyncSessionLocal() as db:
        plan_or_err = await PlanService.create_plan(
            db=db,
            telegram_id=update.effective_user.id,
            amount=amount,
            duration_days=duration_days
        )
        if isinstance(plan_or_err, str):
            await update.message.reply_text(f"[ERROR] {plan_or_err}")
            return
            
        await update.message.reply_text(
            f"[SUCCESS] WakeLock Plan Activated!\n\n"
            f"Days: {duration_days}\n"
            f"Locked: Rs. {amount}\n"
            f"Penalty: Rs. {plan_or_err.per_day_penalty}/day\n"
            f"(Don't forget to set your alarm with /alarm HH:MM!)"
        )

async def alarm_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /alarm [HH:MM]\nExample: /alarm 05:00")
        return
        
    try:
        time_str = context.args[0]
        alarm_time = datetime.datetime.strptime(time_str, "%H:%M").time()
    except Exception as e:
        await update.message.reply_text("Invalid time format. Make sure to use 24-hour HH:MM format (e.g., 05:00, 14:30).")
        return
        
    async with AsyncSessionLocal() as db:
        res = await PreferencesService.set_alarm(db, update.effective_user.id, alarm_time)
        await update.message.reply_text(
            f"[SUCCESS] {res}\n\n"
            f"What buffer do you need (e.g., to freshen up, have tea, take a bath)?\n"
            f"Use /buffer [minutes] to set a delay before the OTP drops!"
        )

async def buffer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /buffer [minutes]\nExample: /buffer 20")
        return
        
    try:
        buffer_mins = int(context.args[0])
    except Exception as e:
        await update.message.reply_text("Invalid number of minutes.")
        return
        
    async with AsyncSessionLocal() as db:
        res = await PreferencesService.set_buffer(db, update.effective_user.id, buffer_mins)
        await update.message.reply_text(f"[SUCCESS] {res}")

async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with AsyncSessionLocal() as db:
        wallet = await WalletService.manual_withdraw(db, update.effective_user.id)
        if not wallet:
            await update.message.reply_text("[ERROR] No locked funds to withdraw.")
            return
        await update.message.reply_text(f"[SUCCESS] Withdrawal complete. Locked funds moved to available balance.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    
    # We only care about potential OTP codes (6 digits)
    if not (len(text) == 6 and text.isdigit()):
        await update.message.reply_text("I only understand commands and 6-digit OTP codes!")
        return
        
    async with AsyncSessionLocal() as db:
        response = await VerificationService.verify_user_otp(db, update.effective_user.id, text)
        await update.message.reply_text(response)

# Add handlers
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("deposit", deposit_command))
application.add_handler(CommandHandler("balance", balance_command))
application.add_handler(CommandHandler("plan", plan_command))
application.add_handler(CommandHandler("withdraw", withdraw_command))
application.add_handler(CommandHandler("alarm", alarm_command))
application.add_handler(CommandHandler("buffer", buffer_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    import logging
    logging.exception("Telegram bot error", exc_info=context.error)

application.add_error_handler(error_handler)

async def send_alert(user_id: int, message: str) -> None:
    from telegram import Bot
    async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
        await bot.send_message(chat_id=user_id, text=message)
