import os, time, threading, random, datetime, json
from flask import Flask
import telebot

print("=== V15 PERSISTENT 100-200-400 ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

BASE_AMOUNT = 100
MARTINGALE_AMOUNTS = [100, 200, 400]
MAX_MARTINGALE = 3

STATE_FILE = "bot_state.json"

# Load saved state if exists
def load_state():
    global current_amount, martingale_level
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                martingale_level = data.get('level', 0)
                current_amount = MARTINGALE_AMOUNTS[martingale_level]
                print(f"LOADED STATE Lvl {martingale_level} Amt {current_amount}", flush=True)
                return True
    except Exception as e:
        print(f"LOAD ERR {e}", flush=True)
    return False

def save_state():
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({'level': martingale_level, 'amount': current_amount, 'time': time.time()}, f)
        print(f"SAVED STATE Lvl {martingale_level} Amt {current_amount}", flush=True)
    except Exception as e:
        print(f"SAVE ERR {e}", flush=True)

current_amount = BASE_AMOUNT
martingale_level = 0
load_state() # Try load on boot

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
        Iq = IQ_Option(EMAIL, PASS)
        check, reason = Iq.connect()
        if check:
            Iq.change_balance("PRACTICE")
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
def home(): return f"V15 REMEMBER BAL {Iq.get_balance() if Iq else 'NO IQ'} AMT {current_amount} LVL {martingale_level}"

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL
    OWNER_ID=m.chat.id; RESUME_AT=time.time(); LAST_SIGNAL=0
    load_state() # Load on start too
    if not Iq: iq_connect()
    try: bal=round(Iq.get_balance(),2)
    except: bal="?"
    bot.send_message(m.chat.id, f"🤖 V15 REMEMBERS 100-200-400\nBal ${bal}\nSaved Lvl {martingale_level} Amt ${current_amount}\nSequence 100->200->400->reset\n🤑 Win | 😮‍💨 Loss\n/resume /pause /balance /reset")

@bot.message_handler(commands=['reset'])
def reset_state(m):
    global martingale_level, current_amount, OWNER_ID
    OWNER_ID=m.chat.id
    martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]
    save_state()
    bot.send_message(m.chat.id, f"🔄 MANUALLY RESET to $100 Lvl 0")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING
    OWNER_ID=m.chat.id; SCANNING=True; RESUME_AT=time.time(); LAST_SIGNAL=0
    load_state()
    if not Iq: iq_connect()
    bot.send_message(m.chat.id, f"▶️ RESUMED Saved ${current_amount} Lvl {martingale_level}")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING; SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused - State saved")

@bot.message_handler(commands=['balance','status'])
def status(m):
    global OWNER_ID; OWNER_ID=m.chat.id
    if not Iq: iq_connect()
    try: b=round(Iq.get_balance(),2)
    except: b="?"
    bot.send_message(m.chat.id, f"BAL ${b}\nSaved ${current_amount} Lvl {martingale_level}\nFile exists: {os.path.exists(STATE_FILE)}")

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
        if direction:
            try:
                bot.send_message(OWNER_ID,f"📊 SIGNAL {pair} {direction.upper()}\nAmt ${current_amount} Lvl {martingale_level}\n{reason}")
                status, trade_id = Iq.buy(current_amount, pair, direction, 1)
                if not status: continue
                bot.send_message(OWNER_ID,f"✅ BOUGHT {pair} {direction.upper()} ${current_amount} Lvl {martingale_level}\nWait 65s...")
                time.sleep(65)
                profit=Iq.check_win_v3(trade_id); bal=Iq.get_balance(); LAST_SIGNAL=time.time()
                if profit and profit>0:
                    bot.send_message(OWNER_ID,f"💰 WIN +${round(profit,2)}\nBal ${round(bal,2)}\n🔄 Reset to $100")
                    bot.send_message(OWNER_ID,"🤑")
                    martingale_level=0
                    current_amount=MARTINGALE_AMOUNTS[0]
                    save_state()
                else:
                    bot.send_message(OWNER_ID,f"📉 LOSS -${current_amount}\nBal ${round(bal,2)}")
                    bot.send_message(OWNER_ID,"😮‍💨")
                    martingale_level+=1
                    if martingale_level >= MAX_MARTINGALE:
                        bot.send_message(OWNER_ID,f"⚠️ 3 losses reset to $100")
                        martingale_level=0
                        current_amount=MARTINGALE_AMOUNTS[0]
                    else:
                        current_amount=MARTINGALE_AMOUNTS[martingale_level]
                        bot.send_message(OWNER_ID,f"📈 Next ${current_amount} Lvl {martingale_level}")
                    save_state()
                return
            except Exception as e: print(f"BUY ERR {e}", flush=True); continue
    LAST_SIGNAL=time.time()
    if OWNER_ID:
        try: bal=round(Iq.get_balance(),2)
        except: bal="?"
        bot.send_message(OWNER_ID,f"⏭️ No trend Skip | Next ${current_amount} Lvl {martingale_level} | Bal ${bal}")

def scanner():
    while True:
        try:
            time.sleep(10)
            if not OWNER_ID or not SCANNING: continue
            if time.time() - (RESUME_AT if LAST_SIGNAL==0 else LAST_SIGNAL) < (120 if LAST_SIGNAL==0 else 180): continue
            do_trade()
        except Exception as e: print(f"SCAN ERR {e}", flush=True); time.sleep(5)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(none_stop=True), daemon=True).start()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
