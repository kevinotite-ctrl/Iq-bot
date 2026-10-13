import os, time, threading, random, datetime, requests
from flask import Flask
import telebot

print("=== KEVIN V16 FIX 409 CONFLICT ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

BASE_AMOUNT=10; MAX_MARTINGALE=3; current_amount=10; martingale_level=0
OWNER_ID=None; Iq=None; SCANNING=True; LAST_SIGNAL=0; RESUME_AT=time.time()
BOT_RUNNING=False

WEEKEND_PAIRS=["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC"]
WEEKDAY_PAIRS=["EURUSD","GBPUSD","EURJPY","USDJPY","EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC"]

def get_pairs():
    return WEEKEND_PAIRS if datetime.datetime.now().weekday()>=5 else WEEKDAY_PAIRS

def delete_webhook():
    try:
        # Kill everything
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
        b=telebot.TeleBot(TOKEN)
        b.remove_webhook()
        print("✅ WEBHOOK + PENDING DELETED", flush=True)
        time.sleep(3)
    except Exception as e: print(f"delhook err {e}", flush=True)

def get_rsi(candles,p=14):
    try:
        closes=[c['close'] for c in candles]; g=[]; l=[]
        for i in range(1,len(closes)):
            d=c[closes[i]-c[i-1]] if False else None
            d=closes[i]-closes[i-1] if False else closes[i]-closes[i-1]
        # simple calc
        closes=[c['close'] for c in candles]
        gains=[]; losses=[]
        for i in range(1,len(closes)):
            d=closes[i]-closes[i-1]
            gains.append(max(d,0)); losses.append(max(-d,0))
        if len(gains)<p: return 50
        ag=sum(gains[-p:])/p; al=sum(losses[-p:])/p
        return 70 if al==0 else 100-(100/(1+ag/al))
    except: return 50

def get_ema(candles,period):
    try:
        closes=[c['close'] for c in candles]; ema=closes[0]; k=2/(period+1)
        for p in closes[1:]: ema=p*k+ema*(1-k)
        return ema
    except: return 0

def iq_connect_force():
    global Iq
    if Iq:
        try: Iq.close()
        except: pass
        Iq=None
    time.sleep(3)
    try:
        from iqoptionapi.stable_api import IQ_Option
        print(f"CONNECTING IQ {EMAIL}...", flush=True)
        Iq=IQ_Option(EMAIL,PASS)
        ok,_=Iq.connect()
        if ok:
            time.sleep(5)
            try: Iq.change_balance("PRACTICE")
            except: pass
            print(f"IQ BAL {Iq.get_balance()}", flush=True)
            return True
        return False
    except Exception as e:
        print(f"IQ ERR {e}", flush=True)
        return False

def get_candles_safe(pair):
    for _ in range(3):
        try:
            c=Iq.get_candles(pair,60,50,time.time())
            if c and len(c)>=20: return c
        except: pass
        iq_connect_force()
        time.sleep(3)
    return None

def analyze(pair):
    candles=get_candles_safe(pair)
    if not candles: return None, "No candles"
    ema7=get_ema(candles[-15:],7); ema21=get_ema(candles,21); rsi=get_rsi(candles,14); close=candles[-1]['close']
    if close>ema7>ema21 and 55<rsi<75: return "call", f"UP RSI {round(rsi,1)}"
    elif close<ema7<ema21 and 25<rsi<45: return "put", f"DOWN RSI {round(rsi,1)}"
    else: return None, f"SKIP RSI {round(rsi,1)}"

# DELETE WEBHOOK BEFORE ANYTHING
delete_webhook()
bot=telebot.TeleBot(TOKEN, threaded=False)

@app.route('/')
def home():
    try: b=round(Iq.get_balance(),2) if Iq else "NO IQ"
    except: b="?"
    return f"V16 FIX 409 BAL {b} AMT {current_amount} RUNNING {BOT_RUNNING}"

@app.route(f'/{TOKEN}', methods=['POST'])
def wh(): delete_webhook(); return "DELETED",200

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, current_amount, martingale_level
    OWNER_ID=m.chat.id; RESUME_AT=time.time(); LAST_SIGNAL=0; current_amount=BASE_AMOUNT; martingale_level=0
    if not iq_connect_force():
        bot.send_message(m.chat.id, "❌ IQ login failed")
        return
    bot.send_message(m.chat.id, f"🤖 V16 FIXED 409\n✅ No more conflict\nBal ${Iq.get_balance()}\n/resume /pause /balance")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING
    OWNER_ID=m.chat.id; SCANNING=True; RESUME_AT=time.time(); LAST_SIGNAL=0
    iq_connect_force()
    bot.send_message(m.chat.id, f"▶️ RESUMED Amt ${current_amount}")

@bot.message_handler(commands=['pause'])
def pause(m): global SCANNING; SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused")
@bot.message_handler(commands=['balance','status'])
def status(m):
    global OWNER_ID; OWNER_ID=m.chat.id
    if not Iq: iq_connect_force()
    try: b=round(Iq.get_balance(),2)
    except: b="?"
    bot.send_message(m.chat.id,f"BAL ${b} AMT ${current_amount} LVL {martingale_level}")
@bot.message_handler(commands=['scan'])
def scan(m): global OWNER_ID; OWNER_ID=m.chat.id; threading.Thread(target=do_trade, daemon=True).start()

def do_trade():
    global LAST_SIGNAL, current_amount, martingale_level
    if not OWNER_ID: return
    print("=== TRADE CYCLE FORCE RECONNECT ===", flush=True)
    iq_connect_force()
    PAIRS=get_pairs(); random.shuffle(PAIRS)
    for pair in PAIRS:
        direction, reason=analyze(pair)
        print(f"ANALYZE {pair} {direction} {reason}", flush=True)
        if direction:
            try:
                ok,tid=Iq.buy(current_amount,pair,direction,1)
                if not ok: continue
                bot.send_message(OWNER_ID,f"✅ BOUGHT {pair} {direction.upper()} ${current_amount} {reason}")
                time.sleep(65)
                profit=Iq.check_win_v3(tid); bal=Iq.get_balance(); LAST_SIGNAL=time.time()
                if profit and profit>0:
                    bot.send_message(OWNER_ID,f"💰 WIN +${round(profit,2)} Bal ${round(bal,2)} Reset"); current_amount=BASE_AMOUNT; martingale_level=0
                else:
                    martingale_level+=1
                    if martingale_level>=MAX_MARTINGALE:
                        bot.send_message(OWNER_ID,f"📉 LOSS Reset Bal ${round(bal,2)}"); current_amount=BASE_AMOUNT; martingale_level=0
                    else:
                        current_amount=BASE_AMOUNT*(2**martingale_level)
                        bot.send_message(OWNER_ID,f"📉 LOSS Next ${current_amount} Lvl {martingale_level} Bal ${round(bal,2)}")
                return
            except Exception as e: print(f"BUY ERR {e}", flush=True); continue
    LAST_SIGNAL=time.time()
    bot.send_message(OWNER_ID,f"⏭️ No signal Amt ${current_amount}")

def scanner_loop():
    while True:
        try:
            time.sleep(10)
            if not OWNER_ID or not SCANNING: continue
            if time.time()-(RESUME_AT if LAST_SIGNAL==0 else LAST_SIGNAL) < (120 if LAST_SIGNAL==0 else 180): continue
            do_trade()
        except Exception as e: print(f"SCAN ERR {e}", flush=True); time.sleep(5)

def polling_loop():
    global BOT_RUNNING
    if BOT_RUNNING:
        print("Polling already running, skipping", flush=True)
        return
    BOT_RUNNING=True
    print("🔄 Starting SINGLE polling loop", flush=True)
    delete_webhook()
    time.sleep(2)
    while True:
        try:
            # SINGLE POLLING - NO CONFLICT
            bot.infinity_polling(none_stop=True, timeout=90, long_polling_timeout=90, skip_pending=True)
        except Exception as e:
            err=str(e).lower()
            if "409" in err or "conflict" in err:
                print(f"409 CONFLICT - deleting webhook and waiting 15s {e}", flush=True)
                delete_webhook()
                time.sleep(15)
            else:
                print(f"Polling restart {e}", flush=True)
                time.sleep(5)

threading.Thread(target=scanner_loop, daemon=True).start()
# ONLY ONE POLLING THREAD
threading.Thread(target=polling_loop, daemon=True).start()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)), use_reloader=False)
