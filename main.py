import os, re
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
IQ_EMAIL = os.getenv("IQ_EMAIL")
IQ_PASSWORD = os.getenv("IQ_PASSWORD")

# Try both library versions
try:
    from iqoptionapi.stable_api import IQ_Option
    iq = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
except:
    from iqoptionapi.api import IQOptionAPI
    iq = IQOptionAPI(IQ_EMAIL, IQ_PASSWORD)

check, reason = iq.connect()
iq.change_balance("PRACTICE")
print(f"DEMO Connected: {check} Balance: ${iq.get_balance()}")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.channel_post.text if update.channel_post else update.message.text
    if not text: return
    text_up = text.upper()
    m = re.search(r'([A-Z]{3}/?[A-Z]{3})', text_up)
    if not m: return
    pair = m.group(1).replace("/", "")
    direction = "call" if "CALL" in text_up or "BUY" in text_up else "put" if "PUT" in text_up else None
    if not direction: return
    print(f"Signal {pair} {direction}")
    try:
        if hasattr(iq, 'buy'):
            status, _id = iq.buy(1, pair, direction, 1)
        else:
            status, _id = iq.buy_digital_spot(pair, 1, direction, 1)
        print(f"DEMO {pair} {direction} -> {status}")
    except Exception as e:
        print(f"Trade error: {e}")

tg_app = Application.builder().token(TOKEN).build()
tg_app.add_handler(MessageHandler(filters.ALL, handle))

@app.route('/')
def home():
    return "BOT LIVE - DEMO - ONE STRATEGY"

if __name__ == '__main__':
    import threading
    threading.Thread(target=lambda: tg_app.run_polling()).start()
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))
