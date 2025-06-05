require('dotenv').config();
const TelegramBot = require('node-telegram-bot-api');
const { MongoClient } = require('mongodb');
const express = require('express');

const BOT_TOKEN = process.env.BOT_TOKEN;
const MONGO_URI = process.env.MONGO_URI;

const app = express();
const PORT = process.env.PORT || 3000;

app.get('/', (req, res) => res.send('Bot is running'));

app.listen(PORT, () => console.log(`Server listening on port ${PORT}`));

const client = new MongoClient(MONGO_URI);
let db;

async function startBot() {
  try {
    await client.connect();
    db = client.db('expense_bot');
    console.log('Connected to MongoDB');

    const bot = new TelegramBot(BOT_TOKEN, { polling: true });

    // Format date as YYYY-MM-DD
    function formatDate(date) {
      return date.toISOString().split('T')[0];
    }

    // Escape markdown special chars for Telegram
    function escapeMarkdown(text) {
      if (!text) return '';
      return text.replace(/[_*[\]()~`>#+\-=|{}.!\\]/g, '\\$&');
    }

    bot.onText(/\/start/, (msg) => {
      const chatId = msg.chat.id;
      const text = `
*👋 Welcome to Expense Tracker Bot!*
📲 *Track & Share your Expenses Easily*

Here’s what I can help you with:

💵 *Personal Expenses*
\`/add 150 lunch\` — Quickly add your own spending

👥 *Shared Expenses*
\`/shared 600 jai dinner swaraj\` — Split or owe with others

📈 *Smart Summaries*
• \`/daily\` — _Today’s summary_
• \`/weekly\` — _Last 7 days_
• \`/15days\` — _Last 15 days_
• \`/monthly\` — _This month’s report_

💰 *Settle Balances*
• \`/settle\` — _Who owes whom?_

📋 *Shared History*
• \`/show\` — _All shared entries_

🛠 *Help*
• \`/help\` — _All commands with examples_

_✨ Start tracking now and take control of your money!_
`;
      bot.sendMessage(chatId, text, { parse_mode: 'Markdown' });
    });

    bot.onText(/\/add$/, (msg) => {
      const chatId = msg.chat.id;
      const text = `
*Usage:* /add <amount> <category>

*Example:* /add 150 lunch
`;
      bot.sendMessage(chatId, text, { parse_mode: 'Markdown' });
    });

    bot.onText(/\/add (\d+\.?\d*) (.+)/, async (msg, match) => {
      const chatId = msg.chat.id;
      const amount = parseFloat(match[1]);
      const category = match[2];

      try {
        await db.collection('expenses').insertOne({
          user_id: msg.from.id,
          amount: amount,
          category: category,
          timestamp: new Date()
        });
        bot.sendMessage(chatId, `✅ Added ₹${amount} for *${escapeMarkdown(category)}*`, { parse_mode: 'Markdown' });
      } catch (err) {
        console.error('Error adding expense:', err);
        bot.sendMessage(chatId, '❌ Error adding expense');
      }
    });

    // Improved shared command parser - expects /shared <amount> <payer> <description> <payee1> [<payee2> ...]
    bot.onText(/\/shared (\d+\.?\d*) (\w+) (.+)/, async (msg, match) => {
      const chatId = msg.chat.id;
      const amount = parseFloat(match[1]);
      const payer = match[2];
      // The rest is description and payees, split on quotes or spaces carefully

      // Try to split description and payees by quotes or last space groups
      let rest = match[3].trim();

      // Try to extract description inside quotes if present
      let description = '';
      let payeesPart = '';

      const quotedDescMatch = rest.match(/^"([^"]+)"\s*(.*)$/);
      if (quotedDescMatch) {
        description = quotedDescMatch[1];
        payeesPart = quotedDescMatch[2];
      } else {
        // No quotes, split by last space group
        const parts = rest.split(/\s+/);
        if (parts.length < 2) {
          bot.sendMessage(chatId, '❌ Invalid format. Usage: /shared <amount> <payer> <description> <payee1> [<payee2> ...]');
          return;
        }
        description = parts.slice(0, parts.length - 1).join(' ');
        payeesPart = parts.slice(parts.length - 1).join(' ');
      }

      const payees = payeesPart.split(/\s+/).filter(Boolean);

      if (!description || payees.length === 0) {
        bot.sendMessage(chatId, '❌ Invalid format. Usage: /shared <amount> <payer> <description> <payee1> [<payee2> ...]');
        return;
      }

      const keyboard = {
        inline_keyboard: [
          [
            { text: '➗ Split Equally', callback_data: `split|${amount}|${payer}|${description}|${payees.join(',')}` },
            { text: '💯 Full Owe', callback_data: `owe|${amount}|${payer}|${description}|${payees.join(',')}` }
          ],
          [{ text: '❌ Close', callback_data: 'close' }]
        ]
      };

      bot.sendMessage(chatId, 'How should this be split?', { reply_markup: keyboard });
    });

    bot.onText(/\/shared$/, (msg) => {
      const chatId = msg.chat.id;
      const text = `
*Usage:* /shared <amount> <payer> <description> <payee1> [<payee2> ...]
*Example:* /shared 60 akash "lunch office" jai swaraj
`;
      bot.sendMessage(chatId, text, { parse_mode: 'Markdown' });
    });

    bot.on('callback_query', async (query) => {
      const chatId = query.message.chat.id;
      const data = query.data.split('|');

      try {
        const action = data[0];

        if (action === 'split' || action === 'owe' || action.startsWith('split_')) {
          if (data.length < 5) throw new Error('Invalid callback data format');

          const amount = parseFloat(data[1]);
          const payer = data[2];
          const description = data[3];
          let payees = data[4].split(',');

          if (action === 'split') {
            const keyboard = {
              inline_keyboard: [
                [
                  { text: 'Include Payer', callback_data: `split_include|${amount}|${payer}|${description}|${payees.join(',')}` },
                  { text: 'Exclude Payer', callback_data: `split_exclude|${amount}|${payer}|${description}|${payees.join(',')}` }
                ],
                [{ text: '❌ Close', callback_data: 'close' }]
              ]
            };
            await bot.editMessageText('Should the payer be included in the split?', {
              chat_id: chatId,
              message_id: query.message.message_id,
              reply_markup: keyboard
            });
          } else if (action === 'split_include' || action === 'split_exclude') {
            const totalPeople = action === 'split_include' ? payees.length + 1 : payees.length;
            const share = amount / totalPeople;

            if (action === 'split_include') {
              payees.push(payer);
            }

            const entries = [];
            for (const payee of payees) {
              await db.collection('shared_expenses').insertOne({
                user_id: query.from.id,
                amount: share,
                payer,
                payee,
                description,
                timestamp: new Date(),
                split: true
              });
              entries.push(`*${escapeMarkdown(payee)}* split ₹${share.toFixed(2)}`);
            }

            const msg = `✅ Recorded shared expense for *${escapeMarkdown(description)}*:\n• Paid by *${escapeMarkdown(payer)}*\n• Total split among ${totalPeople} people\n${entries.join('\n')}`;
            await bot.editMessageText(msg, { chat_id: chatId, message_id: query.message.message_id, parse_mode: 'Markdown' });
          } else if (action === 'owe') {
            const entries = [];
            for (const payee of payees) {
              const share = amount;
              await db.collection('shared_expenses').insertOne({
                user_id: query.from.id,
                amount: share,
                payer,
                payee,
                description,
                timestamp: new Date(),
                split: false
              });
              entries.push(`*${escapeMarkdown(payee)}* owes ₹${share.toFixed(2)}`);
            }
            const msg = `✅ Recorded shared expense for *${escapeMarkdown(description)}*:\n• Paid by *${escapeMarkdown(payer)}*\n${entries.join('\n')}`;
            await bot.editMessageText(msg, { chat_id: chatId, message_id: query.message.message_id, parse_mode: 'Markdown' });
          }
        } else if (query.data === 'settle_now') {
          await showBalances(chatId, query.from.id);
        } else if (query.data === 'clear_all') {
          await db.collection('shared_expenses').deleteMany({ user_id: query.from.id });
          await bot.editMessageText('✅ All your shared expenses cleared.', { chat_id: chatId, message_id: query.message.message_id });
        } else if (query.data === 'show_shared') {
          await bot.deleteMessage(chatId, query.message.message_id);
          await showSharedExpenses(chatId, query.from.id);
        } else if (query.data === 'close') {
          await bot.deleteMessage(chatId, query.message.message_id);
        }
      } catch (err) {
        console.error('Error handling callback query:', err);
        await bot.answerCallbackQuery(query.id, { text: '❌ An error occurred while processing your request.' });
      }
    });

    // Show total expense in last N days
    async function getTotal(chatId, userId, days) {
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - days);

      const entries = await db.collection('expenses').find({
        user_id: userId,
        timestamp: { $gte: startDate }
      }).sort({ timestamp: 1 }).toArray();

      if (entries.length === 0) {
        await bot.sendMessage(chatId, `No expenses found in the last ${days} day(s).`);
        return;
      }

      let total = 0;
      const lines = ['*Category-wise Expenses:*', '```'];
      entries.forEach(e => {
        const dateStr = formatDate(e.timestamp);
        const cat = e.category;
        const amt = e.amount;
        total += amt;
        lines.push(`[${dateStr}] ${cat.padEnd(18)}: ₹${amt.toFixed(2)}`);
      });
      lines.push(`\nTotal in the last ${days} day(s): ₹${total.toFixed(2)}`);
      lines.push('```');
      await bot.sendMessage(chatId, lines.join('\n'), { parse_mode: 'Markdown' });
    }

    bot.onText(/\/daily/, (msg) => getTotal(msg.chat.id, msg.from.id, 1));
    bot.onText(/\/weekly/, (msg) => getTotal(msg.chat.id, msg.from.id, 7));
    bot.onText(/\/15days/, (msg) => getTotal(msg.chat.id, msg.from.id, 15));

    bot.onText(/\/monthly/, async (msg) => {
      const chatId = msg.chat.id;
      const userId = msg.from.id;
      const start = new Date();
      start.setDate(1);
      start.setHours(0, 0, 0, 0);

      const results = await db.collection('expenses').aggregate([
        { $match: { user_id: userId, timestamp: { $gte: start } } },
        { $group: { _id: '$category', category_total: { $sum: '$amount' } } },
        { $sort: { category_total: -1 } }
      ]).toArray();

      if (results.length === 0) {
        await bot.sendMessage(chatId, 'No expenses found for the current month.');
        return;
      }

      let total = 0;
      const lines = ['*Category-wise Expenses for this month:*'];
      results.forEach(r => {
        const cat = r._id;
        const amt = r.category_total;
        lines.push(`\`${cat.padEnd(12)}\` : ₹${amt.toFixed(2)}`);
        total += amt;
      });
      lines.push(`\n*Total this month:* ₹${total.toFixed(2)}`);
      await bot.sendMessage(chatId, lines.join('\n'), { parse_mode: 'Markdown' });
    });

    bot.onText(/\/settle/, (msg) => showBalances(msg.chat.id, msg.from.id));

    async function showSharedExpenses(chatId, userId) {
      const records = await db.collection('shared_expenses').find({ user_id: userId }).sort({ timestamp: -1 }).toArray();
      if (records.length === 0) {
        await bot.sendMessage(chatId, 'No shared expenses found.');
        return;
      }

      const lines = ['*📋 Shared Expense History:*', '```'];
      records.forEach(r => {
        const payer = escapeMarkdown(r.payer);
        const payee = escapeMarkdown(r.payee);
        const amt = r.amount;
        const desc = escapeMarkdown(r.description);
        const split = r.split;
        const dateStr = formatDate(r.timestamp);

        if (split) {
          lines.push(`• *${payer}* paid ₹${amt.toFixed(2)} ➝ *${payee}* split for *${desc}* (\`${dateStr}\`)`);
        } else {
          lines.push(`• *${payer}* paid ₹${amt.toFixed(2)} ➝ *${payee}* owes for *${desc}* (\`${dateStr}\`)`);
        }
      });
      lines.push('```');

      const keyboard = {
        inline_keyboard: [
          [
            { text: '✅ Settle Now', callback_data: 'settle_now' },
            { text: '❌ Close', callback_data: 'close' }
          ]
        ]
      };

      await bot.sendMessage(chatId, lines.join('\n'), { parse_mode: 'Markdown', reply_markup: keyboard });
    }

    async function showBalances(chatId, userId) {
      const records = await db.collection('shared_expenses').find({ user_id: userId }).toArray();
      if (records.length === 0) {
        await bot.sendMessage(chatId, 'No balances to show.');
        return;
      }

      const balances = {};
      records.forEach(r => {
        const payer = r.payer;
        const payee = r.payee;
        const amt = r.amount;
        balances[payer] = (balances[payer] || 0) + amt;
        balances[payee] = (balances[payee] || 0) - amt;
      });

      const lines = ['*💰 Balance Summary:*'];
      for (const [person, bal] of Object.entries(balances)) {
        lines.push(`*${escapeMarkdown(person)}*: ${bal > 0 ? 'gets' : 'owes'} ₹${Math.abs(bal).toFixed(2)}`);
      }

      const keyboard = {
        inline_keyboard: [
          [
            { text: '🧹 Clear All', callback_data: 'clear_all' },
            { text: '↩️ Back', callback_data: 'show_shared' },
            { text: '❌ Close', callback_data: 'close' }
          ]
        ]
      };

      await bot.sendMessage(chatId, lines.join('\n'), { parse_mode: 'Markdown', reply_markup: keyboard });
    }

    bot.onText(/\/help/, (msg) => {
      const chatId = msg.chat.id;
      const text = `
🤖 *Expense Tracker Help*

➕ /add <amount> <category>
👥 /shared <amount> <payer> <description> <payee1> [<payee2> ...]
📋 /show - View shared history
💰 /settle - View balances
📅 /daily - Show today’s expenses
📈 /weekly - Last 7 days
🗓️ /15days - Last 15 days
📆 /monthly - This month
❓ /help - Show this help

Example: \`/shared 100 jai "lunch office" swaraj\`
`;
      bot.sendMessage(chatId, text, { parse_mode: 'Markdown' });
    });

    bot.onText(/\/show/, (msg) => showSharedExpenses(msg.chat.id, msg.from.id));

    console.log('Bot is running...');

  } catch (err) {
    console.error('Error starting bot:', err);
  }
}

startBot();
