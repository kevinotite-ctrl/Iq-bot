import os, time, threading, random, datetime, json
from flask import Flask
import telebot
print("=== V16.5 95-100% 2-MIN EXPIRY ===", flush=True)
app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")
BASE_AMOUNT = 100
MARTINGALE_AMOUNTS = [100, 200, 400]
MAX_MARTINGALE = 3
STATE_FILE = "bot_state.json"
MIN_CONFIDENCE = 95
EXPIRY = 2 # 2 MINUTES NOW

def load_state():
    global current_amount, martingale_level
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                martingale_level = data.get('level', 0)
                current_amount = MARTINGALE_AMOUNTS[martingale_level]
                return True
    except: pass
    return False

def save_state():
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({'level': martingale_level, 'amount': current_amount, 'time': time.time()}, f)
    except: pass

current_amount = BASE_AMOUNT
martingale_level = 0
load_state()
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
        if al==0: return 85
        return 100-(100/(1+ag/al))
    except: return 50

def get_ema(candles, period):
    try:
        closes=[c['close'] for c in candles]
        ema=closes[0]; k=2/(period+1)
        for p in closes[1:]: ema=p*k+ema*(1-k)
        return ema
    except: return 0

def calculate_confidence_2min(candles, ema7, ema21, rsi, direction):
    try:
        confidence = 64
        closes=[c['close'] for c in candles]
        gap = abs(ema7-ema21) / ema21 * 1000

        # 2-MIN NEEDS BIGGER GAP
        if gap > 1.2: confidence += 20
        elif gap > 0.8: confidence += 15
        elif gap > 0.4: confidence += 9
        elif gap > 0.2: confidence += 5

        # 2-MIN RSI SWEET SPOT
        if direction=="call":
            if 62 <= rsi <= 67: confidence += 18
            elif 60 <= rsi <= 70: confidence += 12
            elif 56 <= rsi <= 73: confidence += 6
        else:
            if 33 <= rsi <= 38: confidence += 18
            elif 30 <= rsi <= 40: confidence += 12
            elif 27 <= rsi <= 43: confidence += 6

        # 2-MIN NEEDS 5 CANDLES TREND FOR 100%
        last_5 = closes[-5:]
        if direction=="call":
            if last_5[0] < last_5[1] < last_5[2] < last_5[3] < last_5[4]: confidence += 14
            elif last_5[1] < last_5[2] < last_5[3] < last_5[4]: confidence += 9
            elif last_5[2] < last_5[3] < last_5[4]: confidence += 5
        else:
            if last_5[0] > last_5[1] > last_5[2] > last_5[3] > last_5[4]: confidence += 14
            elif last_5[1] > last_5[2] > last_5[3] > last_5[4]: confidence += 9
            elif last_5[2] > last_5[3] > last_5[4]: confidence += 5

        return min(100, max(60, int(confidence)))
    except: return 80

def iq_connect():
    global Iq
    try:
        from iqoptionapi.stable_api import IQ_Option
        Iq = IQ_Option(EMAIL, PASS)
        check, reason = Iq.connect()
        if check:
            Iq.change_balance("PRACTICE")
            return True
    except: pass
    return False

def analyze(pair):
    try:
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles)<25: return None, "No candles", 0
        ema7=get_ema(candles[-15:],7); ema21=get_ema(candles,21); rsi=get_rsi(candles,14); close=candles[-1]['close']
        # 2-MIN FILTERS TIGHTER
        if close>ema7>ema21 and 56<rsi<73:
            conf = calculate_confidence_2min(candles, ema7, ema21, rsi, "call")
            return "call", f"2-MIN UP EMA7 {round(ema7,5)} > EMA21 {round(ema21,5)} RSI {round(rsi,1)}", conf
        elif close<ema7<ema21 and 27<rsi<44:
            conf = calculate_confidence_2min(candles, ema7, ema21, rsi, "put")
            return "put", f"2-MIN DOWN EMA7 {round(ema7,5)} < EMA21 {round(ema21,5)} RSI {round(rsi,1)}", conf
        else:
            return None, f"SKIP RSI {round(rsi,1)}", 0
    except: return None, f"Err", 0

iq_connect()
@app.route('/')
def home(): return f"V16.5 95-100% 2MIN BAL {Iq.get_balance() if Iq else 'NO IQ'} AMT {current_amount} LVL {martingale_level}"
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL
    OWNER_ID=m.chat.id; RESUME_AT=time.time(); LAST_SIGNAL=0
    load_state()
    if not Iq: iq_connect()
    try: bal=round(Iq.get_balance(),2)
    except: bal="?"
    bot.send_message(m.chat.id, f"🤖 V16.5 2-MIN EXPIRY\nBot confidence rate >> 95-100% 💯\nBal ${bal}\nNext ${current_amount} Lvl {martingale_level}\nExpiry {EXPIRY}min | Only 95-100%\n/resume /pause /balance /reset")

@bot.message_handler(commands=['reset'])
def reset_state(m):
    global martingale_level, current_amount, OWNER_ID
    OWNER_ID=m.chat.id
    martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]; save_state()
    bot.send_message(m.chat.id, f"🔄 RESET to $100 Lvl 0")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING
    OWNER_ID=m.chat.id; SCANNING=True; RESUME_AT=time.time(); LAST_SIGNAL=0
    load_state()
    if not Iq: iq_connect()
    bot.send_message(m.chat.id, f"▶️ RESUMED 2-MIN 95-100% Saved ${current_amount} Lvl {martingale_level}")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING; SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused")

@bot.message_handler(commands=['balance','status'])
def status(m):
    global OWNER_ID; OWNER_ID=m.chat.id
    if not Iq: iq_connect()
    try: b=round(Iq.get_balance(),2)
    except: b="?"
    bot.send_message(m.chat.id, f"BAL ${b}\nNext ${current_amount} Lvl {martingale_level}\n2-MIN 95-100% Only")

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
        direction, reason, conf = analyze(pair)
        if direction:
            if conf < MIN_CONFIDENCE: continue
            try:
                bot.send_message(OWNER_ID,f"Bot confidence rate >> {conf}% 💯\n💯 2-MIN PERFECT {pair} {direction.upper()} {conf}% Confidence\nAmt ${current_amount} Lvl {martingale_level} Exp {EXPIRY}min\n{reason}\n{'🚀 100% 2-MIN MAX!' if conf==100 else '🔥 95%+ 2-MIN ULTRA'}")
                status, trade_id = Iq.buy(current_amount, pair, direction, EXPIRY)
                if not status: continue
                bot.send_message(OWNER_ID,f"✅ BOUGHT {pair} {direction.upper()} ${current_amount} Lvl {martingale_level} Conf {conf}% Exp {EXPIRY}min\nWait 125s...")
                time.sleep(125)
                profit=Iq.check_win_v3(trade_id); bal=Iq.get_balance(); LAST_SIGNAL=time.time()
                if profit and profit>0:
                    bot.send_message(OWNER_ID,f"💰 WIN +${round(profit,2)} Bot confidence rate >> {conf}% 2-MIN CORRECT 💯\nBal ${round(bal,2)}\n🔄 Reset to $100")
                    bot.send_message(OWNER_ID,"🤑")
                    martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]; save_state()
                else:
                    bot.send_message(OWNER_ID,f"📉 LOSS -${current_amount} Bot confidence rate >> {conf}% 2-MIN FAILED\nBal ${round(bal,2)}")
                    bot.send_message(OWNER_ID,"😮‍💨")
                    martingale_level+=1
                    if martingale_level >= MAX_MARTINGALE:
                        bot.send_message(OWNER_ID,f"⚠️ 3 losses reset to $100")
                        martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]
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
        bot.send_message(OWNER_ID,f"⏭️ No 95-100% 2-MIN signal | Next ${current_amount} Lvl {martingale_level} | Bal ${bal}")

def scanner():
    while True:
        try:
            time.sleep(10)
            if not OWNER_ID or not SCANNING: continue
            if time.time() - (RESUME_AT if LAST_SIGNAL==0 else LAST_SIGNAL) < (120 if LAST_SIGNAL==0 else 240): continue
            do_trade()
        except Exception as e: print(f"SCAN ERR {e}", flush=True); time.sleep(5)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(none_stop=True), daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
