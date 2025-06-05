# main.py
import os
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)
from pymongo import MongoClient

from bot_commands import (
    start,
    add,
    shared,
    handle_split_or_owe,
    handle_settle_now,
    get_monthly,
    settle,
    show_shared,
    help_cmd,
    clear_all,
    daily,
    weekly,
    fifteen,
)

# Load environment
BOT_TOKEN      = os.environ["BOT_TOKEN"]
MONGO_URI      = os.environ["MONGO_URI"]
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "secretpath")
PORT           = int(os.environ.get("PORT", "10000"))
HOSTNAME       = os.environ["RENDER_EXTERNAL_HOSTNAME"]

# Mongo client (shared with bot_commands.py, but this ensures the DB is awake)
MongoClient(MONGO_URI)

# Build the Application
app = Application.builder().token(BOT_TOKEN).build()

# Register command handlers
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

# Register callback/query handlers
app.add_handler(CallbackQueryHandler(handle_split_or_owe, pattern="^(split|owe)\|"))
app.add_handler(CallbackQueryHandler(handle_settle_now, pattern="^settle_now$"))
app.add_handler(CallbackQueryHandler(clear_all, pattern="^clear_all$"))
app.add_handler(CallbackQueryHandler(show_shared, pattern="^show_shared$"))

if __name__ == "__main__":
    # Build your public webhook URL
    webhook_url = f"https://{HOSTNAME}/{WEBHOOK_SECRET}"
    print("▶️ Starting webhook server on port", PORT)
    print("▶️ Setting Telegram webhook to:", webhook_url)

    # run_webhook spins up its own aiohttp server,
    # sets the webhook for you, and binds to PORT.
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_SECRET,
        webhook_url=webhook_url,
    )
