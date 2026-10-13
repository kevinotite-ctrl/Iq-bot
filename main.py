import os, time, threading, random, datetime, json
from flask import Flask, request
import telebot
print("=== V17.5.1 LOUD + FAST SIGNALS ===", flush=True)
app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")
CHANNEL_ID = -1003709183793
BASE_AMOUNT = 10
MARTINGALE_AMOUNTS = [10, 20, 40]
MAX_MARTINGALE = 3
STATE_FILE = "bot_state.json"
EXPIRY = 1
SCAN_INTERVAL = 90 # 1m30s - faster
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL") or "https://your-service-name.onrender.com"

def load_state():
    global current_amount, martingale_level
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                martingale_level = data.get('level', 0)
                current_amount = MARTINGALE_AMOUNTS[martingale_level] if martingale_level < len(MARTINGALE_AMOUNTS) else MARTINGALE_AMOUNTS[0]
    except: pass
def save_state():
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({'level': martingale_level, 'amount': current_amount}, f)
    except: pass

current_amount=BASE_AMOUNT; martingale_level=0; load_state()
OWNER_ID=None; Iq=None; SCANNING=True; NEXT_SCAN_AT=time.time()+30; ALERT_SENT=False

ALL_OTC_PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "GBPJPY-OTC", "EURGBP-OTC", "AUDCAD-OTC", "USDCHF-OTC", "EURAUD-OTC", "AUDUSD-OTC", "USDJPY-OTC"]

def get_pairs(): return random.sample(ALL_OTC_PAIRS, 4)

def get_countdown():
    r = int(NEXT_SCAN_AT - time.time())
    if r<0: r=0
    return f"{r//60:02d}:{r%60:02d}", r

bot = telebot.TeleBot(TOKEN)
def send_private(t):
    try:
        if OWNER_ID: bot.send_message(OWNER_ID, t)
    except: pass
def send_channel(t):
    try: bot.send_message(CHANNEL_ID, t)
    except: pass

def send_channel_big_signal(pair, direction, reason):
    big = "🟢 BUY CALL UP ⬆️⬆️⬆️" if direction=="call" else "🔴 SELL PUT DOWN ⬇️⬇️⬇️"
    msg = f"🔥 SIGNAL {pair}\n{big}\n⏰ {EXPIRY} MIN\n{reason}\n⚡️ TRADE NOW ⚡️"
    def delayed():
        time.sleep(8)
        send_channel(msg)
    threading.Thread(target=delayed, daemon=True).start()

def get_rsi(candles, p=14):
    try:
        c=[x['close'] for x in candles]; g=[]; l=[]
        for i in range(1,len(c)):
            d=c[i]-c[i-1]; g.append(max(d,0)); l.append(max(-d,0))
        if len(g)<p: return 50
        ag=sum(g[-p:])/p; al=sum(l[-p:])/p
        if al==0: return 50
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
        ok,_=Iq.connect()
        if ok:
            Iq.change_balance("PRACTICE")
            return True
    except Exception as e: print(f"IQ fail {e}", flush=True)
    return False

def get_safe_balance():
    global Iq
    try:
        if not Iq: iq_connect()
        return round(Iq.get_balance(),2)
    except:
        try: iq_connect(); time.sleep(1); return round(Iq.get_balance(),2)
        except: return "?"

def analyze(pair):
    try:
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles)<25: return None, f"{pair} No candles"
        ema7=get_ema(candles[-15:],7); ema21=get_ema(candles,21); rsi=get_rsi(candles,14); close=candles[-1]['close']
        # LOOSER LOGIC - 70% more signals
        # Old: close>ema7>ema21 (strict)
        # New: close>ema7 and ema7>ema21 OR just close>ema21 with RSI 30-70
        if close > ema21 and rsi>30 and rsi<70 and close>ema7:
            return "call", f"UP Close {round(close,5)} > EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        elif close < ema21 and rsi>30 and rsi<70 and close<ema7:
            return "put", f"DOWN Close {round(close,5)} < EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        else:
            # DEBUG INFO
            return None, f"{pair} SKIP C:{round(close,5)} EMA7:{round(ema7,5)} EMA21:{round(ema21,5)} RSI:{round(rsi,1)}"
    except Exception as e: return None, f"{pair} Err {e}"

iq_connect()

@app.route('/')
def home():
    cd,_=get_countdown(); return f"V17.5.1 BAL {get_safe_balance()} NEXT {cd}"
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('UTF-8'))])
    except: pass
    return "OK",200

@bot.message_handler(commands=['start','resume','balance','debug'])
def handle_all(m):
    global OWNER_ID, NEXT_SCAN_AT, SCANNING
    OWNER_ID=m.chat.id; SCANNING=True
    if '/start' in m.text or '/resume' in m.text:
        NEXT_SCAN_AT=time.time()+20 # Start fast in 20 sec
    load_state(); iq_connect(); time.sleep(1)
    bal=get_safe_balance(); cd,_=get_countdown()
    bot.send_message(m.chat.id, f"🤖 V17.5.1 1 MIN FAST ✅\nBal ${bal}\n10 OTC rotating 4/scan\nNext ${current_amount} Lvl {martingale_level}\n⏳ Next in {cd}\n\n/resume to restart\n/debug to see live analysis")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING; SCANNING=False; send_private("⏸️ Paused")

@bot.message_handler(commands=['scan'])
def scan(m):
    global OWNER_ID; OWNER_ID=m.chat.id; do_trade()

def do_trade():
    global NEXT_SCAN_AT, current_amount, martingale_level, ALERT_SENT
    if not Iq and not iq_connect():
        send_private("❌ IQ disconnected - retry in 60s")
        NEXT_SCAN_AT=time.time()+60; return
    if not OWNER_ID: return
    PAIRS=get_pairs()
    send_private(f"🔍 Scanning {', '.join(PAIRS)}...") # LOUD - tell you it's working
    tried=[]
    for pair in PAIRS:
        direction, reason = analyze(pair)
        tried.append(reason)
        if direction:
            try:
                status, trade_id = Iq.buy(current_amount, pair, direction, EXPIRY)
                if not status:
                    err=str(trade_id)[:100]
                    send_private(f"⚠️ {pair} {direction.upper()} IQ says: {err}\nTrying next pair...")
                    continue
                # SUCCESS
                send_private(f"✅ PLACED {pair} {direction.upper()} ${current_amount} Lvl {martingale_level}\n{reason}")
                send_channel_big_signal(pair, direction, reason)
                send_private("⏳ 65s to result...")
                time.sleep(65)
                profit=Iq.check_win_v3(trade_id); bal=get_safe_balance()
                NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False
                cd,_=get_countdown()
                if profit and profit>0:
                    send_private(f"💰 WIN +${round(profit,2)} ✅ Bal ${bal} Next {cd}"); send_channel(f"💰 WIN +${round(profit,2)} {pair}")
                    martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]; save_state()
                else:
                    send_private(f"📉 LOSS -${current_amount} ❌ Bal ${bal} Next {cd}"); send_channel(f"📉 LOSS {pair}")
                    martingale_level+=1
                    if martingale_level>=MAX_MARTINGALE: martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]
                    else: current_amount=MARTINGALE_AMOUNTS[martingale_level]
                    send_private(f"📈 Next ${current_amount} Lvl {martingale_level}"); save_state()
                return
            except Exception as e:
                send_private(f"Err {pair} {e}"); continue

    # No trade this scan - SHOW WHY (not quiet)
    NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False; cd,_=get_countdown(); bal=get_safe_balance()
    details = "\n".join(tried[:4])
    send_private(f"⏭️ No signal this round\n{details}\nBal ${bal} Next ${current_amount} | Next in {cd}")

def scanner():
    while True:
        try:
            time.sleep(1)
            if not OWNER_ID or not SCANNING: continue
            if time.time()<NEXT_SCAN_AT: continue
            do_trade()
        except: time.sleep(3)

def countdown_notifier():
    global ALERT_SENT
    while True:
        try:
            time.sleep(1)
            if not OWNER_ID or not SCANNING: continue
            _,rem=get_countdown()
            if rem<=5 and rem>0 and not ALERT_SENT:
                send_private(f"‼️ Signal in 5 sec ‼️ Get Ready Next ${current_amount} Lvl {martingale_level}")
                ALERT_SENT=True
        except: time.sleep(1)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=countdown_notifier, daemon=True).start()

if __name__=="__main__":
    try:
        bot.remove_webhook(); time.sleep(1)
        ext=os.getenv("RENDER_EXTERNAL_URL")
        if ext: bot.set_webhook(url=f"{ext}/{TOKEN}")
    except: pass
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
