import os, time, threading, random
from flask import Flask
import telebot
from telebot import types

print("=== KEVIN BOT V9.7 HEARTBEAT ===", flush=True)
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
    return f"V9.7 LIVE - BAL {bal} - AMT {current_amount}"

bot = telebot.TeleBot(TOKEN)
PAIRS = ["EURUSD-OTC", "EURUSD", "GBPUSD-OTC", "GBPUSD"]
pending_trades = {}

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL
    OWNER_ID = m.chat.id
    RESUME_AT = time.time()
    LAST_SIGNAL = 0
    bal = Iq.get_balance() if Iq else "?"
    bot.send_message(m.chat.id, f"🔥 V9.7 ACTIVE\nBal: ${bal}\n\n/resume - first in 2 mins then every 3 mins\n/scan - force now")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING
    OWNER_ID = m.chat.id
    SCANNING = True
    RESUME_AT = time.time()
    LAST_SIGNAL = 0
    print(f"RESUME called by {OWNER_ID} at {time.time()}", flush=True)
    bot.send_message(m.chat.id, "▶️ Resumed - first signal in 2 mins - WATCH RENDER LOGS for HEARTBEAT")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING
    SCANNING = False
    bot.send_message(m.chat.id, "⏸️ Paused")

@bot.message_handler(commands=['scan','balance','status'])
def handle(m):
    global OWNER_ID, LAST_SIGNAL
    OWNER_ID = m.chat.id
    if "/scan" in m.text:
        LAST_SIGNAL = time.time()
        pair = random.choice(PAIRS)
        direction = random.choice(["call","put"])
        trade_id = f"MAN_{int(time.time())}"
        pending_trades[trade_id] = {"pair": pair, "direction": direction}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"✅ EXECUTE {direction.upper()} ${current_amount}", callback_data=f"execute_{trade_id}"),
                   types.InlineKeyboardButton("⏭️ SKIP", callback_data=f"skip_{trade_id}"))
        bot.send_message(m.chat.id, f"📊 FORCED TEST\n{pair} {direction.upper()} ${current_amount}", reply_markup=markup)
        print(f"MANUAL SIGNAL SENT {trade_id}", flush=True)
    else:
        bal = Iq.get_balance() if Iq else "?"
        left = int((RESUME_AT + 120 - time.time()) if LAST_SIGNAL==0 else (LAST_SIGNAL + 180 - time.time()))
        if left<0: left=0
        bot.send_message(m.chat.id, f"STATUS\nBal ${bal}\nNext in {left}s\nScanning {SCANNING}\nOwner {OWNER_ID}")

@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    global current_amount, martingale_level, LAST_SIGNAL
    print(f"BUTTON CLICKED {call.data}", flush=True)
    try: bot.answer_callback_query(call.id, "Processing...")
    except: pass
    trade_id = call.data.replace("execute_","").replace("skip_","")
    if trade_id not in pending_trades:
        bot.send_message(call.message.chat.id, "❌ Expired, /scan again")
        return
    data = pending_trades[trade_id]
    if "skip" in call.data:
        try: bot.edit_message_text(f"⏭️ SKIPPED {data['pair']}", call.message.chat.id, call.message.message_id)
        except: pass
        del pending_trades[trade_id]
        LAST_SIGNAL = time.time()
        bot.send_message(call.message.chat.id, "⏭️ Skipped - Next in 3 mins")
        return
    pair = data['pair']
    direction = data['direction']
    try: bot.edit_message_text(f"⏳ Executing {direction.upper()} {pair} ${current_amount}...", call.message.chat.id, call.message.message_id)
    except: pass
    if not Iq:
        bot.send_message(call.message.chat.id, "❌ IQ NOT CONNECTED")
        return
    try:
        status, id = Iq.buy(current_amount, pair, direction, 1)
        print(f"BUY RESULT {status} {id}", flush=True)
        if not status:
            bot.send_message(call.message.chat.id, f"❌ Trade failed: {id}")
            return
        bot.send_message(call.message.chat.id, f"✅ EXECUTED {pair} {direction.upper()} ${current_amount}\nID {id}\nWaiting 65s for result...")
        time.sleep(65)
        profit = Iq.check_win_v3(id)
        LAST_SIGNAL = time.time()
        print(f"WIN_CHECK {profit}", flush=True)
        if profit > 0:
            bot.send_message(call.message.chat.id, f"💰 WIN +${round(profit,2)} Bal ${round(Iq.get_balance(),2)} Reset to ${BASE_AMOUNT}\nNext in 3 mins")
            current_amount = BASE_AMOUNT
            martingale_level = 0
        else:
            martingale_level += 1
            loss = current_amount
            current_amount *= 2
            if current_amount > 160:
                current_amount = BASE_AMOUNT
                martingale_level = 0
                bot.send_message(call.message.chat.id, f"📉 LOSS -${loss} Reset Bal ${round(Iq.get_balance(),2)} Next in 3 mins")
            else:
                bot.send_message(call.message.chat.id, f"📉 LOSS -${loss} Next ${current_amount} Lvl {martingale_level} Bal ${round(Iq.get_balance(),2)} Next in 3 mins")
    except Exception as e:
        print(f"EXEC ERROR {e}", flush=True)
        bot.send_message(call.message.chat.id, f"❌ Error {e}")
    if trade_id in pending_trades:
        del pending_trades[trade_id]

def scanner():
    print("SCANNER THREAD STARTED", flush=True)
    while True:
        try:
            time.sleep(5)
            if not OWNER_ID or not SCANNING:
                if int(time.time()) % 30 == 0:
                    print(f"HEARTBEAT - Owner {OWNER_ID} Scanning {SCANNING}", flush=True)
                continue
            now = time.time()
            need = 120 if LAST_SIGNAL == 0 else 180
            last = RESUME_AT if LAST_SIGNAL == 0 else LAST_SIGNAL
            diff = now - last
            if int(now) % 15 == 0:
                print(f"TIMER CHECK - diff {int(diff)} need {need} owner {OWNER_ID}", flush=True)
            if diff < need:
                continue
            pair = random.choice(PAIRS)
            direction = random.choice(["call","put"])
            trade_id = f"AUTO_{int(time.time())}"
            pending_trades[trade_id] = {"pair": pair, "direction": direction}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(f"✅ EXECUTE {direction.upper()} ${current_amount}", callback_data=f"execute_{trade_id}"),
                       types.InlineKeyboardButton("⏭️ SKIP", callback_data=f"skip_{trade_id}"))
            bot.send_message(OWNER_ID, f"📊 KEVIN SIGNAL\nPair: {pair}\nDir: {direction.upper()}\nAmt: ${current_amount}\n\nGuaranteed every 3 mins", reply_markup=markup)
            LAST_SIGNAL = time.time()
            print(f"AUTO SIGNAL SENT {trade_id} to {OWNER_ID}", flush=True)
        except Exception as e:
            print(f"SCANNER ERROR {e}", flush=True)
            import traceback; traceback.print_exc()
            time.sleep(5)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(none_stop=True), daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
