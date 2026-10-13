import os, time, threading, random, datetime, requests, logging
logging.getLogger().setLevel(logging.CRITICAL)
for l in ["", "root", "iqoptionapi", "iqoptionapi.stable_api"]:
    lg = logging.getLogger(l)
    try: lg.setLevel(logging.CRITICAL); lg.propagate=False
    except: pass
from flask import Flask
import telebot
print("=== KEVIN V22 FIX NoneType ===", flush=True)
app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")
BASE_AMOUNT=10; MAX_MARTINGALE=3; current_amount=10; martingale_level=0
OWNER_ID=None; Iq=None; SCANNING=True; LAST_SIGNAL=0; RESUME_AT=time.time()
IQ_LOCK=threading.RLock(); BOT_RUNNING=False
WEEKEND_PAIRS=["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC","XAUUSD-OTC","EURJPY-OTC","USDJPY-OTC","GBPJPY-OTC"]
WEEKDAY_PAIRS=["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC","XAUUSD-OTC","EURJPY-OTC","USDJPY-OTC"]
def get_pairs(): return WEEKEND_PAIRS
def delete_webhook():
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
        b=telebot.TeleBot(TOKEN); b.remove_webhook()
        print("✅ WEBHOOK DELETED", flush=True); time.sleep(2)
    except: pass
def get_rsi(candles,p=14):
    try:
        closes=[c['close'] for c in candles]; g=[]; l=[]
        for i in range(1,len(closes)):
            d=closes[i]-closes[i-1]; g.append(max(d,0)); l.append(max(-d,0))
        if len(g)<p: return 50
        ag=sum(g[-p:])/p; al=sum(l[-p:])/p
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
    with IQ_LOCK:
        if Iq:
            try: Iq.close()
            except: pass
            Iq=None
        time.sleep(2)
        try:
            from iqoptionapi.stable_api import IQ_Option
            print(f"CONNECTING IQ {EMAIL}...", flush=True)
            Iq=IQ_Option(EMAIL,PASS)
            ok,reason=Iq.connect()
            print(f"IQ CONNECT {ok} {reason}", flush=True)
            if ok:
                time.sleep(5)
                try: Iq.change_balance("PRACTICE")
                except: pass
                print(f"✅ IQ READY BAL {Iq.get_balance()}", flush=True)
                return True
            return False
        except Exception as e:
            print(f"IQ ERR {e}", flush=True); return False

def get_open_pairs():
    try:
        with IQ_LOCK:
            if Iq is None: return WEEKEND_PAIRS
            all_open=Iq.get_all_open_time()
        if not all_open or not isinstance(all_open, dict):
            print(f"get_all_open_time None, fallback OTC", flush=True)
            return WEEKEND_PAIRS
        open_dict=all_open.get('turbo', {}) or all_open.get('binary', {}) or {}
        if not open_dict: return WEEKEND_PAIRS
        all_pairs=list(set(WEEKEND_PAIRS+WEEKDAY_PAIRS))
        open_pairs=[]
        for p in all_pairs:
            data=open_dict.get(p)
            if isinstance(data, dict) and data.get('open'): open_pairs.append(p)
            elif data is True: open_pairs.append(p)
        if not open_pairs: return WEEKEND_PAIRS
        print(f"✅ OPEN PAIRS: {open_pairs}", flush=True)
        return open_pairs
    except Exception as e:
        print(f"get_open_pairs err {e} fallback", flush=True)
        return WEEKEND_PAIRS

def get_candles_safe(pair):
    global Iq
    for _ in range(3):
        try:
            with IQ_LOCK:
                if Iq is None: raise Exception("Iq None")
                c=Iq.get_candles(pair,60,50,time.time())
            if c and len(c)>=20: return c
        except Exception as e:
            print(f"candles retry {pair} {e}", flush=True)
        iq_connect_force(); time.sleep(2)
    return None
def analyze_loose(pair):
    candles=get_candles_safe(pair)
    if not candles: return None,"No candles"
    ema7=get_ema(candles[-15:],7); rsi=get_rsi(candles,14); close=candles[-1]['close']
    if close>ema7 and 40<rsi<85: return "call",f"UP RSI {round(rsi,1)}"
    elif close<ema7 and 15<rsi<60: return "put",f"DOWN RSI {round(rsi,1)}"
    else:
        if rsi>52: return "call",f"LOOSE UP RSI {round(rsi,1)}"
        elif rsi<48: return "put",f"LOOSE DOWN RSI {round(rsi,1)}"
        return None,f"SKIP RSI {round(rsi,1)}"
delete_webhook()
bot=telebot.TeleBot(TOKEN, threaded=False)
@app.route('/')
def home():
    try:
        with IQ_LOCK: b=Iq.get_balance() if Iq else "NO IQ"
    except: b="?"
    return f"V22 FIX BAL {b}"
@app.route(f'/{TOKEN}', methods=['POST'])
def wh(): delete_webhook(); return "DELETED",200
@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, current_amount, martingale_level
    OWNER_ID=m.chat.id; RESUME_AT=time.time(); LAST_SIGNAL=0; current_amount=BASE_AMOUNT; martingale_level=0
    bot.send_message(m.chat.id,"🔄 V22 Connecting...")
    if not iq_connect_force(): bot.send_message(m.chat.id,"❌ IQ fail"); return
    open_pairs=get_open_pairs()
    bot.send_message(m.chat.id,f"🤖 V22 FIXED NoneType\nOpen: {', '.join(open_pairs)}\nBal ${Iq.get_balance()}\n/testbuy /scan /balance")
@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING
    OWNER_ID=m.chat.id; SCANNING=True; RESUME_AT=time.time(); LAST_SIGNAL=0
    iq_connect_force(); bot.send_message(m.chat.id,f"▶️ RESUMED Amt ${current_amount}")
@bot.message_handler(commands=['pause'])
def pause(m): global SCANNING; SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused")
@bot.message_handler(commands=['balance','status'])
def status(m):
    global OWNER_ID; OWNER_ID=m.chat.id
    try:
        with IQ_LOCK: bal=Iq.get_balance() if Iq else None
        if bal is None:
            iq_connect_force()
            with IQ_LOCK: bal=Iq.get_balance()
        open_pairs=get_open_pairs()
        bot.send_message(m.chat.id,f"BAL ${round(bal,2)} AMT ${current_amount} LVL {martingale_level}\nOpen: {', '.join(open_pairs[:5])}")
    except Exception as e:
        bot.send_message(m.chat.id,f"BAL $9989 cache AMT ${current_amount} LVL {martingale_level}\nErr {e}"); iq_connect_force()
@bot.message_handler(commands=['scan'])
def scan(m): global OWNER_ID; OWNER_ID=m.chat.id; bot.send_message(m.chat.id,"🔍 Scanning OPEN OTC..."); threading.Thread(target=do_trade, daemon=True).start()
@bot.message_handler(commands=['testbuy'])
def testbuy(m):
    global OWNER_ID; OWNER_ID=m.chat.id
    bot.send_message(m.chat.id,"🧪 Testing BUY...")
    try:
        open_pairs=get_open_pairs()
        test_pair=open_pairs[0] if open_pairs else "EURUSD-OTC"
        with IQ_LOCK:
            if Iq is None: iq_connect_force()
            status,tid=Iq.buy(10,test_pair,"call",1)
        if status:
            bot.send_message(m.chat.id,f"✅ BUY PLACED {test_pair} ID {tid} 65s wait...")
            time.sleep(65)
            with IQ_LOCK: profit=Iq.check_win_v3(tid); bal=Iq.get_balance()
            bot.send_message(m.chat.id,f"Result {profit} Bal ${round(bal,2)}")
        else:
            bot.send_message(m.chat.id,f"❌ Failed {test_pair}: {tid}")
    except Exception as e:
        bot.send_message(m.chat.id,f"❌ Err {e}"); print(f"testbuy err {e}", flush=True)
@bot.message_handler(commands=['loosetrade'])
def loosetrade(m): global OWNER_ID; OWNER_ID=m.chat.id; bot.send_message(m.chat.id,"🔥 LOOSE start"); threading.Thread(target=do_trade, daemon=True).start()
def do_trade():
    global LAST_SIGNAL, current_amount, martingale_level
    if not OWNER_ID: return
    if Iq is None: iq_connect_force()
    PAIRS=get_open_pairs(); random.shuffle(PAIRS)
    print(f"SCANNING OPEN ONLY {PAIRS}", flush=True)
    try: bot.send_message(OWNER_ID,f"🔍 Scanning {', '.join(PAIRS)} Amt ${current_amount}")
    except: pass
    for pair in PAIRS:
        direction,reason=analyze_loose(pair)
        print(f"ANALYZE {pair} {direction} {reason}", flush=True)
        if direction:
            try:
                with IQ_LOCK:
                    if Iq is None: raise Exception("Iq None")
                    status,tid=Iq.buy(current_amount,pair,direction,1)
                if not status:
                    print(f"BUY FAILED {pair} {tid} next", flush=True); continue
                bot.send_message(OWNER_ID,f"✅ BOUGHT {pair} {direction.upper()} ${current_amount}\n{reason}")
                time.sleep(65)
                with IQ_LOCK: profit=Iq.check_win_v3(tid); bal=Iq.get_balance()
                LAST_SIGNAL=time.time()
                if profit and profit>0:
                    bot.send_message(OWNER_ID,f"💰 WIN +${round(profit,2)} Bal ${round(bal,2)} Reset")
                    current_amount=BASE_AMOUNT; martingale_level=0
                else:
                    martingale_level+=1
                    if martingale_level>=MAX_MARTINGALE:
                        bot.send_message(OWNER_ID,f"📉 LOSS Reset Bal ${round(bal,2)}"); current_amount=BASE_AMOUNT; martingale_level=0
                    else:
                        current_amount=BASE_AMOUNT*(2**martingale_level); bot.send_message(OWNER_ID,f"📉 LOSS Next ${current_amount} Lvl {martingale_level} Bal ${round(bal,2)}")
                return
            except Exception as e: print(f"BUY ERR {e}", flush=True); continue
    LAST_SIGNAL=time.time()
    try: bot.send_message(OWNER_ID,f"⏭️ No signal Amt ${current_amount}")
    except: pass
def scanner_loop():
    while True:
        try:
            time.sleep(10)
            if not OWNER_ID or not SCANNING: continue
            wait_time=120 if LAST_SIGNAL==0 else 180
            if time.time()-(RESUME_AT if LAST_SIGNAL==0 else LAST_SIGNAL) < wait_time: continue
            print("Auto scanner trigger", flush=True); do_trade()
        except Exception as e: print(f"SCAN ERR {e}", flush=True); time.sleep(5)
def polling_loop():
    global BOT_RUNNING
    if BOT_RUNNING: return
    BOT_RUNNING=True; delete_webhook(); time.sleep(3)
    print("🔄 Starting polling V22", flush=True)
    while True:
        try: bot.infinity_polling(none_stop=True, timeout=90, long_polling_timeout=90, skip_pending=True)
        except Exception as e:
            if "409" in str(e).lower(): print("409 15s", flush=True); delete_webhook(); time.sleep(15)
            else: print(f"Polling err {e}", flush=True); time.sleep(5)
threading.Thread(target=scanner_loop, daemon=True).start()
threading.Thread(target=polling_loop, daemon=True).start()
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)), use_reloader=False)
