import os, time, threading, random
from flask import Flask
import telebot
from telebot import types

print("=== KEVIN BOT V9.6 FINAL TIMER FIX ===", flush=True)
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
CURRENT_BALANCE_MODE = "PRACTICE"
LAST_SIGNAL_SENT = 0
LAST_EXECUTED_AT = 0
RESUME_AT = time.time()

try:
    from iqoptionapi.stable_api import IQ_Option
    Iq = IQ_Option(EMAIL, PASS)
    check, reason = Iq.connect()
    print(f"IQ CONNECT: {check} | {reason}", flush=True)
    if check:
        Iq.change_balance(CURRENT_BALANCE_MODE)
        print(f"BAL: ${Iq.get_balance()}", flush=True)
except Exception as e:
    print(f"IQ ERROR: {e}", flush=True)

@app.route('/')
def home():
    bal = Iq.get_balance() if Iq else "NO IQ"
    return f"V9.6 LIVE - BAL {bal} - AMT {current_amount}"

bot = telebot.TeleBot(TOKEN)
PAIRS = ["EURUSD-OTC", "EURUSD", "GBPUSD-OTC"]
pending_trades = {}

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_EXECUTED_AT, LAST_SIGNAL_SENT
    OWNER_ID = m.chat.id
    RESUME_AT = time.time()
    LAST_EXECUTED_AT = 0
    LAST_SIGNAL_SENT = 0
    bal = Iq.get_balance() if Iq else "?"
    bot.send_message(m.chat.id, f"🔥 V9.6 ACTIVE\nBal: ${bal}\nBase: ${BASE_AMOUNT}\n\nAuto signal every 3 mins (no spam)\n/scan = force now\n/pause /resume")

@bot.message_handler(commands=['scan'])
def manual_scan(m):
    global OWNER_ID, LAST_SIGNAL_SENT
    OWNER_ID = m.chat.id
    LAST_SIGNAL_SENT = time.time()  # reset timer so next auto is 3 mins from now
    pair = random.choice(PAIRS)
    direction = random.choice(["call", "put"])
    trade_id = f"MAN_{int(time.time())}"
    pending_trades[trade_id] = {"pair": pair, "direction": direction}
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"✅ EXECUTE {direction.upper()} ${current_amount}", callback_data=f"execute_{trade_id}"),
               types.InlineKeyboardButton("⏭️ SKIP", callback_data=f"skip_{trade_id}"))
    bot.send_message(m.chat.id, f"📊 FORCED SIGNAL\nPair: {pair}\nDir: {direction.upper()}\nAmt: ${current_amount}", reply_markup=markup)

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING
    SCANNING = False
    bot.send_message(m.chat.id, "⏸️ Paused")

@bot.message_handler(commands=['resume'])
def resume(m):
    global SCANNING, RESUME_AT, LAST_EXECUTED_AT, LAST_SIGNAL_SENT, OWNER_ID
    OWNER_ID = m.chat.id
    SCANNING = True
    RESUME_AT = time.time()
    LAST_EXECUTED_AT = 0
    LAST_SIGNAL_SENT = 0
    bot.send_message(m.chat.id, "▶️ Resumed - first signal in 2 mins")

@bot.message_handler(commands=['balance','status'])
def bal_status(m):
    bal = Iq.get_balance() if Iq else "?"
    now = time.time()
    next_in = 0
    if LAST_EXECUTED_AT > 0:
        next_in = int(180 - (now - LAST_EXECUTED_AT))
    elif LAST_SIGNAL_SENT > 0:
        next_in = int(180 - (now - LAST_SIGNAL_SENT))
    else:
        next_in = int(120 - (now - RESUME_AT))
    if next_in < 0: next_in = 0
    bot.send_message(m.chat.id, f"📊 V9.6 STATUS\nBal: ${bal}\nAmt: ${current_amount}\nNext signal in: {next_in}s\nScanning: {SCANNING}")

@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    global current_amount, martingale_level, LAST_EXECUTED_AT, LAST_SIGNAL_SENT
    print(f"CLICK: {call.data}", flush=True)
    try:
        bot.answer_callback_query(call.id, "Processing... Please wait")
    except: pass
    trade_id = call.data.replace("execute_","").replace("skip_","")
    if trade_id not in pending_trades:
        bot.send_message(call.message.chat.id, "❌ Expired, use /scan")
        return
    data = pending_trades[trade_id]
    if "skip" in call.data:
        try: bot.edit_message_text(f"⏭️ SKIPPED {data['pair']}", call.message.chat.id, call.message.message_id)
        except: pass
        del pending_trades[trade_id]
        LAST_SIGNAL_SENT = time.time()
        LAST_EXECUTED_AT = time.time()  # start 3 min timer even on skip
        bot.send_message(call.message.chat.id, "⏭️ Skipped. Next signal in 3 mins...")
        return
    pair = data['pair']
    direction = data['direction']
    try: bot.edit_message_text(f"⏳ Executing {direction.upper()} {pair} ${current_amount}...", call.message.chat.id, call.message.message_id)
    except: pass
    if not Iq:
        bot.send_message(call.message.chat.id, "❌ IQ not connected")
        return
    try:
        print(f"BUY {pair} {direction} {current_amount}", flush=True)
        status, id = Iq.buy(current_amount, pair, direction, 1)
        print(f"RESULT {status} {id}", flush=True)
        if not status:
            bot.send_message(call.message.chat.id, f"❌ Failed: {id}\nTry /scan again")
            return
        bot.send_message(call.message.chat.id, f"✅ TRADE EXECUTED\n{pair} {direction.upper()} ${current_amount}\nID {id}\nWaiting 65s...")
        time.sleep(65)
        profit = Iq.check_win_v3(id)
        LAST_EXECUTED_AT = time.time()
        LAST_SIGNAL_SENT = time.time()
        print(f"PROFIT {profit}", flush=True)
        if profit > 0:
            bot.send_message(call.message.chat.id, f"💰 WIN +${round(profit,2)}\nBal: ${round(Iq.get_balance(),2)}\nReset to ${BASE_AMOUNT}\n\nNext in 3 mins")
            current_amount = BASE_AMOUNT
            martingale_level = 0
        else:
            martingale_level += 1
            loss = current_amount
            current_amount = current_amount * 2
            if current_amount > 160:
                current_amount = BASE_AMOUNT
                martingale_level = 0
                bot.send_message(call.message.chat.id, f"📉 LOSS -${loss} Reset to ${BASE_AMOUNT}\nBal: ${round(Iq.get_balance(),2)}\n\nNext in 3 mins")
            else:
                bot.send_message(call.message.chat.id, f"📉 LOSS -${loss} Next ${current_amount} Lvl {martingale_level}\nBal: ${round(Iq.get_balance(),2)}\n\nNext in 3 mins")
    except Exception as e:
        print(f"BUY ERROR {e}", flush=True)
        bot.send_message(call.message.chat.id, f"❌ Error: {e}")
    if trade_id in pending_trades:
        del pending_trades[trade_id]

def scanner():
    while True:
        if not OWNER_ID or not Iq or not SCANNING:
            time.sleep(5); continue
        now = time.time()
        # Timer: 2 mins after resume, 3 mins after last signal/executed
        wait_needed = 120 if (LAST_EXECUTED_AT == 0 and LAST_SIGNAL_SENT == 0) else 180
        last_time = RESUME_AT
        if LAST_EXECUTED_AT > 0: last_time = LAST_EXECUTED_AT
        elif LAST_SIGNAL_SENT > 0: last_time = LAST_SIGNAL_SENT
        if now - last_time < wait_needed:
            time.sleep(5); continue
        try:
            pair = random.choice(PAIRS)
            direction = random.choice(["call","put"])
            trade_id = f"AUTO_{int(time.time())}"
            pending_trades[trade_id] = {"pair": pair, "direction": direction}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(f"✅ EXECUTE {direction.upper()} ${current_amount}", callback_data=f"execute_{trade_id}"),
                       types.InlineKeyboardButton("⏭️ SKIP", callback_data=f"skip_{trade_id}"))
            bot.send_message(OWNER_ID, f"📊 KEVIN SIGNAL\nPair: {pair}\nDir: {direction.upper()}\nAmt: ${current_amount}\n\nEvery 3 mins - Guaranteed", reply_markup=markup)
            LAST_SIGNAL_SENT = time.time()
            print(f"SENT SIGNAL {trade_id}", flush=True)
        except Exception as e:
            print(f"Scan err {e}", flush=True)
        time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
