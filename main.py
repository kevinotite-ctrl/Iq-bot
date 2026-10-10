import os, time, threading, random
from flask import Flask
import telebot
from telebot import types

print("=== KEVIN TRAILBLAZER BOT V9.3 - 2MIN / 3MIN AFTER RESULT ===", flush=True)
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
AUTO_MODE = False
CURRENT_BALANCE_MODE = "PRACTICE"

# TIMERS
RESUME_AT = 0
LAST_EXECUTED_AT = 0 # set AFTER result

try:
    from iqoptionapi.stable_api import IQ_Option
    Iq = IQ_Option(EMAIL, PASS)
    check, reason = Iq.connect()
    print(f"IQ CONNECT: {check} | {reason}", flush=True)
    if check:
        Iq.change_balance(CURRENT_BALANCE_MODE)
        print(f"BAL {CURRENT_BALANCE_MODE}: ${Iq.get_balance()}")
except Exception as e:
    print(f"IQ ERROR: {e}")

@app.route('/')
def home():
    bal = Iq.get_balance() if Iq else "NOT CONNECTED"
    status = "RUNNING" if SCANNING else "PAUSED"
    wait_info = ""
    now = time.time()
    if SCANNING:
        if LAST_EXECUTED_AT == 0 and RESUME_AT > 0:
            left = 120 - (now - RESUME_AT)
            if left > 0:
                wait_info = f" | FIRST SIGNAL IN {int(left)}s"
        elif LAST_EXECUTED_AT > 0:
            left = 180 - (now - LAST_EXECUTED_AT)
            if left > 0:
                wait_info = f" | NEXT SIGNAL IN {int(left)}s"
    return f"KEVIN TRAILBLAZER BOT LIVE - STATUS: {status} - MODE: {CURRENT_BALANCE_MODE} - BAL: ${bal} - AMOUNT: ${current_amount} - LEVEL: {martingale_level}{wait_info}"

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
    global OWNER_ID, current_amount, martingale_level, RESUME_AT, LAST_EXECUTED_AT
    OWNER_ID = m.chat.id
    current_amount = BASE_AMOUNT
    martingale_level = 0
    RESUME_AT = time.time()
    LAST_EXECUTED_AT = 0
    bal = Iq.get_balance() if Iq else "?"
    bot.send_message(m.chat.id, f"🔥 KEVIN TRAILBLAZER BOT ACTIVE\nID: {OWNER_ID}\nMode: {CURRENT_BALANCE_MODE}\nBalance: ${bal}\nBase: ${BASE_AMOUNT}\nCurrent: ${current_amount}\n\nLogic: 2min after /resume -> signal -> 1min result -> 3min wait -> next signal\n\n/scan - Force signal now\n/pause - Pause\n/resume - Resume\n/amount 20 - Set amount\n/balance - Status")

@bot.message_handler(commands=['scan'])
def manual_scan(m):
    global OWNER_ID
    OWNER_ID = m.chat.id
    pair = random.choice(PAIRS)
    direction = random.choice(["call", "put"])
    trade_id = f"MANUAL_{pair}_{int(time.time())}"
    pending_trades[trade_id] = {"pair": pair, "direction": direction}
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(f"✅ EXECUTE {direction.upper()} ${current_amount}", callback_data=f"execute_{trade_id}"),
               types.InlineKeyboardButton("⏭️ SKIP", callback_data=f"skip_{trade_id}"))
    bot.send_message(m.chat.id, f"📊 KEVIN SIGNAL [FORCED BY /scan]\nPair: {pair}\nDir: {direction.upper()} ({'BUY' if direction=='call' else 'SELL'})\nAmount: ${current_amount} Lvl:{martingale_level}", reply_markup=markup)

@bot.message_handler(commands=['pause','stop'])
def pause_scan(m):
    global SCANNING
    SCANNING = False
    bot.send_message(m.chat.id, "⏸️ Scanning PAUSED. No new signals. Use /resume to start again.")

@bot.message_handler(commands=['resume'])
def resume_scan(m):
    global SCANNING, RESUME_AT, LAST_EXECUTED_AT, OWNER_ID
    OWNER_ID = m.chat.id
    SCANNING = True
    RESUME_AT = time.time()
    LAST_EXECUTED_AT = 0
    bot.send_message(m.chat.id, "▶️ Scanning RESUMED.\n⏳ First signal in 2 minutes...")

@bot.message_handler(commands=['amount'])
def set_amount(m):
    global BASE_AMOUNT, current_amount, martingale_level
    try:
        new_amt = int(m.text.split()[1])
        if new_amt < 1 or new_amt > 1000:
            bot.send_message(m.chat.id, "❌ Amount must be 1-1000")
            return
        BASE_AMOUNT = new_amt
        current_amount = new_amt
        martingale_level = 0
        bot.send_message(m.chat.id, f"✅ Base amount set to ${BASE_AMOUNT}\nCurrent reset to ${current_amount}")
    except:
        bot.send_message(m.chat.id, "Usage: /amount 20")

@bot.message_handler(commands=['real'])
def set_real(m):
    global CURRENT_BALANCE_MODE
    try:
        Iq.change_balance("REAL")
        CURRENT_BALANCE_MODE = "REAL"
        bot.send_message(m.chat.id, f"⚠️ SWITCHED TO REAL ACCOUNT\nBalance: ${Iq.get_balance()}")
    except Exception as e:
        bot.send_message(m.chat.id, f"Error: {e}")

@bot.message_handler(commands=['practice','demo'])
def set_practice(m):
    global CURRENT_BALANCE_MODE
    try:
        Iq.change_balance("PRACTICE")
        CURRENT_BALANCE_MODE = "PRACTICE"
        bot.send_message(m.chat.id, f"✅ SWITCHED TO PRACTICE\nBalance: ${Iq.get_balance()}")
    except Exception as e:
        bot.send_message(m.chat.id, f"Error: {e}")

@bot.message_handler(commands=['balance','status'])
def check_bal(m):
    bal = Iq.get_balance() if Iq else "?"
    status = "RUNNING" if SCANNING else "PAUSED"
    now = time.time()
    timer_msg = ""
    if SCANNING:
        if LAST_EXECUTED_AT == 0 and RESUME_AT > 0:
            left = int(120 - (now - RESUME_AT))
            if left > 0:
                timer_msg = f"\n⏳ First signal in: {left}s"
        elif LAST_EXECUTED_AT > 0:
            left = int(180 - (now - LAST_EXECUTED_AT))
            if left > 0:
                timer_msg = f"\n⏳ Next signal in: {left}s"
            else:
                timer_msg = "\n✅ Ready - scanning market..."
    bot.send_message(m.chat.id, f"📊 KEVIN STATUS\nMode: {CURRENT_BALANCE_MODE}\nBalance: ${bal}\nScanning: {status}\nBase: ${BASE_AMOUNT}\nCurrent: ${current_amount}\nLevel: {martingale_level}{timer_msg}")

@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    global current_amount, martingale_level, LAST_EXECUTED_AT
    trade_id = call.data.replace("execute_","").replace("skip_","")
    if trade_id not in pending_trades:
        bot.answer_callback_query(call.id, "Expired")
        return
    data = pending_trades[trade_id]
    if "skip" in call.data:
        bot.edit_message_text(f"⏭️ SKIPPED {data['pair']} {data['direction']}", call.message.chat.id, call.message.message_id)
        del pending_trades[trade_id]
        return

    pair = data['pair']
    direction = data['direction']
    bot.edit_message_text(f"⏳ Kevin Executing {direction.upper()} on {pair} for ${current_amount}... (Level {martingale_level})", call.message.chat.id, call.message.message_id)
    try:
        status, id = Iq.buy(current_amount, pair, direction, 1)
        if not status:
            bot.send_message(call.message.chat.id, f"❌ Trade Failed: {id}")
            return
        bot.send_message(call.message.chat.id, f"✅ TRADE EXECUTED\n{pair} | {direction.upper()} | ${current_amount}\nID: {id}\nWaiting 65s for result...")
        time.sleep(65)
        profit = Iq.check_win_v3(id)

        # TIMER STARTS AFTER RESULT - 3 MIN WAIT
        LAST_EXECUTED_AT = time.time()

        if profit > 0:
            bot.send_message(call.message.chat.id, f"💰 WIN! +${round(profit,2)}\nPair: {pair}\nBalance: ${round(Iq.get_balance(),2)}\n🔄 Reset to ${BASE_AMOUNT}\n\n⏳ Next signal in 3 mins...")
            current_amount = BASE_AMOUNT
            martingale_level = 0
        else:
            martingale_level += 1
            loss_amount = current_amount
            current_amount = current_amount * 2
            if current_amount > 160:
                current_amount = BASE_AMOUNT
                martingale_level = 0
                bot.send_message(call.message.chat.id, f"📉 LOSS: -${loss_amount}\nCap reached $160. Reset to ${BASE_AMOUNT}\nBal: ${round(Iq.get_balance(),2)}\n\n⏳ Next signal in 3 mins...")
            else:
                bot.send_message(call.message.chat.id, f"📉 LOSS: -${loss_amount}\nNext: ${current_amount} (Level {martingale_level})\nBal: ${round(Iq.get_balance(),2)}\n\n⏳ Next signal in 3 mins...")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Error: {e}")
    if trade_id in pending_trades:
        del pending_trades[trade_id]

def scanner():
    while True:
        if not OWNER_ID or not Iq or not SCANNING:
            time.sleep(5)
            continue

        now = time.time()

        # FIRST SIGNAL: 2 MIN AFTER RESUME
        if LAST_EXECUTED_AT == 0:
            if RESUME_AT == 0:
                RESUME_AT = now
            if now - RESUME_AT < 120:
                time.sleep(5)
                continue
        else:
            # AFTER RESULT: WAIT 3 MIN
            if now - LAST_EXECUTED_AT < 180:
                time.sleep(5)
                continue

        for pair in PAIRS:
            if not SCANNING: break
            try:
                candles = Iq.get_candles(pair, 60, 30, time.time())
                if not candles: continue
                prices = [c['close'] for c in candles]
                rsi = get_rsi(prices)
                ema9 = get_ema(prices, 9)
                ema21 = get_ema(prices, 21)
                signal = None
                if rsi < 32 and ema9 > ema21: signal = "call"
                elif rsi > 68 and ema9 < ema21: signal = "put"
                if signal:
                    trade_id = f"{pair}_{int(time.time())}"
                    pending_trades[trade_id] = {"pair": pair, "direction": signal}
                    markup = types.InlineKeyboardMarkup()
                    btn_exec = types.InlineKeyboardButton(f"✅ EXECUTE {signal.upper()} ${current_amount}", callback_data=f"execute_{trade_id}")
                    btn_skip = types.InlineKeyboardButton("⏭️ SKIP", callback_data=f"skip_{trade_id}")
                    markup.add(btn_exec, btn_skip)
                    bot.send_message(OWNER_ID, f"📊 KEVIN SIGNAL [{CURRENT_BALANCE_MODE}]\nPair: {pair}\nDir: {signal.upper()} ({'BUY' if signal=='call' else 'SELL'})\nRSI: {rsi:.1f}\nAmount: ${current_amount} Lvl:{martingale_level}", reply_markup=markup)
                    time.sleep(30)
                    break
            except Exception as e:
                print(f"Scan {pair}: {e}")
        time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
