import os
import nest_asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler
)
from aiohttp import web
from pymongo import MongoClient
from datetime import datetime, timedelta

from bot_commands import (
    start, add, shared, handle_split_or_owe, get_monthly,
    settle, show_shared, help_cmd,
    daily, weekly, fifteen
)

nest_asyncio.apply()

# --- Load env vars (or use os.environ) ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI", "YOUR_MONGO_URI")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "secretpath")
PORT = int(os.environ.get("PORT", "10000"))

# --- MongoDB Setup ---
client = MongoClient(MONGO_URI)
db = client.expense_bot
expenses = db.expenses
shared_expenses = db.shared_expenses

# --- Telegram Webhook Route ---
async def webhook_handler(request):
    update = await request.json()
    await application.update_queue.put(Update.de_json(update, application.bot))
    return web.Response()

# --- Telegram Bot Init ---
async def on_startup(app):
    webhook_url = f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/{WEBHOOK_SECRET}"
    await application.bot.set_webhook(webhook_url)
    print("✅ Webhook set:", webhook_url)

application = Application.builder().token(BOT_TOKEN).build()

# Register Handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("add", add))
application.add_handler(CommandHandler("shared", shared))
application.add_handler(CommandHandler("settle", settle))
application.add_handler(CommandHandler("show", show_shared))
application.add_handler(CommandHandler("daily", daily))
application.add_handler(CommandHandler("weekly", weekly))
application.add_handler(CommandHandler("15days", fifteen))
application.add_handler(CommandHandler("monthly", get_monthly))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(CallbackQueryHandler(handle_split_or_owe, pattern="^(split|owe)\|"))
application.add_handler(CallbackQueryHandler(clear_all, pattern="^clear_all$"))
application.add_handler(CallbackQueryHandler(show_shared, pattern="^show_shared$"))

# --- AIOHTTP App ---
web_app = web.Application()
web_app.router.add_post(f'/{WEBHOOK_SECRET}', webhook_handler)
web_app.on_startup.append(on_startup)

# --- Run Aiohttp App ---
if __name__ == '__main__':
    web.run_app(web_app, port=PORT)
