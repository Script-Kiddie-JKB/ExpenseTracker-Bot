import nest_asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes
)
from pymongo import MongoClient
from datetime import datetime, timedelta
from aiohttp import web

nest_asyncio.apply()

# --- ENV Credentials ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
RENDER_URL = os.getenv("RENDER_URL", "https://your-app-name.onrender.com")  # Replace

# --- MongoDB Setup ---
client = MongoClient(MONGO_URI)
db = client.expense_bot
expenses = db.expenses
shared_expenses = db.shared_expenses

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        text="""
*👋 Welcome to Expense Tracker Bot \\!*

📲 *Track & Share your Expenses Easily*

Here’s what I can help you with:

💵 *Personal Expenses*
`/add 150 lunch` — Quickly add your own spending

👥 *Shared Expenses*
`/shared 600 jai dinner swaraj` — Split or owe with others

📈 *Smart Summaries*
• `/daily` — _Today’s summary_  
• `/weekly` — _Last 7 days_  
• `/15days` — _Last 15 days_  
• `/monthly` — _This month’s report_

💰 *Settle Balances*
• `/settle` — _Who owes whom?_

📋 *Shared History*
• `/show` — _All shared entries_

🛠 *Help*
• `/help` — _All commands with examples_

_✨ Start tracking now and take control of your money \\!_
        """,
        parse_mode="MarkdownV2"
    )

# --- /add ---
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(context.args[0])
        category = " ".join(context.args[1:]) or "misc"
        entry = {
            "user_id": update.effective_user.id,
            "amount": amount,
            "category": category,
            "timestamp": datetime.utcnow()
        }
        expenses.insert_one(entry)
        await update.message.reply_text(f"✅ Added ₹{amount} for *{category}*", parse_mode="Markdown")
    except:
        await update.message.reply_text("❌ Usage: /add <amount> <category>")

# --- /shared ---
async def shared(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(context.args[0])
        payer = context.args[1]
        for i in range(2, len(context.args)):
            if len(context.args[i:]) > 1:
                continue
            description = " ".join(context.args[2:i])
            payees = context.args[i:]
            break
        else:
            raise ValueError("At least one payee required.")
    except Exception:
        await update.message.reply_text("❌ Usage: /shared <amount> <payer> <desc> <payee1> [<payee2>...]")
        return

    payees_str = ",".join(payees)
    keyboard = [
        [
            InlineKeyboardButton("➗ Split Equally", callback_data=f"split|{amount}|{payer}|{description}|{payees_str}"),
            InlineKeyboardButton("💯 Full Owe", callback_data=f"owe|{amount}|{payer}|{description}|{payees_str}"),
        ]
    ]
    await update.message.reply_text("How should this be split?", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Handle Split/Owe Button ---
async def handle_split_or_owe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, amount, payer, description, payees_str = query.data.split("|")
    payees = payees_str.split(",")
    amount = float(amount)
    split = action == "split"

    user_id = query.from_user.id
    entries = []
    for payee in payees:
        share = amount / len(payees) if split else amount
        shared_expenses.insert_one({
            "user_id": user_id,
            "amount": share,
            "payer": payer,
            "payee": payee,
            "description": description,
            "timestamp": datetime.utcnow(),
            "split": split
        })
        entries.append(f"*{payee}* {'owes' if not split else 'split'} ₹{share:.2f}")

    msg = f"✅ Recorded shared expense for *{description}*:\n• Paid by *{payer}*\n" + "\n".join(entries)
    await query.edit_message_text(msg, parse_mode="Markdown")

# --- Show Expenses ---
async def get_total(update: Update, context: ContextTypes.DEFAULT_TYPE, days: int):
    user_id = update.effective_user.id
    start_date = datetime.utcnow() - timedelta(days=days)
    entries = list(expenses.find({"user_id": user_id, "timestamp": {"$gte": start_date}}).sort("timestamp", 1))
    if not entries:
        await update.message.reply_text(f"No expenses found in last {days} day(s).")
        return

    lines = ["*Category-wise Expenses:*", "```"]
    total = 0
    for e in entries:
        date_str = e["timestamp"].strftime("%Y-%m-%d")
        lines.append(f"[{date_str}] {e['category']:<18}: ₹{e['amount']:.2f}")
        total += e["amount"]
    lines.append(f"\nTotal in last {days} day(s): ₹{total:.2f}")
    lines.append("```")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def get_monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    pipeline = [
        {"$match": {"user_id": user_id, "timestamp": {"$gte": start}}},
        {"$group": {"_id": "$category", "category_total": {"$sum": "$amount"}}},
        {"$sort": {"category_total": -1}}
    ]
    results = list(expenses.aggregate(pipeline))
    if not results:
        await update.message.reply_text("No expenses found for the current month.")
        return
    lines = ["*Category-wise Expenses for this month:*"]
    total = 0
    for r in results:
        lines.append(f"`{r['_id']:<12}` : ₹{r['category_total']:.2f}")
        total += r['category_total']
    lines.append(f"\n*Total this month:* ₹{total:.2f}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def settle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_balances(update.message.reply_text)

async def show_shared(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        responder = update.callback_query.message
        user_id = update.callback_query.from_user.id
    else:
        responder = update.message
        user_id = update.effective_user.id

    records = list(shared_expenses.find({"user_id": user_id}).sort("timestamp", -1))
    if not records:
        await responder.reply_text("No shared expenses found.")
        return

    lines = ["*📋 Shared Expense History:*"]
    for r in records:
        ts = r.get("timestamp", "N/A")
        date_str = ts.strftime("%d %b %Y") if isinstance(ts, datetime) else "Unknown"
        if r.get("split"):
            lines.append(f"• *{r['payer']}* paid ₹{r['amount']:.2f} ➝ *{r['payee']}* split for *{r['description']}* (`{date_str}`)")
        else:
            lines.append(f"• *{r['payer']}* paid ₹{r['amount']:.2f} ➝ *{r['payee']}* owes for *{r['description']}* (`{date_str}`)")

    keyboard = [[InlineKeyboardButton("✅ Settle Now", callback_data="settle_now")]]
    await responder.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_settle_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    await show_balances(update.callback_query.edit_message_text, user_id)
    await update.callback_query.answer()

async def clear_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    shared_expenses.delete_many({"user_id": user_id})
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("✅ All your shared expenses cleared.")

async def show_balances(responder, user_id):
    records = list(shared_expenses.find({"user_id": user_id}))
    if not records:
        await responder("No balances to show.")
        return
    balances = {}
    for r in records:
        amt = r["amount"] / 2 if r.get("split") else r["amount"]
        balances[r["payer"]] = balances.get(r["payer"], 0) + amt
        balances[r["payee"]] = balances.get(r["payee"], 0) - amt
    lines = ["*💰 Balance Summary:*"]
    for person, bal in balances.items():
        lines.append(f"*{person}*: {'gets' if bal > 0 else 'owes'} ₹{abs(bal):.2f}")
    keyboard = [[
        InlineKeyboardButton("🧹 Clear All", callback_data="clear_all"),
        InlineKeyboardButton("↩️ Back", callback_data="show_shared")
    ]]
    await responder("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""\
🤖 *Expense Tracker Help*

➕ /add <amount> <category>  
👥 /shared <amount> <payer> <desc> <payee1> [<payee2>...]  
📋 /show - View shared history  
💰 /settle - View balances  
📅 /daily - Show today’s expenses  
📈 /weekly - Last 7 days  
🗓️ /15days - Last 15 days  
📆 /monthly - This month  
❓ /help - Show this help

Example: `/shared 100 jai food swaraj`
""", parse_mode="Markdown")

# --- Shortcuts ---
async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE): await get_total(update, context, 1)
async def weekly(update: Update, context: ContextTypes.DEFAULT_TYPE): await get_total(update, context, 7)
async def fifteen(update: Update, context: ContextTypes.DEFAULT_TYPE): await get_total(update, context, 15)

# --- Webhook ---
application = Application.builder().token(BOT_TOKEN).build()
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
application.add_handler(CallbackQueryHandler(handle_settle_now, pattern="^settle_now$"))
application.add_handler(CallbackQueryHandler(clear_all, pattern="^clear_all$"))
application.add_handler(CallbackQueryHandler(show_shared, pattern="^show_shared$"))

web_app = web.Application()
web_app.router.add_post("/webhook", lambda req: webhook(req))

async def webhook(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return web.Response()

async def on_startup(app):
    await application.bot.set_webhook(f"{RENDER_URL}/webhook")

web_app.on_startup.append(on_startup)

if __name__ == "__main__":
    web.run_app(web_app, port=int(os.environ.get("PORT", 8080)))
