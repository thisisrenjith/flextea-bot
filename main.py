
from flask import Flask, request
import os
import asyncio
import re
from telegram import Update, Bot, constants
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# --- Config ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

app = Flask(__name__)
bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

verified_users = {}
user_groups = {}
message_inbox = {}
comfort_queue = {}

CATEGORIES = ["Gossip", "Suggestion", "Complaint", "Appreciation"]
AUDIENCES = ["My Office", "A Specific Store", "A Specific Team", "All Flexway"]

def emotion_shield(text):
    rude_words = ["sucks", "hate", "stupid", "idiot", "trash", "useless", "dog"]
    if any(w in text.lower() for w in rude_words):
        return False
    if re.search(r"\b(hr|admin|finance|manager|it)\b.*\b(sucks|lazy|idiot|trash)\b", text.lower()):
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to FlexTea 🍵\nPlease reply with your Office/Store/Team name.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in verified_users:
        verified_users[user_id] = True
        user_groups[user_id] = {"group": text}
        await update.message.reply_text(f"✅ You’re verified under: {text}")
        return

    if text.lower() == "/spill":
        cats = "\n".join([f"{i+1}. {c}" for i, c in enumerate(CATEGORIES)])
        await update.message.reply_text(f"What would you like to post?\n{cats}")
        return

    if text.isdigit() and int(text) in range(1, len(CATEGORIES)+1):
        verified_users[user_id] = {"category": CATEGORIES[int(text)-1]}
        auds = "\n".join([f"{i+1}. {a}" for i, a in enumerate(AUDIENCES)])
        await update.message.reply_text(f"Who should see this message?\n{auds}")
        return

    if isinstance(verified_users[user_id], dict):
        data = verified_users[user_id]
        if "category" in data and "audience" not in data and text.isdigit() and int(text) in range(1, len(AUDIENCES)+1):
            data["audience"] = AUDIENCES[int(text)-1]
            await update.message.reply_text("Type your message now:")
            return

        if "audience" in data:
            if not emotion_shield(text):
                await update.message.reply_text("⚠️ Please rephrase respectfully.")
                return

            msg_id = f"MSG{len(message_inbox)+1}"
            message_inbox[msg_id] = user_id
            comfort_queue[msg_id] = []

            audience = data["audience"]
            group = user_groups[user_id]["group"]
            targets = [uid for uid, g in user_groups.items()
                       if audience == "All Flexway" or g["group"] == group]

            for t_id in targets:
                if t_id != user_id:
                    try:
                        await context.bot.send_message(
                            chat_id=t_id,
                            text=f"🍵 *{data['category']}* #{msg_id}\n{text}\n\nReply anonymously? Type: /reply {msg_id}",
                            parse_mode=constants.ParseMode.MARKDOWN
                        )
                    except:
                        pass

            await update.message.reply_text("✅ Your message was posted anonymously.")
            verified_users[user_id] = True
            return

    if text.startswith("/reply"):
        parts = text.split()
        if len(parts) == 2 and parts[1] in message_inbox:
            comfort_queue[parts[1]].append((user_id, "Pending reply"))
            await update.message.reply_text("✏️ Type your anonymous reply now:")
            return
        await update.message.reply_text("❌ Invalid format. Use /reply MSG1")
        return

    for msg_id, replies in comfort_queue.items():
        for i, (uid, status) in enumerate(replies):
            if uid == user_id and status == "Pending reply":
                comfort_queue[msg_id][i] = (uid, text)
                original_user = message_inbox[msg_id]
                await context.bot.send_message(chat_id=original_user,
                                               text=f"💌 Anonymous reply to #{msg_id}:\n{text}")
                await update.message.reply_text("✅ Your reply was sent anonymously.")
                return

bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.route('/')
def home():
    return "✅ FlexTeaBot is running"

@app.route(f"/webhook/<token>", methods=["POST"])
async def webhook(token):
    if token != BOT_TOKEN:
        return {"error": "Unauthorized"}, 403
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}

@app.before_first_request
def setup_webhook():
    bot = Bot(BOT_TOKEN)
    asyncio.run(bot.set_webhook(WEBHOOK_URL))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
