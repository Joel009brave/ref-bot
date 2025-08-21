import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)

# 🔹 Environment Variables
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
REF_CHANNEL = os.getenv("REF_CHANNEL")  # @darktunnel_ssh_tm
GIFT_CHANNEL = os.getenv("GIFT_CHANNEL")  # @kingvvod

DATA_FILE = "data.json"

# 🔹 JSON management
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# 🔹 Start / Referral
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    data = load_data()

    # Kullanıcıyı kaydet
    if str(user.id) not in data:
        data[str(user.id)] = {"username": user.username, "balance": 0, "refs": []}

    # Referal varsa işleme
    if args:
        ref_id = args[0]
        if ref_id != str(user.id) and ref_id in data:
            if str(user.id) not in data[ref_id]["refs"]:
                data[ref_id]["refs"].append(str(user.id))
                data[ref_id]["balance"] += 2
                await context.bot.send_message(
                    chat_id=ref_id,
                    text=f"🎉 Size täze referal geldi: @{user.username or user.id}"
                )

    save_data(data)

    # Klavye
    keyboard = [
        [InlineKeyboardButton("💰 Balans", callback_data="balance")],
        [InlineKeyboardButton("🏆 Top 10", callback_data="top10")],
        [InlineKeyboardButton("🎁 Sowgatlarym", callback_data="gifts")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Hoş geldiň, {user.first_name}!\n\n"
        f"📌 Referal linkiň: https://t.me/{context.bot.username}?start={user.id}",
        reply_markup=reply_markup
    )

# 🔹 Button / Callback handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = load_data()
    user = query.from_user
    user_data = data.get(str(user.id), {"balance": 0, "refs": []})

    if query.data == "balance":
        await query.edit_message_text(f"💰 Balansyň: {user_data['balance']} bal")

    elif query.data == "top10":
        sorted_users = sorted(data.items(), key=lambda x: x[1]["balance"], reverse=True)[:10]
        text = "🏆 Top 10 Bal boýunça:\n"
        for i, (uid, udata) in enumerate(sorted_users, start=1):
            text += f"{i}. @{udata['username']} — {udata['balance']} bal\n"
        await query.edit_message_text(text)

    elif query.data == "gifts":
        keyboard = [
            [InlineKeyboardButton("30 bal = 3 TMT", callback_data="gift_30")],
            [InlineKeyboardButton("60 bal = 6 TMT", callback_data="gift_60")],
            [InlineKeyboardButton("120 bal = 12 TMT", callback_data="gift_120")],
            [InlineKeyboardButton("240 bal = 24 TMT", callback_data="gift_240")],
            [InlineKeyboardButton("480 bal = 48 TMT", callback_data="gift_480")]
        ]
        await query.edit_message_text("🎁 Sowgat saýla:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("gift_"):
        amount = int(query.data.split("_")[1])
        reward_map = {30: 3, 60: 6, 120: 12, 240: 24, 480: 48}

        if user_data["balance"] >= amount:
            user_data["balance"] -= amount
            save_data(data)
            await context.bot.send_message(
                chat_id=GIFT_CHANNEL,
                text=f"🎁 @{user.username} {reward_map[amount]} TMT sowgady talap etdi. Adminiň tassyklamagyny garaşýar."
            )
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"✅ @{user.username} {reward_map[amount]} TMT sowgady talap etdi. Tassyklamaga garaşýar."
            )
            await query.edit_message_text("✅ Sowgad talabyň ugradylýar, adminiň tassyklamagyny garaşaň.")
        else:
            await query.edit_message_text("⚠️ Balansyň ýeterlik däl!")

# 🔹 Admin log
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    data = load_data()
    text = "📋 Referal Log:\n\n"
    for uid, udata in data.items():
        text += f"👤 @{udata['username']} | ID: {uid} | Bal: {udata['balance']} | Refs: {len(udata['refs'])}\n"
    await update.message.reply_text(text)

# 🔹 Run bot
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()            save_data(data)
            await context.bot.send_message(
                chat_id=GIFT_CHANNEL,
                text=f"🎁 @{user.username} {reward_map[amount]} TMT sowgady talap etdi. "
                     f"Adminiň tassyklamagyny garaşýar."
            )
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"✅ @{user.username} {reward_map[amount]} TMT sowgady talap etdi. Tassyklamaga garaşýar."
            )
            await query.edit_message_text("✅ Sowgad talabyň ugradylýar, adminiň tassyklamagyny garaşaň.")
        else:
            await query.edit_message_text("⚠️ Balansyň ýeterlik däl!")

# 🔹 Admin üçin log
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    data = load_data()
    text = "📋 Referal Log:\n\n"
    for uid, udata in data.items():
        text += f"👤 @{udata['username']} | ID: {uid} | Bal: {udata['balance']} | Refs: {len(udata['refs'])}\n"
    await update.message.reply_text(text)

# 🔹 Run Bot
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start", ref_system))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling()

if __name__ == "__main__":
    main()
