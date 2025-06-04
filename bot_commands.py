from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime, timedelta
from pymongo import MongoClient
import os

# --- Mongo Setup ---
client = MongoClient(os.environ["MONGO_URI"])
db = client.expense_bot
expenses = db.expenses
shared_expenses = db.shared_expenses

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        text="""
👋 *Welcome to Expense Tracker Bot!*

💵 `/add 150 lunch` — Add your own expense  
👥 `/shared 600 jai dinner swaraj` — Shared expense  
📈 `/daily`, `/weekly`, `/15days`, `/monthly` — Reports  
💰 `/settle` — See who owes whom  
📋 `/show` — Shared history  
🛠 `/help` — All commands

✨ Start tracking now and control your money!
        """,
        parse_mode="Markdown"
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
            InlineKeyboardButton("💯 Full Owe", callback_data=f"owe|{amount}|{payer}|{description}|{payees_str}")
        ]
    ]
    await update.message.reply_text("How should this be split?", reply_markup=InlineKeyboardMarkup(keyboard))

# --- Callback: Split or Owe ---
async def handle_split_or_owe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, amount, payer, description, payees_str = query.data.split("|")
    payees = payees_str.split(",")
    amount = float(amount)
    split = action == "split"
    user_id = query.from_user.id

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

    entries = [
        f"*{payee}* {'owes' if not split else 'split'} ₹{amount / len(payees) if split else amount:.2f}"
        for payee in payees
    ]
    msg = f"✅ Recorded shared expense for *{description}*:\n• Paid by *{payer}*\n" + "\n".join(entries)
    await query.edit_message_text(msg, parse_mode="Markdown")

# --- /daily, /weekly, /15days, /monthly ---
async def get_total(update: Update, context: ContextTypes.DEFAULT_TYPE, days: int):
    user_id = update.effective_user.id
    start_date = datetime.utcnow() - timedelta(days=days)
    entries = list(expenses.find({
        "user_id": user_id,
        "timestamp": {"$gte": start_date}
    }).sort("timestamp", 1))

    if not entries:
        await update.message.reply_text(f"No expenses found in last {days} day(s).")
        return

    lines = ["*Category-wise Expenses:*", "```"]
    total = 0
    for e in entries:
        date_str = e["timestamp"].strftime("%Y-%m-%d")
        lines.append(f"[{date_str}] {e['category']:<18}: ₹{e['amount']:.2f}")
        total += e['amount']
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

# --- /show ---
async def show_shared(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    records = list(shared_expenses.find({"user_id": user_id}).sort("timestamp", -1))
    if not records:
        await update.message.reply_text("No shared expenses found.")
        return

    lines = ["*📋 Shared Expense History:*"]
    for r in records:
        payer, payee, amt, desc, split = r["payer"], r["payee"], r["amount"], r["description"], r["split"]
        ts = r["timestamp"].strftime("%d %b %Y")
        lines.append(
            f"• *{payer}* paid ₹{amt:.2f} ➝ *{payee}* {'split' if split else 'owes'} for *{desc}* (`{ts}`)"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# --- /settle ---
async def settle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_balances(update.message.reply_text, update.effective_user.id)

# --- Balance Summary ---
async def show_balances(responder, user_id):
    records = list(shared_expenses.find({"user_id": user_id}))
    if not records:
        await responder("No balances to show.")
        return

    balances = {}
    for r in records:
        payer, payee = r["payer"], r["payee"]
        amt = r["amount"] / 2 if r.get("split") else r["amount"]
        balances[payer] = balances.get(payer, 0) + amt
        balances[payee] = balances.get(payee, 0) - amt

    lines = ["*💰 Balance Summary:*"]
    for person, bal in balances.items():
        lines.append(f"*{person}*: {'gets' if bal > 0 else 'owes'} ₹{abs(bal):.2f}")
    await responder("\n".join(lines), parse_mode="Markdown")

# --- /help ---
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
