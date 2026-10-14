import os, time, threading, random, datetime
from flask import Flask
import telebot

print("=== KEVIN V25 FINAL - NO CONFLICT ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

# === SETTINGS ===
BASE_AMOUNT = 10
MAX_MARTINGALE = 3
current_amount = BASE_AMOUNT
martingale_level = 0

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
        closes=[c['close'] for c in candles]
        gains=[]; losses=[]
        for i in range(1,len(closes)):
            d=closes[i]-closes[i-1]
            gains.append(max(d,0)); losses.append(max(-d,0))
        if len(gains)<period: return 50
        ag=sum(gains[-period:])/period; al=sum(losses[-period:])/period
        if al==0: return 70
        return 100-(100/(1+ag/al))
    except: return 50

def get_ema(candles, period):
    try:
        closes=[c['close'] for c in candles]
        ema=closes[0]; k=2/(period+1)
        for p in closes[1:]: ema=p*k+ema*(1-k)
        return ema
    except: return 0

def iq_connect():
    global Iq
    try:
        from iqoptionapi.stable_api import IQ_Option
        print("Connecting IQ...", flush=True)
        Iq = IQ_Option(EMAIL, PASS)
        check, reason = Iq.connect()
        print(f"IQ CONNECT {check} {reason}", flush=True)
        if check:
            Iq.change_balance("PRACTICE")
            print(f"BAL {Iq.get_balance()}", flush=True)
            return True
    except Exception as e: print(f"IQ ERR {e}", flush=True)
    return False

def analyze(pair):
    try:
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles)<25: return None, "No candles"
        ema7=get_ema(candles[-15:],7); ema21=get_ema(candles,21); rsi=get_rsi(candles,14); close=candles[-1]['close']
        if close>ema7>ema21 and 55<rsi<75: return "call", f"UP EMA7 {round(ema7,5)} > EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        elif close<ema7<ema21 and 25<rsi<45: return "put", f"DOWN EMA7 {round(ema7,5)} < EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        else: return None, f"SKIP RSI {round(rsi,1)}"
    except Exception as e: return None, f"Err {e}"

iq_connect()

@app.route('/')
def home():
    try: b=Iq.get_balance() if Iq else "NO IQ"
    except: b="?"
    return f"V25 LIVE BAL {b} AMT {current_amount} LVL {martingale_level}"

# === TELEGRAM BOT WITH AUTO WEBHOOK FIX ===
bot = telebot.TeleBot(TOKEN, threaded=False)

# THIS FIXES YOUR 404 + CONFLICT ERROR
try:
    print("Removing old webhook...", flush=True)
    bot.remove_webhook()
    time.sleep(3)
    print("Webhook removed OK", flush=True)
except Exception as e:
    print(f"Webhook remove: {e}", flush=True)

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, current_amount, martingale_level
    OWNER_ID=m.chat.id; RESUME_AT=time.time(); LAST_SIGNAL=0
    current_amount=BASE_AMOUNT; martingale_level=0
    if not Iq: iq_connect()
    try: bal=round(Iq.get_balance(),2)
    except: bal="?"
    bot.send_message(m.chat.id, f"🤖 KEVIN V25 LIVE FIXED\nBal ${bal}\nBase ${BASE_AMOUNT} Max x{MAX_MARTINGALE}\n$10 -> $20 -> $40 then reset\n/resume /pause /balance /scan")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING
    OWNER_ID=m.chat.id; SCANNING=True; RESUME_AT=time.time(); LAST_SIGNAL=0
    if not Iq: iq_connect()
    bot.send_message(m.chat.id, f"▶️ RESUMED Lvl {martingale_level} Amt ${current_amount}")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING; SCANNING=False
    bot.send_message(m.chat.id,"⏸️ Paused")

@bot.message_handler(commands=['balance','status','pairs'])
def status(m):
    global OWNER_ID
    OWNER_ID=m.chat.id
    if not Iq: iq_connect()
    try: b=round(Iq.get_balance(),2)
    except: b="?"
    bot.send_message(m.chat.id, f"BAL ${b}\nAmt ${current_amount} Lvl {martingale_level}/{MAX_MARTINGALE}\nPairs: {', '.join(get_pairs())}")

@bot.message_handler(commands=['scan'])
def scan(m):
    global OWNER_ID; OWNER_ID=m.chat.id; do_trade()

def do_trade():
    global LAST_SIGNAL, current_amount, martingale_level
    if not Iq and not iq_connect():
        if OWNER_ID: bot.send_message(OWNER_ID,"❌ IQ login failed")
        LAST_SIGNAL=time.time(); return
    if not OWNER_ID: return
    PAIRS=get_pairs(); random.shuffle(PAIRS)
    for pair in PAIRS:
        direction, reason = analyze(pair)
        print(f"ANALYZE {pair} {direction} {reason} AMT {current_amount} LVL {martingale_level}", flush=True)
        if direction:
            try:
                bot.send_message(OWNER_ID,f"📊 SIGNAL {pair} {direction.upper()}\nAmt ${current_amount} Lvl {martingale_level}\n{reason}")
                status, trade_id = Iq.buy(current_amount, pair, direction, 1)
                if not status: continue
                bot.send_message(OWNER_ID,f"✅ BOUGHT {pair} {direction.upper()} ${current_amount} Lvl {martingale_level}\nWait 65s...")
                time.sleep(65)
                profit=Iq.check_win_v3(trade_id); bal=Iq.get_balance(); LAST_SIGNAL=time.time()

                if profit and profit>0:
                    bot.send_message(OWNER_ID,f"💰 WIN +${round(profit,2)}\n{reason}\nBal ${round(bal,2)}\n🔄 Reset to ${BASE_AMOUNT}")
                    current_amount=BASE_AMOUNT
                    martingale_level=0
                else:
                    martingale_level+=1
                    if martingale_level >= MAX_MARTINGALE:
                        bot.send_message(OWNER_ID,f"📉 LOSS -${current_amount}\n{reason}\n⚠️ 3 losses -> RESET to ${BASE_AMOUNT}\nBal ${round(bal,2)}")
                        current_amount=BASE_AMOUNT
                        martingale_level=0
                    else:
                        current_amount = BASE_AMOUNT * (2 ** martingale_level)
                        bot.send_message(OWNER_ID,f"📉 LOSS\n{reason}\n📈 Next ${current_amount} Lvl {martingale_level}\nBal ${round(bal,2)}")
                return
            except Exception as e: print(f"BUY ERR {e}", flush=True); continue
    LAST_SIGNAL=time.time()
    try: bal=round(Iq.get_balance(),2)
    except: bal="?"
    if OWNER_ID: bot.send_message(OWNER_ID,f"⏭️ No trend Skip | Amt ${current_amount} Lvl {martingale_level} | Bal ${bal}")

def scanner():
    while True:
        try:
            time.sleep(10)
            if not OWNER_ID or not SCANNING: continue
            if time.time() - (RESUME_AT if LAST_SIGNAL==0 else LAST_SIGNAL) < (120 if LAST_SIGNAL==0 else 180): continue
            do_trade()
        except Exception as e: print(f"SCAN ERR {e}", flush=True); time.sleep(5)

def bot_polling():
    while True:
        try:
            print("Polling started...", flush=True)
            bot.infinity_polling(timeout=60, long_polling_timeout=60, none_stop=True)
        except Exception as e:
            print(f"Polling error {e}, retry in 5s", flush=True)
            time.sleep(5)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=bot_polling, daemon=True).start()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
