import os
import time
import threading
import logging
from flask import Flask

# === ENV DEBUG - DO NOT REMOVE ===
print("=== ENV DEBUG ===")
print("All env keys:", list(os.environ.keys()))
BOT_TOKEN = (
    os.getenv("TELEGRAM_TOKEN") or 
    os.getenv("BOT_TOKEN") or 
    os.getenv("TELEGRAM_BOT_TOKEN") or 
    os.getenv("TOKEN") or
    os.getenv("BOT_TOKEN".strip())
)
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or os.getenv("ADMIN_ID")
IQ_EMAIL = os.getenv("IQ_EMAIL") or os.getenv("IQOPTION_EMAIL")
IQ_PASSWORD = os.getenv("IQ_PASSWORD") or os.getenv("IQOPTION_PASSWORD")
ACCOUNT_TYPE = os.getenv("ACCOUNT_TYPE", "PRACTICE")

print(f"BOT_TOKEN exists? {bool(BOT_TOKEN)} - len: {len(BOT_TOKEN) if BOT_TOKEN else 0}")
print(f"CHAT_ID exists? {bool(CHAT_ID)}")
print(f"IQ_EMAIL exists? {bool(IQ_EMAIL)}")
print(f"ACCOUNT_TYPE: {ACCOUNT_TYPE}")

if not BOT_TOKEN:
    print("!!! FATAL: No token found in Environment Variables !!!")
    print("Go to Render -> Environment -> Add TELEGRAM_TOKEN and BOT_TOKEN -> Save Changes -> Clear cache & deploy")
    # Keep alive to show logs
    app = Flask(__name__)
    @app.route('/')
    def home():
        return "ERROR: BOT_TOKEN MISSING - Check Render Environment Variables", 500
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
    exit()

if not CHAT_ID:
    print("WARNING: CHAT_ID missing, bot will start but cannot send signals")

# === FLASK FOR RENDER HEALTH CHECK ===
app = Flask(__name__)
@app.route('/')
def home():
    return "KEVIN V25 LIVE - Bot is running", 200

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# === TELEGRAM BOT V25 ===
from telegram import Bot
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram import Update

# IQ Option API
try:
    from iqoptionapi.stable_api import IQ_Option
    IQ_AVAILABLE = True
except Exception as e:
    print(f"IQ API not available: {e}")
    IQ_AVAILABLE = False

bot_instance = Bot(token=BOT_TOKEN)

def start_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🚀 *KEVIN V25 ONLINE*\n\n"
        "Commands:\n"
        "/start - Check bot\n"
        "/status - Bot status\n"
        "/balance - IQ Balance\n"
        "/signal - Manual signal\n\n"
        "Bot is running 24/7 on Render",
        parse_mode='Markdown'
    )

def status_command(update: Update, context: CallbackContext):
    update.message.reply_text(f"✅ KEVIN V25 LIVE\nAccount: {ACCOUNT_TYPE}\nIQ Connected: {IQ_AVAILABLE}")

def balance_command(update: Update, context: CallbackContext):
    if not IQ_AVAILABLE or not IQ_EMAIL:
        update.message.reply_text("IQ credentials not set")
        return
    try:
        iq = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
        check, reason = iq.connect()
        if check:
            iq.change_balance(ACCOUNT_TYPE)
            bal = iq.get_balance()
            update.message.reply_text(f"💰 Balance ({ACCOUNT_TYPE}): ${bal}")
        else:
            update.message.reply_text(f"Connection failed: {reason}")
    except Exception as e:
        update.message.reply_text(f"Error: {e}")

def send_telegram_message(text):
    try:
        if CHAT_ID and BOT_TOKEN:
            bot_instance.send_message(chat_id=CHAT_ID, text=text, parse_mode='Markdown')
            print(f"Sent: {text[:50]}...")
    except Exception as e:
        print(f"Telegram send error: {e}")

def main():
    print("=== KEVIN V25 STARTING ===")
    # Start Flask in background
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"Flask started on port {os.environ.get('PORT', 10000)}")
    
    # Start Telegram polling
    try:
        updater = Updater(BOT_TOKEN, use_context=True)
        dp = updater.dispatcher
        dp.add_handler(CommandHandler("start", start_command))
        dp.add_handler(CommandHandler("status", status_command))
        dp.add_handler(CommandHandler("balance", balance_command))
        
        print("Telegram polling started")
        send_telegram_message("✅ *KEVIN V25 ONLINE*\nBot restarted and live on Render!")
        
        updater.start_polling()
        print("=== KEVIN V25 LIVE ===")
        updater.idle()
    except Exception as e:
        print(f"Bot failed to start: {e}")
        import traceback
        traceback.print_exc()
        # Keep Flask alive even if bot fails
        while True:
            time.sleep(60)

if __name__ == "__main__":
    main()
