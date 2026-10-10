import os, time, threading, random
from flask import Flask
import telebot
from telebot import types

print("=== KEVIN BOT V9.5 EXECUTE FIX ===", flush=True)
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
RESUME_AT = 0
LAST_EXECUTED_AT = 0

try:
    from iqoptionapi.stable_api import IQ_Option
    Iq = IQ_Option(EMAIL, PASS)
    check, reason = Iq.connect()
    print(f"IQ CONNECT: {check} | {reason}", flush=True)
    if check:
        Iq.change_balance(CURRENT_BALANCE_MODE)
        print(f"BALANCE: ${Iq.get_balance()}", flush=True)
    else:
        print(f"IQ FAILED: {reason}", flush=True)
except Exception as e:
    print(f"IQ EXCEPTION: {e}", flush=True)
    import traceback; traceback.print_exc()

@app.route('/')
def home():
    bal = "NOT CONNECTED"
    if Iq:
        try: bal = Iq.get_balance()
        except: bal = "IQ ERROR"
    return f"BOT V9.5 LIVE - {bal} - AMT {current_amount}"

def get_rsi(prices, period=14):
    if len(prices) < period+1: return 50
    gains = [max(prices[i]-prices[i-1],0) for i in range(1,len(prices))]
    losses = [max(prices[i-1]-prices[i],0) for i in range(1,len(prices))]
    ag = sum(gains[-period:])/period
    al = sum(losses[-period:])/period
    if al == 0: return 100
    return 100-(100/(1+(ag/al)))

def get_ema(prices, period):
    if len(prices) < period: return prices[-1]
    k = 2/(period+1)
    ema = sum(prices[:period])/period
    for p in prices[period:]:
        ema = p*k + ema*(1-k)
    return ema

bot = telebot.TeleBot(TOKEN)
PAIRS = ["EURUSD-OTC", "EURUSD", "GBPUSD-OTC"]
pending_trades = {}

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_EXECUTED_AT
    OWNER_ID = m.chat.id
    RESUME_AT = time.time()
    LAST_EXECUTED_AT = 0
    bal = "?"
    if Iq:
        try: bal = Iq.get_balance()
        except Exception as e: bal = f"Error {e}"
    bot.send_message(m.chat.id, f"🔥 V9.5 EXECUTE FIX ACTIVE\nID: {OWNER_ID}\nBal: ${bal}\nIQ Connected: {Iq is not None}\n\n/scan to test execute")

@bot.message_handler(commands=['scan'])
def manual_scan(m):
    global OWNER_ID
    OWNER_ID = m.chat.id
    pair = random.choice(PAIRS)
    direction = random.choice(["call", "put"])
    trade_id = f"MANUAL_{pair}_{int(time.time())}"
    pending_trades[trade_id] = {"pair": pair, "direction": direction}
    print(f"SCAN CREATED: {trade_id} {pair} {direction}", flush=True)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"✅ EXECUTE {direction.upper()} ${current_amount}", callback_data=f"execute_{trade_id}"),
               types.InlineKeyboardButton("⏭️ SKIP", callback_data=f"skip_{trade_id}"))
    bot.send_message(m.chat.id, f"📊 TEST SIGNAL\nPair: {pair}\nDir: {direction.upper()}\nID: {trade_id}\nAmt: ${current_amount}", reply_markup=markup)

@bot.message_handler(commands=['balance','status','resume','pause'])
def other_cmds(m):
    global SCANNING, RESUME_AT, LAST_EXECUTED_AT, OWNER_ID
    OWNER_ID = m.chat.id
    if "/resume" in m.text:
        SCANNING = True
        RESUME_AT = time.time()
        LAST_EXECUTED_AT = 0
        bot.send_message(m.chat.id, "▶️ RESUMED - First in 2 mins")
    elif "/pause" in m.text:
        SCANNING = False
        bot.send_message(m.chat.id, "⏸️ PAUSED")
    else:
        bal = "?"
        if Iq:
            try: bal = Iq.get_balance()
            except Exception as e: bal = f"Error {e}"
        bot.send_message(m.chat.id, f"📊 STATUS\nBal: ${bal}\nIQ OK: {Iq is not None}\nAmt: ${current_amount}\nScanning: {SCANNING}")

@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    global current_amount, martingale_level, LAST_EXECUTED_AT
    print(f"BUTTON CLICKED: {call.data}", flush=True)
    bot.answer_callback_query(call.id, "Processing...")
    trade_id = call.data.replace("execute_","").replace("skip_","")
    print(f"TRADE_ID: {trade_id}, PENDING: {list(pending_trades.keys())}", flush=True)
    if trade_id not in pending_trades:
        print("TRADE EXPIRED", flush=True)
        bot.send_message(call.message.chat.id, "❌ Trade expired. Use /scan again.")
        return
    data = pending_trades[trade_id]
    if "skip" in call.data:
        bot.edit_message_text(f"⏭️ SKIPPED {data['pair']}", call.message.chat.id, call.message.message_id)
        del pending_trades[trade_id]
        return
    pair = data['pair']
    direction = data['direction']
    bot.edit_message_text(f"⏳ Executing {direction.upper()} on {pair} ${current_amount}...", call.message.chat.id, call.message.message_id)
    if not Iq:
        bot.send_message(call.message.chat.id, "❌ IQ NOT CONNECTED. Check EMAIL/PASS in Render env. Logs show IQ CONNECT failed.")
        return
    try:
        print(f"BUYING {pair} {direction} {current_amount}", flush=True)
        status, id = Iq.buy(current_amount, pair, direction, 1)
        print(f"BUY RESULT: {status} {id}", flush=True)
        if not status:
            bot.send_message(call.message.chat.id, f"❌ Trade Failed: {id}\nPossible: balance insufficient, or pair closed, or IQ blocked")
            return
        bot.send_message(call.message.chat.id, f"✅ TRADE EXECUTED\n{pair} {direction.upper()} ${current_amount}\nID: {id}\nWaiting 65s for result...")
        time.sleep(65)
        profit = Iq.check_win_v3(id)
        print(f"PROFIT: {profit}", flush=True)
        LAST_EXECUTED_AT = time.time()
        if profit > 0:
            bot.send_message(call.message.chat.id, f"💰 WIN +${round(profit,2)}\nBal: ${round(Iq.get_balance(),2)}")
            current_amount = BASE_AMOUNT
            martingale_level = 0
        else:
            martingale_level += 1
            loss = current_amount
            current_amount *= 2
            if current_amount > 160:
                current_amount = BASE_AMOUNT
                martingale_level = 0
                bot.send_message(call.message.chat.id, f"📉 LOSS -${loss} Reset to ${BASE_AMOUNT}")
            else:
                bot.send_message(call.message.chat.id, f"📉 LOSS -${loss} Next: ${current_amount} Lvl:{martingale_level}")
    except Exception as e:
        print(f"EXECUTE ERROR: {e}", flush=True)
        import traceback; traceback.print_exc()
        bot.send_message(call.message.chat.id, f"❌ EXECUTE ERROR: {e}")
    if trade_id in pending_trades:
        del pending_trades[trade_id]

def scanner():
    while True:
        if not OWNER_ID or not Iq or not SCANNING:
            time.sleep(5); continue
        now = time.time()
        if LAST_EXECUTED_AT == 0:
            if now - RESUME_AT < 120:
                time.sleep(5); continue
        else:
            if now - LAST_EXECUTED_AT < 180:
                time.sleep(5); continue
        # guaranteed signal
        try:
            pair = random.choice(PAIRS)
            direction = random.choice(["call","put"])
            trade_id = f"{pair}_{int(time.time())}"
            pending_trades[trade_id] = {"pair": pair, "direction": direction}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(f"✅ EXECUTE {direction.upper()} ${current_amount}", callback_data=f"execute_{trade_id}"),
                       types.InlineKeyboardButton("⏭️ SKIP", callback_data=f"skip_{trade_id}"))
            bot.send_message(OWNER_ID, f"📊 KEVIN SIGNAL\nPair: {pair}\nDir: {direction.upper()}\nAmt: ${current_amount}", reply_markup=markup)
        except Exception as e:
            print(f"Scanner err: {e}")
        time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
