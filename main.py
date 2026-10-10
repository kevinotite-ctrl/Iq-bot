import os, time, threading, random, datetime
from flask import Flask
import telebot
import numpy as np

print("=== KEVIN BOT V12 SAFE TREND ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

BASE_AMOUNT = 10
current_amount = BASE_AMOUNT
OWNER_ID = None
Iq = None
SCANNING = True
LAST_SIGNAL = 0
RESUME_AT = time.time()

WEEKEND_PAIRS = ["EURUSD-OTC", "GBPUSD-OTC"]
WEEKDAY_PAIRS = ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC"]

def get_pairs():
    wd = datetime.datetime.now().weekday()
    return WEEKEND_PAIRS if wd >= 5 else WEEKDAY_PAIRS

def get_rsi(candles, period=14):
    try:
        closes = [c['close'] for c in candles]
        deltas = np.diff(closes)
        gains = np.where(deltas>0, deltas, 0)
        losses = np.where(deltas<0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 70
        rs = avg_gain / avg_loss
        rsi = 100 - (100/(1+rs))
        return rsi
    except:
        return 50

def get_ema(candles, period):
    try:
        closes = [c['close'] for c in candles]
        ema = closes[0]
        k = 2/(period+1)
        for price in closes[1:]:
            ema = price * k + ema * (1-k)
        return ema
    except:
        return closes[-1] if candles else 0

def analyze(pair):
    try:
        # Get last 50 candles 1 min
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles) < 25:
            return None, "No candles"
        ema7 = get_ema(candles[-15:], 7)
        ema21 = get_ema(candles, 21)
        rsi = get_rsi(candles, 14)
        close = candles[-1]['close']

        # TREND LOGIC
        if close > ema7 > ema21 and rsi > 55 and rsi < 75:
            return "call", f"UPTREND EMA7 {round(ema7,5)} > EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        elif close < ema7 < ema21 and rsi < 45 and rsi > 25:
            return "put", f"DOWNTREND EMA7 {round(ema7,5)} < EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        else:
            return None, f"NO TREND close {close} EMA7 {round(ema7,5)} EMA21 {round(ema21,5)} RSI {round(rsi,1)} -> SKIP"
    except Exception as e:
        return None, f"Analyze err {e}"

try:
    from iqoptionapi.stable_api import IQ_Option
    Iq = IQ_Option(EMAIL, PASS)
    check, reason = Iq.connect()
    print(f"IQ CONNECT {check} {reason}", flush=True)
    if check:
        Iq.change_balance("PRACTICE")
        print(f"BAL {Iq.get_balance()}", flush=True)
except Exception as e:
    print(f"IQ ERR {e}", flush=True)

@app.route('/')
def home():
    bal = Iq.get_balance() if Iq else "NO IQ"
    return f"V12 SAFE TREND BAL {bal} AMT {current_amount}"

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL
    OWNER_ID = m.chat.id
    RESUME_AT = time.time()
    LAST_SIGNAL = 0
    bal = Iq.get_balance() if Iq else "?"
    bot.send_message(m.chat.id, f"🤖 V12 SAFE TREND ACTIVE\nBal ${bal}\nStrategy: EMA7/21 + RSI\nNo martingale - flat ${BASE_AMOUNT}\nSkip if no trend\n/resume /pause /balance /pairs")

@bot.message_handler(commands=['pairs'])
def show_pairs(m):
    bot.send_message(m.chat.id, f"Pairs now: {', '.join(get_pairs())}")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING
    OWNER_ID = m.chat.id
    SCANNING = True
    RESUME_AT = time.time()
    LAST_SIGNAL = 0
    bot.send_message(m.chat.id, "▶️ V12 SAFE RESUMED - Now only trades STRONG trends. May skip some cycles if market choppy.")

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
    bot.send_message(m.chat.id, f"BAL ${b} Amt ${current_amount} Flat mode")

@bot.message_handler(commands=['scan'])
def scan(m):
    global OWNER_ID
    OWNER_ID = m.chat.id
    do_trade()

def do_trade():
    global current_amount, LAST_SIGNAL
    if not Iq or not OWNER_ID:
        return
    PAIRS = get_pairs()
    random.shuffle(PAIRS)

    found = False
    for pair in PAIRS:
        direction, reason = analyze(pair)
        print(f"ANALYZE {pair} -> {direction} | {reason}", flush=True)
        if direction:
            found = True
            if OWNER_ID:
                bot.send_message(OWNER_ID, f"📊 STRONG SIGNAL {pair}\n{reason}\nBuying {direction.upper()} ${current_amount}")
            try:
                status, trade_id = Iq.buy(current_amount, pair, direction, 1)
                if not status:
                    continue
                if OWNER_ID:
                    bot.send_message(OWNER_ID, f"✅ BOUGHT {pair} {direction.upper()} ${current_amount}\nID {trade_id}\nWait 65s...")
                time.sleep(65)
                profit = Iq.check_win_v3(trade_id)
                bal = Iq.get_balance()
                LAST_SIGNAL = time.time()
                if profit and profit > 0:
                    bot.send_message(OWNER_ID, f"💰 WIN +${round(profit,2)} | {reason}\nBal ${round(bal,2)}\nNext in 3 mins")
                else:
                    bot.send_message(OWNER_ID, f"📉 LOSS -${current_amount} | {reason}\nBal ${round(bal,2)}\nFlat ${BASE_AMOUNT} - No double\nNext in 3 mins")
                return
            except Exception as e:
                print(f"BUY ERR {e}", flush=True)
                continue

    # No trend found
    LAST_SIGNAL = time.time()
    if OWNER_ID and not found:
        bot.send_message(OWNER_ID, f"⏭️ No strong trend found in {', '.join(PAIRS)} - Skipping this round. Will check again in 3 mins. Bal ${round(Iq.get_balance(),2)}")

def scanner():
    while True:
        try:
            time.sleep(10)
            if not OWNER_ID or not SCANNING:
                continue
            now = time.time()
            need = 120 if LAST_SIGNAL==0 else 180
            last = RESUME_AT if LAST_SIGNAL==0 else LAST_SIGNAL
            if now - last < need:
                continue
            do_trade()
        except Exception as e:
            print(f"SCANNER ERR {e}", flush=True)
            time.sleep(5)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(none_stop=True), daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
