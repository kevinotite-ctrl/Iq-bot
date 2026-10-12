import os, time, threading, random, datetime, json
from flask import Flask, request
import telebot
print("=== V17.9 4 PAIRS 70-100% FAST ===", flush=True)
app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")
CHANNEL_ID = -1003709183793
BASE_AMOUNT = 10000
MARTINGALE_AMOUNTS = [10000, 15000, 20000]
MAX_MARTINGALE = 3
STATE_FILE = "bot_state.json"
EXPIRY = 2
SCAN_INTERVAL = 90 # FASTER NOW 90s instead of 120s

def get_min_conf():
    return 70 # 70% to 100%

def load_state():
    global current_amount, martingale_level
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                martingale_level = data.get('level', 0)
                current_amount = MARTINGALE_AMOUNTS[martingale_level] if martingale_level < len(MARTINGALE_AMOUNTS) else MARTINGALE_AMOUNTS[0]
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
NEXT_SCAN_AT = time.time() + 60
ALERT_SENT = False

# 4 PAIRS NOW FOR FASTER SIGNALS!
WEEKEND_PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURJPY-OTC"]
WEEKDAY_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "EURJPY"]

def get_pairs(): return WEEKEND_PAIRS if datetime.datetime.now().weekday()>=5 else WEEKDAY_PAIRS

def get_countdown():
    rem = int(NEXT_SCAN_AT - time.time())
    if rem < 0: rem = 0
    return f"{rem//60:02d}:{rem%60:02d}", rem

bot = telebot.TeleBot(TOKEN)

def send_private(text):
    try:
        if OWNER_ID: bot.send_message(OWNER_ID, text)
    except: pass

def send_channel(text):
    try: bot.send_message(CHANNEL_ID, text)
    except: pass

def send_channel_big_signal(pair, direction, conf, reason):
    big_dir = "🟢🟢🟢 CALL / BUY 🟢🟢🟢\n⬆️ GO UP ⬆️" if direction=="call" else "🔴🔴🔴 PUT / SELL 🔴🔴🔴\n⬇️ GO DOWN ⬇️"
    def delayed():
        time.sleep(10)
        send_channel(f"🔥 NEW SIGNAL 🔥\n💰 {pair}\n{big_dir}\n⏰ {EXPIRY} MIN\n🎯 {conf}% [70-100%]\n{reason}\n⚡️ TAKE NOW ⚡️")
    threading.Thread(target=delayed, daemon=True).start()

def get_rsi(candles, period=14):
    try:
        closes=[c['close'] for c in candles]; gains=[]; losses=[]
        for i in range(1,len(closes)):
            d=closes[i]-closes[i-1]; gains.append(max(d,0)); losses.append(max(-d,0))
        if len(gains)<period: return 50
        ag=sum(gains[-period:])/period; al=sum(losses[-period:])/period
        if al==0: return 80
        return 100-(100/(1+ag/al))
    except: return 50

def get_ema(candles, period):
    try:
        closes=[c['close'] for c in candles]; ema=closes[0]; k=2/(period+1)
        for p in closes[1:]: ema=p*k+ema*(1-k)
        return ema
    except: return 0

def calculate_confidence_2min(candles, ema7, ema21, rsi, direction):
    try:
        confidence=70
        closes=[c['close'] for c in candles]
        gap=abs(ema7-ema21)/ema21*1000
        if gap>0.8: confidence+=18
        elif gap>0.4: confidence+=12
        elif gap>0.2: confidence+=6
        if direction=="call":
            if 55<=rsi<=70: confidence+=18
            else: confidence+=8
        else:
            if 30<=rsi<=45: confidence+=18
            else: confidence+=8
        return min(100, max(70, int(confidence)))
    except: return 75

def iq_connect():
    global Iq
    try:
        from iqoptionapi.stable_api import IQ_Option
        Iq=IQ_Option(EMAIL,PASS); chk,_=Iq.connect()
        if chk: Iq.change_balance("PRACTICE"); return True
    except Exception as e:
        print(f"IQ fail {e}", flush=True)
    return False

def analyze(pair):
    try:
        candles=Iq.get_candles(pair,60,50,time.time())
        if not candles or len(candles)<25: return None,f"No candles {pair}",0,0
        ema7=get_ema(candles[-15:],7); ema21=get_ema(candles,21); rsi=get_rsi(candles,14); close=candles[-1]['close']
        if close>ema7>ema21 and 50<rsi<75:
            conf=calculate_confidence_2min(candles,ema7,ema21,rsi,"call")
            return "call", f"UP EMA7 {round(ema7,5)} > EMA21 RSI {round(rsi,1)}", conf, rsi
        elif close<ema7<ema21 and 25<rsi<50:
            conf=calculate_confidence_2min(candles,ema7,ema21,rsi,"put")
            return "put", f"DOWN EMA7 {round(ema7,5)} < EMA21 RSI {round(rsi,1)}", conf, rsi
        else: return None,f"RSI {round(rsi,1)} flat",0,rsi
    except Exception as e: return None,f"Error {e}",0,0

iq_connect()

@app.route('/')
def home():
    cd,_=get_countdown(); return f"V17.9 4PAIRS 70-100% BAL {Iq.get_balance() if Iq else 'NO IQ'} NEXT {cd}"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str=request.get_data().decode('UTF-8')
        update=telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except: pass
    return "OK",200

@app.route('/setwebhook')
def set_webhook():
    try:
        bot.remove_webhook(); time.sleep(1)
        url=f"{os.getenv('RENDER_EXTERNAL_URL')}/{TOKEN}"
        bot.set_webhook(url=url); return f"Webhook set {url}"
    except Exception as e: return f"Error {e}"

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, NEXT_SCAN_AT, ALERT_SENT
    OWNER_ID=m.chat.id; NEXT_SCAN_AT=time.time()+60; ALERT_SENT=False
    load_state()
    if not Iq: iq_connect()
    try: bal=round(Iq.get_balance(),2)
    except: bal="?"
    cd,_=get_countdown()
    bot.send_message(m.chat.id, f"🤖 V17.9 4 PAIRS FAST ✅\n70% - 100%\nPairs: {', '.join(get_pairs())}\nBal ${bal}\nNext ${current_amount} Lvl {martingale_level}\n⏳ Auto every 90s\nNext in {cd}")

@bot.message_handler(commands=['balance'])
def balance_cmd(m):
    global OWNER_ID; OWNER_ID=m.chat.id
    try: bal=round(Iq.get_balance(),2); bot.send_message(m.chat.id, f"💰 Bal ${bal} Next ${current_amount} Lvl {martingale_level} 4 PAIRS 70-100%")
    except: bot.send_message(m.chat.id, "❌ IQ not connected")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, SCANNING, NEXT_SCAN_AT, ALERT_SENT
    OWNER_ID=m.chat.id; SCANNING=True; NEXT_SCAN_AT=time.time()+60; ALERT_SENT=False; bot.send_message(m.chat.id, "▶️ RESUMED 4 PAIRS")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING; SCANNING=False; send_private("⏸️ Paused")

@bot.message_handler(commands=['scan'])
def scan(m):
    global OWNER_ID; OWNER_ID=m.chat.id; do_trade(is_manual=True)

def do_trade(is_manual=False):
    global NEXT_SCAN_AT, ALERT_SENT, current_amount, martingale_level
    if not Iq and not iq_connect():
        send_private("❌ IQ login failed"); NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False; return
    if not OWNER_ID: return
    PAIRS=get_pairs(); random.shuffle(PAIRS); min_c=get_min_conf(); last_reason=""
    for pair in PAIRS:
        direction, reason, conf, rsi = analyze(pair)
        last_reason = f"{pair}: {reason}"
        if direction and conf>=min_c:
            try:
                send_private(f"Bot confidence >> {conf}% 💯 [70-100% FAST]\n💯 {pair} {direction.upper()} {conf}% | ${current_amount} Lvl {martingale_level} Exp {EXPIRY}min\n{reason}")
                send_channel_big_signal(pair, direction, conf, reason)
                status, trade_id = Iq.buy(current_amount, pair, direction, EXPIRY)
                if not status:
                    send_private(f"❌ Buy failed {pair}"); continue
                send_private(f"✅ BOUGHT {pair} {direction.upper()} ${current_amount} {conf}%")
                time.sleep(125)
                profit=Iq.check_win_v3(trade_id); bal=Iq.get_balance(); NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False
                if profit and profit>0:
                    send_private(f"💰 WIN +${round(profit,2)} {conf}% CORRECT Bal ${round(bal,2)}"); send_channel(f"💰 WIN +${round(profit,2)} {conf}%")
                    martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]; save_state()
                else:
                    send_private(f"📉 LOSS -${current_amount} Bal ${round(bal,2)}"); send_channel(f"📉 LOSS -${current_amount}")
                    martingale_level+=1
                    if martingale_level>=MAX_MARTINGALE: martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]
                    else: current_amount=MARTINGALE_AMOUNTS[martingale_level]
                    save_state()
                return
            except Exception as e:
                send_private(f"Trade err {e}"); continue
    NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False
    cd,_=get_countdown()
    if is_manual:
        send_private(f"⏭️ No 70%+ in 4 pairs\nLast: {last_reason}\nNeed 70-100% | Retry {cd}")
    else:
        send_private(f"⏭️ Scanned 4 pairs: {', '.join(PAIRS)}\nLast: {last_reason}\nNo 70% setup, retry {cd}")

def scanner():
    while True:
        try:
            time.sleep(2)
            if not OWNER_ID or not SCANNING: continue
            if time.time() < NEXT_SCAN_AT: continue
            do_trade(is_manual=False)
        except: time.sleep(5)

def countdown_notifier():
    global ALERT_SENT
    while True:
        try:
            time.sleep(1)
            if not OWNER_ID or not SCANNING: continue
            _, rem = get_countdown()
            if rem <= 5 and rem > 0 and not ALERT_SENT:
                send_private(f"‼️ Signal incoming ‼️\n5 secs - 4 pairs scanning\nNext ${current_amount} Min 70%")
                ALERT_SENT=True
        except: time.sleep(2)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=countdown_notifier, daemon=True).start()

if __name__=="__main__":
    try:
        bot.remove_webhook(); time.sleep(1)
        ext_url=os.getenv("RENDER_EXTERNAL_URL")
        if ext_url: bot.set_webhook(url=f"{ext_url}/{TOKEN}")
    except: pass
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
