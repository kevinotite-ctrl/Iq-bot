import os, time, threading, random, datetime
from flask import Flask
import telebot

print("=== KEVIN BOT V12.1 SAFE NO-NUMPY ===", flush=True)
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
        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i-1]
            if diff > 0:
                gains.append(diff)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(-diff)
        if len(gains) < period:
            return 50
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 70
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except:
        return 50

def get_ema(candles, period):
    try:
        closes = [c['close'] for c in candles]
        if not closes:
            return 0
        ema = closes[0]
        k = 2/(period+1)
        for price in closes[1:]:
            ema = price * k + ema * (1-k)
        return ema
    except:
        return 0

def analyze(pair):
    try:
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles) < 25:
            return None, "No candles"
        ema7 = get_ema(candles[-15:], 7)
        ema21 = get_ema(candles, 21)
        rsi = get_rsi(candles, 14)
        close = candles[-1]['close']

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
    return f"V12.1 SAFE BAL {bal}"

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL
    OWNER_ID = m.chat.id
    RESUME_AT = time.time()
    LAST_SIGNAL = 0
    bal = Iq.get_balance() if Iq else "?"
    bot.send_message(m.chat.id, f"🤖 V12.1 SAFE ACTIVE\nBal ${bal}\nEMA+RSI only\nFlat $10\n/resume /pause /balance")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING
    OWNER_ID = m.chat.id
    SCANNING = True
    RESUME_AT = time.time()
    LAST_SIGNAL = 0
    bot.send_message(m.chat.id, "▶️ V12.1 RESUMED - Strong trends only, skips choppy.")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING
    SCANNING = False
    bot.send_message(m.chat.id, "⏸️ Paused")

@bot.message_handler(commands=['balance','status','pairs'])
def status(m):
    global OWNER_ID
    OWNER_ID = m.chat.id
    b = Iq.get_balance() if Iq else "?"
    bot.send_message(m.chat.id, f"BAL ${b} Pairs: {', '.join(get_pairs())} Amt ${current_amount}")

@bot.message_handler(commands=['scan'])
def scan(m):
    global OWNER_ID
    OWNER_ID = m.chat.id
    do_trade()

def do_trade():
    global LAST_SIGNAL
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
            try:
                bot.send_message(OWNER_ID, f"📊 SIGNAL {pair} {direction.upper()} ${current_amount}\n{reason}")
                status, trade_id = Iq.buy(current_amount, pair, direction, 1)
                if not status:
                    continue
                bot.send_message(OWNER_ID, f"✅ BOUGHT {pair} {direction.upper()} ${current_amount}\nID {trade_id} Wait 65s...")
                time.sleep(65)
                profit = Iq.check_win_v3(trade_id)
                bal = Iq.get_balance()
                LAST_SIGNAL = time.time()
                if profit and profit > 0:
                    bot.send_message(OWNER_ID, f"💰 WIN +${round(profit,2)}\n{reason}\nBal ${round(bal,2)}")
                else:
                    bot.send_message(OWNER_ID, f"📉 LOSS -${current_amount}\n{reason}\nBal ${round(bal,2)} Flat no double")
                return
            except Exception as e:
                print(f"BUY ERR {e}", flush=True)
                continue
    LAST_SIGNAL = time.time()
    if not found and OWNER_ID:
        bot.send_message(OWNER_ID, f"⏭️ No trend - Skip. Bal ${round(Iq.get_balance(),2)} Next 3 mins")

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
