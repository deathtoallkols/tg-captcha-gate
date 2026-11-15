import os
import random
import logging
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ==============================
# CONFIGURATION
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN")
DESTINATION_BOT = os.getenv("DESTINATION_BOT", "https://t.me/WaveformProtocolBot")
DESTINATION_NAME = os.getenv("DESTINATION_NAME", "WaveformProtocolBot")

MAX_ATTEMPTS = 3
CHALLENGE_TIMEOUT = 120  # seconds

# ==============================
# LOGGING
# ==============================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ==============================
# CAPTCHA GENERATOR
# ==============================

def make_captcha():
    a = random.randint(2, 15)
    b = random.randint(2, 15)
    answer = a + b

    choices = {answer}
    while len(choices) < 4:
        wrong = answer + random.randint(-5, 5)
        if wrong > 0:
            choices.add(wrong)

    choices = list(choices)
    random.shuffle(choices)

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(str(c), callback_data=f"answer:{c}")] for c in choices]
    )

    message = (
        "🛡️ <b>Human Verification</b>\n\n"
        "Complete the quick security check below.\n\n"
        f"🧩 What is <b>{a} + {b}</b>?\n\n"
        "Choose the correct answer:"
    )
    return message, answer, keyboard

# ==============================
# HELPERS
# ==============================

def new_challenge(context, keep_attempts=False):
    message, answer, keyboard = make_captcha()
    attempts = context.user_data.get("attempts", 0) if keep_attempts else 0
    context.user_data["answer"] = answer
    context.user_data["attempts"] = attempts
    context.user_data["created"] = datetime.now(timezone.utc)
    return message, keyboard

# ==============================
# START COMMAND
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    welcome = (
        "👋 <b>Welcome!</b>\n\n"
        "Before continuing to our Telegram bot, "
        "please complete this quick human verification.\n\n"
        "🔐 This check helps reduce automated traffic.\n\n"
        "No passwords, Telegram login codes, "
        "or wallet information are required.\n\n"
        "<i>Independent community project.</i>"
    )
    await update.message.reply_text(welcome, parse_mode="HTML")

    message, keyboard = new_challenge(context)
    await update.message.reply_text(message, parse_mode="HTML", reply_markup=keyboard)

# ==============================
# VERIFY CAPTCHA
# ==============================

async def verify_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if "answer" not in context.user_data:
        await query.edit_message_text(
            "⏳ Verification expired.\n\nSend /start to try again."
        )
        return

    created = context.user_data.get("created")
    if not created or (datetime.now(timezone.utc) - created).total_seconds() > CHALLENGE_TIMEOUT:
        context.user_data.clear()
        await query.edit_message_text(
            "⏳ Your verification session expired.\n\nSend /start to try again."
        )
        return

    try:
        selected = int(query.data.split(":", 1)[1])
    except (IndexError, ValueError):
        return

    correct = context.user_data["answer"]

    # ---------- CORRECT ----------
    if selected == correct:
        context.user_data.clear()
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"🚀 Continue to {DESTINATION_NAME}", url=DESTINATION_BOT)]]
        )
        await query.edit_message_text(
            "✅ <b>Verification Successful!</b>\n\n"
            "You've successfully completed the human verification check.\n\n"
            "👇 Tap below to continue to the main bot.",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    # ---------- WRONG ----------
    context.user_data["attempts"] = context.user_data.get("attempts", 0) + 1
    attempts = context.user_data["attempts"]

    if attempts >= MAX_ATTEMPTS:
        context.user_data.clear()
        await query.edit_message_text(
            "❌ <b>Verification Failed</b>\n\n"
            f"You've used all {MAX_ATTEMPTS} attempts.\n\n"
            "Send /start to try again.",
            parse_mode="HTML",
        )
        return

    message, keyboard = new_challenge(context, keep_attempts=True)
    await query.edit_message_text(
        "❌ <b>Incorrect Answer</b>\n"
        f"Attempts remaining: <b>{MAX_ATTEMPTS - attempts}</b>\n\n" + message,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

# ==============================
# HELP COMMAND
# ==============================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 <b>Verification Bot Help</b>\n\n"
        "Send /start to begin verification.\n\n"
        "Complete the CAPTCHA to continue to the main bot.",
        parse_mode="HTML",
    )

# ==============================
# ERROR HANDLER
# ==============================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Bot error: %s", context.error, exc_info=context.error)

# ==============================
# MAIN
# ==============================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Add it to Railway environment variables.")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CallbackQueryHandler(verify_answer, pattern=r"^answer:"))
    application.add_error_handler(error_handler)

    logger.info("Verification bot started successfully.")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
