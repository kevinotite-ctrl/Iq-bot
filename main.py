import os, re
from flask import Flask
import threading

# PRINT IMMEDIATELY - BEFORE ANYTHING
print("=== BOT STARTING ===", flush=True)

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from iqoptionapi.stable_api import IQ_Option

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

print(f"ENV Email={bool(EMAIL)} Pass={bool(PASS)} Token={bool(TOKEN)}", flush=True)

Iq = IQ_Option(EMAIL, PASS)
check, reason = Iq.connect()
print(f"CONNECT: {check} Reason: {reason}", flush=True)

if check:
    Iq.change_balance("PRACTICE")
    print(f"DEMO BALANCE: ${Iq.get_balance()} MODE: {Iq.get_balance_mode()}", flush=True)
else:
    print("CONNECT FAILED", flush=True)

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post if update.channel_post else update.message
    text = msg.text if msg else ""
    up = text.upper()
    if "EURUSD" in up or "GBPUSD" in up:
        direction = "call" if "CALL" in up or "BUY" in up else "put" if "PUT" in up else None
        if direction:
            pair = "EURUSD" if "EURUSD" in up else "GBPUSD"
            print(f"SIGNAL {pair} {direction}", flush=True)
            try:
                ok,_id = Iq.buy(1, pair, direction, 1)
                print(f"TRADE {pair} {direction} -> {ok}", flush=True)
            except Exception as e:
                print(f"ERR {e}", flush=True)

tg_app = Application.builder().token(TOKEN).build()
tg_app.add_handler(MessageHandler(filters.ALL, handle))

@app.route('/')
def home():
    try:
        return f"BOT LIVE DEMO BALANCE ${Iq.get_balance()}"
    except:
        return "BOT LIVE but not connected"

if __name__ == '__main__':
    threading.Thread(target=lambda: tg_app.run_polling(), daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))
