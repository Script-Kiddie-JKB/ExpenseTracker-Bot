import os
import nest_asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler
)
from bot_commands import (
    start, add, shared, settle, show_shared, help_cmd, clear_all,
    handle_split_or_owe, handle_settle_now, get_monthly,
    daily, weekly, fifteen
)

nest_asyncio.apply()

# --- Load env vars ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "secretpath")
PORT = int(os.environ.get("PORT", 10000))
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")

# --- App Setup ---
app = Application.builder().token(BOT_TOKEN).build()

# --- Command Handlers ---
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add))
app.add_handler(CommandHandler("shared", shared))
app.add_handler(CommandHandler("settle", settle))
app.add_handler(CommandHandler("show", show_shared))
app.add_handler(CommandHandler("daily", daily))
app.add_handler(CommandHandler("weekly", weekly))
app.add_handler(CommandHandler("15days", fifteen))
app.add_handler(CommandHandler("monthly", get_monthly))
app.add_handler(CommandHandler("help", help_cmd))

# --- Callback Handlers ---
app.add_handler(CallbackQueryHandler(handle_split_or_owe, pattern="^(split|owe)\|"))
app.add_handler(CallbackQueryHandler(handle_settle_now, pattern="^settle_now$"))
app.add_handler(CallbackQueryHandler(clear_all, pattern="^clear_all$"))
app.add_handler(CallbackQueryHandler(show_shared, pattern="^show_shared$"))

# --- Webhook ---
webhook_url = f"https://{RENDER_EXTERNAL_HOSTNAME}/{WEBHOOK_SECRET}"
print(f"▶️ Starting webhook server on port {PORT}")
print(f"▶️ Setting Telegram webhook to: {webhook_url}")

if __name__ == "__main__":
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=webhook_url
    )
