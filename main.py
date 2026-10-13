import os, time, threading, random, json
from flask import Flask, request
import telebot
print("=== V17.5.2 FIX get_candles need reconnect ===", flush=True)
app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")
CHANNEL_ID = -1003709183793
BASE_AMOUNT=10; MARTINGALE_AMOUNTS=[10,20,40]; MAX_MARTINGALE=3
STATE_FILE="bot_state.json"; EXPIRY=1; SCAN_INTERVAL=90
RENDER_URL=os.getenv("RENDER_EXTERNAL_URL") or ""

def load_state():
    global current_amount, martingale_level
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE,'r') as f:
                d=json.load(f); martingale_level=d.get('level',0)
                current_amount=MARTINGALE_AMOUNTS[martingale_level] if martingale_level<len(MARTINGALE_AMOUNTS) else MARTINGALE_AMOUNTS[0]
    except: pass
def save_state():
    try:
        with open(STATE_FILE,'w') as f: json.dump({'level':martingale_level,'amount':current_amount}, f)
    except: pass

current_amount=BASE_AMOUNT; martingale_level=0; load_state()
OWNER_ID=None; Iq=None; SCANNING=True; NEXT_SCAN_AT=time.time()+30; ALERT_SENT=False; LAST_IQ_CONNECT=0

ALL_OTC_PAIRS=["EURUSD-OTC","GBPUSD-OTC","EURJPY-OTC","GBPJPY-OTC","EURGBP-OTC","AUDCAD-OTC","USDCHF-OTC","EURAUD-OTC","AUDUSD-OTC","USDJPY-OTC"]
def get_pairs(): return random.sample(ALL_OTC_PAIRS,4)
def get_countdown():
    r=int(NEXT_SCAN_AT-time.time());
    if r<0: r=0
    return f"{r//60:02d}:{r%60:02d}", r

bot=telebot.TeleBot(TOKEN)
def send_private(t):
    try:
        if OWNER_ID: bot.send_message(OWNER_ID,t)
    except: pass
def send_channel(t):
    try: bot.send_message(CHANNEL_ID,t)
    except: pass

def iq_connect(force=False):
    global Iq, LAST_IQ_CONNECT
    # Don't spam reconnect every sec
    if not force and time.time()-LAST_IQ_CONNECT<15: return Iq is not None
    try:
        from iqoptionapi.stable_api import IQ_Option
        print("IQ CONNECTING...", flush=True)
        Iq=IQ_Option(EMAIL,PASS)
        ok,_=Iq.connect()
        if ok:
            Iq.change_balance("PRACTICE")
            LAST_IQ_CONNECT=time.time()
            print(f"IQ CONNECTED BAL {Iq.get_balance()}", flush=True)
            return True
        else:
            print("IQ CONNECT FAILED", flush=True)
    except Exception as e: print(f"IQ err {e}", flush=True)
    LAST_IQ_CONNECT=time.time()
    return False

def get_candles_safe(pair, tf=60, count=50):
    # THE FIX FOR YOUR LOG ERROR
    global Iq
    for attempt in range(3):
        try:
            if not Iq:
                iq_connect(force=True); time.sleep(1)
            candles = Iq.get_candles(pair, tf, count, time.time())
            if candles and len(candles)>=10:
                return candles
            # Empty candles = disconnected
            print(f"get_candles empty {pair} attempt {attempt}", flush=True)
            iq_connect(force=True)
            time.sleep(2)
        except Exception as e:
            err=str(e).lower()
            print(f"get_candles error {pair} {e}", flush=True)
            if "need reconnect" in err or "get_candles" in err:
                iq_connect(force=True)
                time.sleep(2)
            else:
                time.sleep(1)
    return None

def get_rsi(candles,p=14):
    try:
        c=[x['close'] for x in candles]; g=[]; l=[]
        for i in range(1,len(c)):
            d=c[i]-c[i-1]; g.append(max(d,0)); l.append(max(-d,0))
        if len(g)<p: return 50
        ag=sum(g[-p:])/p; al=sum(l[-p:])/p
        if al==0: return 50
        return 100-(100/(1+ag/al))
    except: return 50

def get_ema(candles,period):
    try:
        closes=[x['close'] for x in candles]; ema=closes[0]; k=2/(period+1)
        for p in closes[1:]: ema=p*k+ema*(1-k)
        return ema
    except: return 0

def analyze(pair):
    candles=get_candles_safe(pair)
    if not candles: return None, f"{pair} No candles (IQ reconnecting...)"
    try:
        ema7=get_ema(candles[-15:],7); ema21=get_ema(candles,21); rsi=get_rsi(candles,14); close=candles[-1]['close']
        if close>ema21 and 30<rsi<70 and close>ema7:
            return "call", f"UP C {round(close,5)} > EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        elif close<ema21 and 30<rsi<70 and close<ema7:
            return "put", f"DOWN C {round(close,5)} < EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        else:
            return None, f"{pair} SKIP RSI:{round(rsi,1)} C:{round(close,5)} EMA7:{round(ema7,5)}"
    except Exception as e: return None, f"{pair} Err {e}"

def send_channel_big_signal(pair, direction, reason):
    big="🟢 BUY CALL UP ⬆️" if direction=="call" else "🔴 SELL PUT DOWN ⬇️"
    msg=f"🔥 SIGNAL {pair}\n{big}\n⏰ {EXPIRY} MIN\n{reason}\n⚡️ TRADE NOW ⚡️"
    def delayed(): time.sleep(8); send_channel(msg)
    threading.Thread(target=delayed, daemon=True).start()

iq_connect(force=True)

@app.route('/')
def home():
    return f"V17.5.2 BAL {Iq.get_balance() if Iq else '?'} NEXT {get_countdown()[0]}"
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try: bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('UTF-8'))])
    except: pass
    return "OK",200

@bot.message_handler(commands=['start','resume','balance','debug'])
def handle_all(m):
    global OWNER_ID, NEXT_SCAN_AT, SCANNING
    OWNER_ID=m.chat.id; SCANNING=True
    if '/start' in m.text or '/resume' in m.text: NEXT_SCAN_AT=time.time()+20
    load_state(); iq_connect(force=True); time.sleep(1)
    bal=Iq.get_balance() if Iq else "?"; cd,_=get_countdown()
    bot.send_message(m.chat.id, f"🤖 V17.5.2 RECONNECT FIX ✅\nBal ${bal}\n10 OTC rotating 4/scan\nNext ${current_amount} Lvl {martingale_level}\n⏳ Next {cd}")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING; SCANNING=False; send_private("⏸️ Paused")
@bot.message_handler(commands=['scan'])
def scan(m):
    global OWNER_ID; OWNER_ID=m.chat.id; do_trade()

def do_trade():
    global NEXT_SCAN_AT, current_amount, martingale_level, ALERT_SENT
    if not iq_connect():
        send_private("❌ IQ still disconnected - retry 60s")
        NEXT_SCAN_AT=time.time()+60; return
    if not OWNER_ID: return
    PAIRS=get_pairs()
    send_private(f"🔍 Scanning {', '.join(PAIRS)}")
    tried=[]
    for pair in PAIRS:
        direction, reason=analyze(pair); tried.append(reason)
        if direction:
            try:
                # Ensure still connected before buy
                if not iq_connect(): continue
                status, tid = Iq.buy(current_amount, pair, direction, EXPIRY)
                if not status:
                    err=str(tid)[:100]
                    if "suspended" in err.lower(): continue
                    send_private(f"⚠️ {pair} IQ: {err}"); continue
                send_private(f"✅ PLACED {pair} {direction.upper()} ${current_amount} Lvl {martingale_level}\n{reason}")
                send_channel_big_signal(pair,direction,reason)
                send_private("⏳ 65s...")
                time.sleep(65)
                profit=Iq.check_win_v3(tid); bal=Iq.get_balance() if Iq else "?"; NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False; cd,_=get_countdown()
                if profit and profit>0:
                    send_private(f"💰 WIN +${round(profit,2)} ✅ Bal ${bal} Next {cd}"); send_channel(f"💰 WIN {pair}")
                    martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]; save_state()
                else:
                    send_private(f"📉 LOSS -${current_amount} ❌ Bal ${bal} Next {cd}"); send_channel(f"📉 LOSS {pair}")
                    martingale_level+=1
                    if martingale_level>=MAX_MARTINGALE: martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]
                    else: current_amount=MARTINGALE_AMOUNTS[martingale_level]
                    save_state()
                return
            except Exception as e:
                send_private(f"Buy err {pair} {e}"); iq_connect(force=True); continue
    NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False; cd,_=get_countdown(); bal=Iq.get_balance() if Iq else "?"
    details="\n".join(tried[:4])
    send_private(f"⏭️ No signal\n{details}\nBal ${bal} Next ${current_amount} in {cd}")

def scanner():
    while True:
        try:
            time.sleep(1)
            if not OWNER_ID or not SCANNING: continue
            if time.time()<NEXT_SCAN_AT: continue
            do_trade()
        except Exception as e: print(f"scanner err {e}", flush=True); time.sleep(3)

def countdown_notifier():
    global ALERT_SENT
    while True:
        try:
            time.sleep(1)
            if not OWNER_ID or not SCANNING: continue
            _,rem=get_countdown()
            if rem<=5 and rem>0 and not ALERT_SENT:
                send_private(f"‼️ 5 sec to signal ‼️ Next ${current_amount}"); ALERT_SENT=True
        except: time.sleep(1)

def iq_keepalive():
    # Ping IQ every 60 sec so it doesn't disconnect = fix for your log
    while True:
        try:
            time.sleep(60)
            if Iq:
                try: Iq.get_balance()
                except: iq_connect(force=True)
        except: time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=countdown_notifier, daemon=True).start()
threading.Thread(target=iq_keepalive, daemon=True).start()

if __name__=="__main__":
    try:
        bot.remove_webhook(); time.sleep(1)
        ext=os.getenv("RENDER_EXTERNAL_URL")
        if ext: bot.set_webhook(url=f"{ext}/{TOKEN}")
    except: pass
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
