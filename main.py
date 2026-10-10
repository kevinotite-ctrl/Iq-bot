import os, re
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from iqoptionapi.stable_api import IQ_Option
import threading

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

print(f"=== BOT STARTING ===")
print(f"Env check Email:{bool(EMAIL)} Pass:{bool(PASS)} Token:{bool(TOKEN)}")

Iq = IQ_Option(EMAIL, PASS)
check, reason = Iq.connect()
print(f"Connect result: {check} / {reason}")

if check:
    Iq.change_balance("PRACTICE")
    bal = Iq.get_balance()
    mode = Iq.get_balance_mode()
    print(f"DEMO BALANCE: ${bal} MODE: {mode}")
else:
    print("FAILED TO CONNECT - CHECK EMAIL/PASS OR 2FA")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post if update.channel_post else update.message
    text = msg.text if msg else ""
    if not text: return
    up = text.upper()
    m = re.search(r'([A-Z]{3}/?[A-Z]{3}|[A-Z]{3}-[A-Z]{3}|[A-Z]{3}_[A-Z]{3}|[A-Z]{6})', up)
    # simplified pair detect
    m2 = re.search(r'(EURUSD|GBPUSD|USDJPY|AUDUSD|EURGBP|USDCAD|GBPJPY|EURJPY)', up)
    pair = m2.group(1) if m2 else (m.group(1).replace("/","").replace("-","").replace("_","") if m else None)
    if not pair: return
    if len(pair)==6:
        pair = f"{pair[:3]}/{pair[3:]}"
        pair_api = pair.replace("/","")
    else:
        pair_api = pair.replace("/","")
        
    direction = None
    if "CALL" in up or "BUY" in up or "UP" in up or "⬆" in up:
        direction = "call"
    elif "PUT" in up or "SELL" in up or "DOWN" in up or "⬇" in up:
        direction = "put"
    if not direction: return
    
    print(f"SIGNAL FOUND: {pair_api} {direction} | Text: {text[:100]}")
    try:
        ok, _id = Iq.buy(1, pair_api, direction, 1)
        print(f">>> DEMO TRADE EXECUTED: {pair_api} {direction} -> {ok} id:{_id}")
    except Exception as e:
        print(f"Trade error: {e}")

tg_app = Application.builder().token(TOKEN).build()
tg_app.add_handler(MessageHandler(filters.ALL, handle))

@app.route('/')
def home():
    try:
        b = Iq.get_balance()
        return f"BOT LIVE - DEMO BALANCE: ${b}"
    except:
        return "BOT LIVE - Connecting..."

if __name__ == '__main__':
    threading.Thread(target=lambda: tg_app.run_polling(), daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))
