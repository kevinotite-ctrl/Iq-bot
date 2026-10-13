import os, time, threading, random, datetime, json
from flask import Flask, request
import telebot
print("=== V17.5.0 REAL SIGNALS - NO SUSPENDED SPAM ===", flush=True)
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
SCAN_INTERVAL = 180 # 3 mins - stop IQ from suspending you
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL") or "https://your-service-name.onrender.com"

def load_state():
    global current_amount, martingale_level
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                martingale_level = data.get('level', 0)
                if martingale_level < len(MARTINGALE_AMOUNTS):
                    current_amount = MARTINGALE_AMOUNTS[martingale_level]
                else:
                    martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]
    except: pass

def save_state():
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({'level': martingale_level, 'amount': current_amount, 'time': time.time()}, f)
    except: pass

current_amount=BASE_AMOUNT; martingale_level=0; load_state()
OWNER_ID=None; Iq=None; SCANNING=True; LAST_SIGNAL=0; NEXT_SCAN_AT=time.time()+60; ALERT_SENT=False

# 8 PAIRS - IQ won't suspend all at once
ALL_OTC_PAIRS = [
    "EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "GBPJPY-OTC",
    "EURGBP-OTC", "AUDCAD-OTC", "USDCHF-OTC", "EURAUD-OTC"
]

def get_pairs():
    # Return 3 random from 8 to avoid suspension
    return random.sample(ALL_OTC_PAIRS, 3)

def get_countdown():
    remaining = int(NEXT_SCAN_AT - time.time())
    if remaining < 0: remaining = 0
    m=remaining//60; s=remaining%60
    return f"{m:02d}:{s:02d}", remaining

bot = telebot.TeleBot(TOKEN)

def send_private(text):
    try:
        if OWNER_ID: bot.send_message(OWNER_ID, text)
    except: pass

def send_channel(text):
    try: bot.send_message(CHANNEL_ID, text)
    except: pass

def send_channel_big_signal(pair, direction, reason):
    big = "🟢🟢 BUY / CALL UP ⬆️" if direction=="call" else "🔴🔴 SELL / PUT DOWN ⬇️"
    channel_msg = f"""
🔥 NEW SIGNAL 🚀
💰 PAIR: {pair}
{big}
⏰ EXPIRY: {EXPIRY} MINUTE
💵 At your own risk
{reason}
⚡️ TAKE TRADE NOW ⚡️
"""
    def delayed():
        time.sleep(10)
        send_channel(channel_msg)
    threading.Thread(target=delayed, daemon=True).start()

def get_rsi(candles, period=14):
    try:
        closes=[c['close'] for c in candles]; gains=[]; losses=[]
        for i in range(1,len(closes)):
            d=closes[i]-closes[i-1]
            gains.append(max(d,0)); losses.append(max(-d,0))
        if len(gains)<period: return 50
        ag=sum(gains[-period:])/period; al=sum(losses[-period:])/period
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
        check, _ = Iq.connect()
        if check:
            # TRY REAL FIRST - PRACTICE OTC gets suspended fast
            # If REAL has no money, it will auto stay on PRACTICE
            try:
                Iq.change_balance("REAL")
                bal = Iq.get_balance()
                if bal < 5: # No real money
                    Iq.change_balance("PRACTICE")
            except:
                Iq.change_balance("PRACTICE")
            return True
    except: pass
    return False

def get_safe_balance():
    global Iq
    try:
        if not Iq: iq_connect()
        return round(Iq.get_balance(),2)
    except:
        try:
            iq_connect(); time.sleep(1)
            return round(Iq.get_balance(),2)
        except: return "RECONNECTING"

def is_asset_open(pair):
    # Check if IQ says asset is open
    try:
        all_open = Iq.get_all_open_time()
        if 'binary' in all_open and pair in all_open['binary']:
            return all_open['binary'][pair]['open']
        return True # Assume open if not in list
    except: return True

def analyze(pair):
    try:
        if not is_asset_open(pair):
            return None, "SUSPENDED"
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles)<25: return None, "No candles"
        ema7=get_ema(candles[-15:],7); ema21=get_ema(candles,21); rsi=get_rsi(candles,14); close=candles[-1]['close']
        if close>ema7>ema21 and 30<rsi<70:
            return "call", f"UP EMA7 > EMA21 RSI {round(rsi,1)}"
        elif close<ema7<ema21 and 30<rsi<70:
            return "put", f"DOWN EMA7 < EMA21 RSI {round(rsi,1)}"
        else:
            return None, f"SKIP RSI {round(rsi,1)}"
    except: return None, "Err"

iq_connect()

@app.route('/')
def home():
    cd,_=get_countdown(); bal=get_safe_balance()
    return f"V17.5.0 LIVE BAL {bal} NEXT {cd}"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except: pass
    return "OK",200

@bot.message_handler(commands=['start','balance','resume'])
def handle_all(m):
    global OWNER_ID, LAST_SIGNAL, NEXT_SCAN_AT, SCANNING
    OWNER_ID=m.chat.id
    if m.text.startswith('/resume'): SCANNING=True; LAST_SIGNAL=0; NEXT_SCAN_AT=time.time()+60
    if m.text.startswith('/start'): LAST_SIGNAL=0; NEXT_SCAN_AT=time.time()+60
    load_state(); iq_connect(); time.sleep(1)
    bal=get_safe_balance(); cd,_=get_countdown()
    txt = f"🤖 V17.5.0 1 MIN ✅\nBal ${bal}\nPairs: 8 OTC rotating (3 per scan)\nNext ${current_amount} Lvl {martingale_level}\n⏳ Next in {cd}\n\nIf OTC suspended, bot auto-skips and waits."
    bot.send_message(m.chat.id, txt)

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING; SCANNING=False; send_private("⏸️ Paused")

@bot.message_handler(commands=['scan'])
def scan(m):
    global OWNER_ID; OWNER_ID=m.chat.id; do_trade()

def do_trade():
    global LAST_SIGNAL, current_amount, martingale_level, NEXT_SCAN_AT, ALERT_SENT
    if not Iq and not iq_connect():
        LAST_SIGNAL=time.time(); NEXT_SCAN_AT=time.time()+300; return
    if not OWNER_ID: return
    PAIRS=get_pairs()
    success=False
    suspended_count=0
    for pair in PAIRS:
        direction, reason = analyze(pair)
        if reason=="SUSPENDED": suspended_count+=1; continue
        if direction:
            try:
                status, trade_id = Iq.buy(current_amount, pair, direction, EXPIRY)
                if not status:
                    err=str(trade_id)
                    if "suspended" in err.lower():
                        suspended_count+=1
                        continue # Skip this pair, try next - don't spam
                    send_private(f"⚠️ {pair} {direction.upper()} IQ rejected: {err[:60]}")
                    continue

                # SUCCESS - TRADE PLACED FIRST
                success=True
                private_msg = f"✅ TRADE PLACED {pair} {direction.upper()} | 1 MIN\n${current_amount} Lvl {martingale_level}\n{reason}"
                send_private(private_msg)
                send_channel_big_signal(pair, direction, reason)

                send_private(f"⏳ Wait 65s...")
                time.sleep(65)
                profit=Iq.check_win_v3(trade_id); bal=get_safe_balance()
                LAST_SIGNAL=time.time(); NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False
                cd,_=get_countdown()
                if profit and profit>0:
                    result=f"💰 WIN +${round(profit,2)} ✅\nBal ${bal}\nReset to $10\n⏳ Next {cd}"
                    send_private(result); send_channel(result)
                    martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]; save_state()
                else:
                    result=f"📉 LOSS -${current_amount} ❌\nBal ${bal}\n⏳ Next {cd}"
                    send_private(result); send_channel(result)
                    martingale_level+=1
                    if martingale_level>=MAX_MARTINGALE:
                        martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]
                        send_private(f"🔄 Reset to ${current_amount}")
                    else:
                        current_amount=MARTINGALE_AMOUNTS[martingale_level]
                        send_private(f"📈 Next ${current_amount} Lvl {martingale_level}")
                    save_state()
                threading.Thread(target=lambda: (time.sleep(3), send_channel("We go again ‼️💯")), daemon=True).start()
                return
            except Exception as e:
                continue

    # AFTER LOOP
    LAST_SIGNAL=time.time()
    if suspended_count>=2:
        # IQ suspended most OTC - wait 5 mins longer
        NEXT_SCAN_AT=time.time()+300
        cd,_=get_countdown()
        bal=get_safe_balance()
        send_private(f"⏸️ IQ suspended {suspended_count} pairs | Cooling 5 mins | Bal ${bal} | Next {cd}")
    else:
        NEXT_SCAN_AT=time.time()+SCAN_INTERVAL
        ALERT_SENT=False
        # ONLY send "No signal" if truly no signal, not if suspended
        if suspended_count==0:
            bal=get_safe_balance(); cd,_=get_countdown()
            send_private(f"⏭️ No RSI 30-70 signal in {len(PAIRS)} pairs | Next ${current_amount} Lvl {martingale_level} | Bal ${bal} | Next {cd}")

def scanner():
    while True:
        try:
            time.sleep(2)
            if not OWNER_ID or not SCANNING: continue
            if time.time()<NEXT_SCAN_AT: continue
            do_trade()
        except: time.sleep(5)

def countdown_notifier():
    global ALERT_SENT
    while True:
        try:
            time.sleep(1)
            if not OWNER_ID or not SCANNING: continue
            cd,rem=get_countdown()
            if rem<=5 and rem>0 and not ALERT_SENT:
                send_private(f"‼️Signal incoming in 5 secs - Get Ready‼️ Next ${current_amount}")
                ALERT_SENT=True
        except: time.sleep(2)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=countdown_notifier, daemon=True).start()

if __name__=="__main__":
    try:
        bot.remove_webhook(); time.sleep(1)
        ext=os.getenv("RENDER_EXTERNAL_URL")
        if ext: bot.set_webhook(url=f"{ext}/{TOKEN}")
    except: pass
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
