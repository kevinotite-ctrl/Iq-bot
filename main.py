import os, re, time
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from iqoptionapi.stable_api import IQ_Option

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

print(f"Env check Email:{bool(EMAIL)} Pass:{bool(PASS)} Token:{bool(TOKEN)}")

Iq = IQ_Option(EMAIL, PASS)
check, reason = Iq.connect()
print(f"Connect: {check} / {reason}")

if check:
    Iq.change_balance("PRACTICE")
    print(f"DEMO BALANCE: {Iq.get_balance()} - MODE: {Iq.get_balance_mode()}")
else:
    print("FAILED TO CONNECT - CHECK EMAIL/PASS")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post if update.channel_post else update.message
    text = msg.text if msg else ""
    if not text: return
    up = text.upper()
    m = re.search(r'([A-Z]{3}/?[A-Z]{3})', up)
    if not m: return
    pair = m.group(1).replace("/", "")
    direction = "call" if "CALL" in up or "BUY" in up else "put" if "PUT" in up else None
    if not direction: return
    print(f"SIGNAL {pair} {direction}")
    try:
        ok, _id = Iq.buy(1, pair, direction, 1)
        print(f"DEMO TRADE {pair} {direction} -> {ok} id:{_id}")
    except Exception as e:
        print(f"Trade err: {e}")

tg_app = Application.builder().token(TOKEN).build()
tg_app.add_handler(MessageHandler(filters.ALL, handle))

@app.route('/')
def home():
    return f"BOT LIVE - Balance: {Iq.get_balance() if check else 'Not connected'}"

if __name__ == '__main__':
    import threading
    threading.Thread(target=lambda: tg_app.run_polling()).start()
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))
