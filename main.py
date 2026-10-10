import os
from flask import Flask
print("=== BOT STARTING V2 ===", flush=True)

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

print(f"ENV CHECK - TOKEN:{bool(TOKEN)} EMAIL:{bool(EMAIL)} PASS:{bool(PASS)}", flush=True)
if EMAIL:
    print(f"EMAIL VALUE: {EMAIL[:3]}***", flush=True)

# Try IQ login in background
balance_info = "Checking..."
try:
    from iqoptionapi.stable_api import IQ_Option
    print("Connecting to IQ...", flush=True)
    Iq = IQ_Option(EMAIL, PASS)
    check, reason = Iq.connect()
    print(f"IQ CONNECT: {check} - {reason}", flush=True)
    if check:
        Iq.change_balance("PRACTICE")
        bal = Iq.get_balance()
        mode = Iq.get_balance_mode()
        balance_info = f"DEMO BALANCE: ${bal} MODE: {mode}"
        print(balance_info, flush=True)
    else:
        balance_info = f"IQ FAILED: {reason} - Disable 2FA!"
        print(balance_info, flush=True)
except Exception as e:
    balance_info = f"ERROR: {e}"
    print(balance_info, flush=True)

@app.route('/')
def home():
    return f"BOT LIVE<br>{balance_info}<br>ENV: Email={bool(EMAIL)} Token={bool(TOKEN)}"

# Telegram part - starts after
def start_telegram():
    print("Starting Telegram...", flush=True)
    try:
        import re
        import threading
        from telegram import Update
        from telegram.ext import Application, MessageHandler, filters, ContextTypes
        
        async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
            msg = update.channel_post if update.channel_post else update.message
            text = msg.text if msg else ""
            print(f"Got message: {text[:50]}", flush=True)
            up = text.upper()
            if "EURUSD" in up and ("CALL" in up or "PUT" in up):
                direction = "call" if "CALL" in up else "put"
                print(f"SIGNAL EURUSD {direction}", flush=True)
                try:
                    ok,_id = Iq.buy(1, "EURUSD", direction, 1)
                    print(f"TRADE RESULT: {ok} {_id}", flush=True)
                except Exception as e:
                    print(f"TRADE ERR: {e}", flush=True)

        tg_app = Application.builder().token(TOKEN).build()
        tg_app.add_handler(MessageHandler(filters.ALL, handle))
        tg_app.run_polling()
    except Exception as e:
        print(f"TELEGRAM ERROR: {e}", flush=True)

import threading
threading.Thread(target=start_telegram, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))
