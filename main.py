import os, time, threading, random
from flask import Flask
import telebot

print("=== KEVIN BOT V10 FULL AUTO ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

BASE_AMOUNT = 10
current_amount = BASE_AMOUNT
martingale_level = 0
OWNER_ID = None
Iq = None
SCANNING = True
LAST_SIGNAL = 0
RESUME_AT = time.time()

try:
    from iqoptionapi.stable_api import IQ_Option
    Iq = IQ_Option(EMAIL, PASS)
    check, reason = Iq.connect()
    print(f"IQ CONNECT: {check} | {reason}", flush=True)
    if check:
        Iq.change_balance("PRACTICE")
        print(f"BAL: ${Iq.get_balance()}", flush=True)
except Exception as e:
    print(f"IQ ERR {e}", flush=True)

@app.route('/')
def home():
    bal = Iq.get_balance() if Iq else "NO IQ"
    return f"V10 AUTO LIVE - BAL {bal} - AMT {current_amount}"

bot = telebot.TeleBot(TOKEN)
PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "EURUSD", "GBPUSD"]

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL
    OWNER_ID = m.chat.id
    RESUME_AT = time.time()
    LAST_SIGNAL = 0
    bal = Iq.get_balance() if Iq else "?"
    bot.send_message(m.chat.id, f"🤖 V10 FULL AUTO ACTIVE\nBal: ${bal}\nAmt: ${current_amount}\n\nBot trades BY ITSELF every 3 mins\n/resume - start\n/pause - stop\n/balance - check")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING
    OWNER_ID = m.chat.id
    SCANNING = True
    RESUME_AT = time.time()
    LAST_SIGNAL = 0
    print(f"RESUME AUTO {OWNER_ID}", flush=True)
    bot.send_message(m.chat.id, "▶️ AUTO RESUMED - First trade in 2 mins, then every 3 mins. No tap needed.")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING
    SCANNING = False
    bot.send_message(m.chat.id, "⏸️ Paused")

@bot.message_handler(commands=['balance','status'])
def status(m):
    global OWNER_ID
    OWNER_ID = m.chat.id
    b = Iq.get_balance() if Iq else "?"
    left = int((RESUME_AT + 120 - time.time()) if LAST_SIGNAL==0 else (LAST_SIGNAL + 180 - time.time()))
    if left < 0: left = 0
    bot.send_message(m.chat.id, f"BAL ${b} | Next in {left}s | Amt ${current_amount} | Lvl {martingale_level}")

@bot.message_handler(commands=['scan'])
def scan(m):
    global OWNER_ID
    OWNER_ID = m.chat.id
    bot.send_message(m.chat.id, "🔍 Force trade now...")
    do_trade()

def do_trade():
    global current_amount, martingale_level, LAST_SIGNAL
    if not Iq:
        if OWNER_ID:
            bot.send_message(OWNER_ID, "❌ IQ NOT CONNECTED")
        return
    pair = random.choice(PAIRS)
    direction = random.choice(["call","put"])
    if OWNER_ID:
        bot.send_message(OWNER_ID, f"📊 SIGNAL {pair} {direction.upper()} ${current_amount}\nAuto buying...")

    bought = False
    bought_pair = pair
    bought_id = None

    for attempt_pair in [pair] + PAIRS:
        try:
            print(f"TRY BUY {attempt_pair} {direction} ${current_amount}", flush=True)
            status, trade_id = Iq.buy(current_amount, attempt_pair, direction, 1)
            print(f"BUY RESULT {attempt_pair} -> {status} {trade_id}", flush=True)
            if status:
                bought = True
                bought_pair = attempt_pair
                bought_id = trade_id
                break
            else:
                if "closed" in str(trade_id).lower() or "not open" in str(trade_id).lower():
                    continue
                else:
                    if OWNER_ID:
                        bot.send_message(OWNER_ID, f"❌ Failed {attempt_pair}: {trade_id}")
                    break
        except Exception as e:
            print(f"BUY ERR {e}", flush=True)
            continue

    if not bought:
        if OWNER_ID:
            bot.send_message(OWNER_ID, f"❌ All pairs failed. Retry in 3 mins. Bal ${round(Iq.get_balance(),2)}")
        LAST_SIGNAL = time.time()
        return

    if OWNER_ID:
        bot.send_message(OWNER_ID, f"✅ AUTO BOUGHT {bought_pair} {direction.upper()} ${current_amount}\nID {bought_id}\nWaiting 65s...")

    time.sleep(65)
    try:
        profit = Iq.check_win_v3(bought_id)
        bal = Iq.get_balance()
        LAST_SIGNAL = time.time()
        print(f"RESULT profit={profit} bal={bal}", flush=True)
        if profit and profit > 0:
            if OWNER_ID:
                bot.send_message(OWNER_ID, f"💰 WIN +${round(profit,2)}\nBal: ${round(bal,2)}\nReset to ${BASE_AMOUNT}\nNext in 3 mins")
            current_amount = BASE_AMOUNT
            martingale_level = 0
        else:
            martingale_level += 1
            loss = current_amount
            current_amount *= 2
            if current_amount > 160:
                current_amount = BASE_AMOUNT
                martingale_level = 0
                if OWNER_ID:
                    bot.send_message(OWNER_ID, f"📉 LOSS -${loss}\nBal: ${round(bal,2)}\nReset to ${BASE_AMOUNT}\nNext in 3 mins")
            else:
                if OWNER_ID:
                    bot.send_message(OWNER_ID, f"📉 LOSS -${loss}\nNext: ${current_amount} Lvl {martingale_level}\nBal: ${round(bal,2)}\nNext in 3 mins")
    except Exception as e:
        print(f"RESULT ERR {e}", flush=True)
        if OWNER_ID:
            bot.send_message(OWNER_ID, f"⚠️ Result error {e}\nBal ${round(Iq.get_balance(),2)}")
        LAST_SIGNAL = time.time()

def scanner():
    print("SCANNER AUTO STARTED V10", flush=True)
    while True:
        try:
            time.sleep(10)
            print(f"ALIVE Owner:{OWNER_ID} Scan:{SCANNING} Last:{int(LAST_SIGNAL)}", flush=True)
            if not OWNER_ID or not SCANNING:
                continue
            now = time.time()
            need = 120 if LAST_SIGNAL == 0 else 180
            last = RESUME_AT if LAST_SIGNAL == 0 else LAST_SIGNAL
            diff = now - last
            print(f"CHECK diff={int(diff)} need={need} -> {'TRADE!' if diff>=need else 'wait'}", flush=True)
            if diff < need:
                continue
            do_trade()
        except Exception as e:
            print(f"SCANNER ERR {e}", flush=True)
            import traceback; traceback.print_exc()
            time.sleep(5)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(none_stop=True), daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
