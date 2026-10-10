import os, re
from flask import Flask
print("=== BOT V3 STARTING ===", flush=True)

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from iqoptionapi.stable_api import IQ_Option
import threading

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

print(f"ENV TOKEN={bool(TOKEN)} EMAIL={bool(EMAIL)}", flush=True)

# IQ Login
try:
    Iq = IQ_Option(EMAIL, PASS)
    check, reason = Iq.connect()
    print(f"IQ CONNECT: {check} / {reason}", flush=True)
    if check:
        Iq.change_balance("PRACTICE")
        bal = Iq.get_balance()
        print(f"DEMO BALANCE: ${bal}", flush=True)
    else:
        print(f"IQ FAIL: {reason}", flush=True)
        Iq = None
except Exception as e:
    print(f"IQ ERROR: {e}", flush=True)
    Iq = None

balance_text = f"DEMO BALANCE: ${bal}" if Iq else "IQ NOT CONNECTED - Check login/2FA"

@app.route('/')
def home():
    return f"BOT LIVE<br>{balance_text}"

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post if update.channel_post else update.message
    text = msg.text if msg else ""
    if not text:
        return
    print(f"CHANNEL MSG: {text[:80]}", flush=True)
    up = text.upper()
    pair = None
    if "EURUSD" in up: pair = "EURUSD"
    elif "GBPUSD" in up: pair = "GBPUSD"
    elif "USDJPY" in up: pair = "USDJPY"
    elif "AUDUSD" in up: pair = "AUDUSD"
    if not pair:
        return
    direction = None
    if "CALL" in up or "BUY" in up or "⬆" in up or "UP" in up:
        direction = "call"
    elif "PUT" in up or "SELL" in up or "⬇" in up or "DOWN" in up:
        direction = "put"
    if not direction:
        return
    print(f"SIGNAL FOUND: {pair} {direction}", flush=True)
    if Iq:
        try:
            ok, _id = Iq.buy(1, pair, direction, 1)
            print(f"TRADE EXECUTED: {pair} {direction} -> {ok} id:{_id}", flush=True)
        except Exception as e:
            print(f"TRADE ERROR: {e}", flush=True)
    else:
        print("Cannot trade - IQ not connected", flush=True)

# Build telegram app
tg_app = Application.builder().token(TOKEN).build()
tg_app.add_handler(MessageHandler(filters.ALL, handle))

# Run Flask in background thread
def run_flask():
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))

threading.Thread(target=run_flask, daemon=True).start()

# Run Telegram in MAIN thread (fixes set_wakeup_fd error)
print("Starting Telegram polling in main thread...", flush=True)
tg_app.run_polling()
