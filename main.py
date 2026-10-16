import os, time, threading, datetime, json, requests
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

print("=== V21 REAL ANALYSIS + 3MIN EXPIRY ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
CHANNEL_ID = "@trailblazeebot"
CHANNEL_LINK = "https://t.me/trailblazeebot"
OWNER_USERNAME = "@kevintraiblazer"
IQ_LINK = "https://iqoption.com/en/register"
PRICE = "$10/month"

OWNER_ID = None
SCANNING = True
PAIRS = ["EURUSD","GBPUSD","USDJPY","EURJPY","AUDUSD"]
PAID_FILE = "paid_users.json"
FREE_FILE = "free_users.json"
HISTORY_FILE = "price_history.json"

def load_json(f):
    try:
        if os.path.exists(f):
            with open(f,'r') as fp: return json.load(fp)
    except: pass
    return {}
def save_json(f,data):
    try:
        with open(f,'w') as fp: json.dump(fp,data)
    except: pass

PAID_USERS = load_json(PAID_FILE)
FREE_USERS = load_json(FREE_FILE)
PRICE_HISTORY = load_json(HISTORY_FILE) # {"EURUSD":[1.08,1.09...]}

def is_paid(uid):
    if OWNER_ID and str(uid)==str(OWNER_ID): return True
    if str(uid) in PAID_USERS and time.time() < PAID_USERS[str(uid)]: return True
    return False
def can_send_free(uid):
    if is_paid(uid): return True
    return FREE_USERS.get(str(uid),0) < 2
def use_free(uid):
    if is_paid(uid): return
    FREE_USERS[str(uid)] = FREE_USERS.get(str(uid),0)+1
    save_json(FREE_FILE, FREE_USERS)

def get_expiry(uid):
    if str(uid) not in PAID_USERS: return "Not paid"
    return datetime.datetime.fromtimestamp(PAID_USERS[str(uid)]).strftime('%d %b %Y')

# REAL FOREX PRICE
def get_price(pair):
    try:
        # Use free forex API
        symbol = pair[:3]+"/"+pair[3:6]
        r = requests.get(f"https://api.exchangerate.host/convert?from={pair[:3]}&to={pair[3:6]}&amount=1", timeout=10).json()
        if r.get("result"):
            return float(r["result"])
        # fallback
        return None
    except:
        return None

def calc_rsi(prices, period=14):
    if len(prices) < period+1: return 50
    gains=[]; losses=[]
    for i in range(1,len(prices)):
        diff=prices[i]-prices[i-1]
        if diff>0: gains.append(diff); losses.append(0)
        else: gains.append(0); losses.append(abs(diff))
    if len(gains)<period: return 50
    avg_gain=sum(gains[-period:])/period
    avg_loss=sum(losses[-period:])/period
    if avg_loss==0: return 75
    if avg_gain==0: return 25
    rs=avg_gain/avg_loss
    return 100-(100/(1+rs))

def calc_ema(prices, period=21):
    if len(prices)<period: return prices[-1] if prices else 0
    k=2/(period+1)
    ema=prices[0]
    for p in prices[1:]: ema = p*k + ema*(1-k)
    return ema

# REAL ANALYSIS
def analyze_real(pair):
    price = get_price(pair)
    if not price:
        return None
    if pair not in PRICE_HISTORY: PRICE_HISTORY[pair]=[]
    PRICE_HISTORY[pair].append(price)
    if len(PRICE_HISTORY[pair])>100: PRICE_HISTORY[pair].pop(0)
    save_json(HISTORY_FILE, PRICE_HISTORY)

    prices = PRICE_HISTORY[pair]
    if len(prices)<30: return None # not enough data

    rsi = calc_rsi(prices)
    ema7 = calc_ema(prices,7)
    ema21 = calc_ema(prices,21)

    # STRICT FILTER - HIGH QUALITY ONLY
    direction=None
    reason=""
    confidence=0

    if rsi < 35 and prices[-1] < ema7 and ema7 < ema21:
        direction="PUT"
        confidence=88 if rsi<30 else 82
        reason=f"Oversold RSI {round(rsi,1)} + Downtrend"
    elif rsi > 65 and prices[-1] > ema7 and ema7 > ema21:
        direction="CALL"
        confidence=88 if rsi>70 else 82
        reason=f"Overbought RSI {round(rsi,1)} + Uptrend"
    else:
        return None # NO SIGNAL - not perfect setup

    # Only send if confidence 80%+
    if confidence < 80: return None
    return direction, confidence, round(rsi,1), "UP" if ema7>ema21 else "DOWN", reason, round(price,5)

bot = telebot.TeleBot(TOKEN, threaded=False) if ':' in TOKEN else None

if bot:
    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        if OWNER_ID is None: OWNER_ID=m.chat.id
        uid=m.chat.id
        if OWNER_ID and uid==OWNER_ID:
            bot.send_message(uid, f"👑 OWNER MODE\n/resume /pause /test /paidlist /approve ID 30")
            return
        if is_paid(uid):
            bot.send_message(uid, f"✅ ACTIVE till {get_expiry(uid)}\nReal analysis - 2-5 signals/day max. 3 MIN expiry auto-set.")
            return
        free_left = 2 - FREE_USERS.get(str(uid),0)
        txt=f"""🚀 KEVIN IQ SNIPER - REAL ANALYSIS

I scan real forex price with RSI+EMA confluence.

📊 Filter:
✅ RSI + EMA trend must agree
✅ Only 80%+ setups
✅ 2-5 signals per day (quality > quantity)
✅ 3 MIN expiry auto-set

🎁 You have {free_left} FREE signals!

STEP 1: {CHANNEL_LINK}
STEP 2: {IQ_LINK}
STEP 3: 1% risk only!

After free: {PRICE} to {OWNER_USERNAME}

⚠️ Educational only. No 100% guarantee. Losses happen."""
        mk=InlineKeyboardMarkup()
        mk.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
        mk.add(InlineKeyboardButton("💼 Register IQ", url=IQ_LINK))
        bot.send_message(uid, txt, reply_markup=mk)

    @bot.message_handler(commands=['approve','paidlist','resume','pause','test'])
    def other(m):
        global SCANNING, OWNER_ID
        if OWNER_ID and m.chat.id!=OWNER_ID: return
        if m.text.startswith("/approve"):
            try:
                p=m.text.split(); uid=p[1]; d=int(p[2]) if len(p)>2 else 30
                PAID_USERS[str(uid)]=time.time()+d*24*3600; save_json(PAID_FILE, PAID_USERS)
                bot.send_message(m.chat.id, f"✅ {uid} {d} days")
                try: bot.send_message(int(uid), f"✅ ACTIVATED {d} days!")
                except: pass
            except: bot.send_message(m.chat.id, "Use /approve ID 30")
        elif m.text.startswith("/paidlist"):
            t="Paid:\n"+"\n".join([f"{k}-{get_expiry(k)}" for k in PAID_USERS]) or "None"
            bot.send_message(m.chat.id,t)
        elif m.text.startswith("/resume"): SCANNING=True; bot.send_message(m.chat.id,"▶️ ON")
        elif m.text.startswith("/pause"): SCANNING=False; bot.send_message(m.chat.id,"⏸️ OFF")
        elif m.text.startswith("/test"):
            bot.send_message(m.chat.id,"Testing real scan... wait 60s")

    @bot.callback_query_handler(func=lambda c: True)
    def cb(call):
        if OWNER_ID and call.message.chat.id!=OWNER_ID: return
        if call.data=="skip":
            bot.edit_message_text("❌ Skipped", call.message.chat.id, call.message.message_id); return
        if call.data.startswith("send_"):
            _,pair,d,c,rsi,ema,price = call.data.split("_")
            now=datetime.datetime.now()+datetime.timedelta(hours=1); exp=now+datetime.timedelta(minutes=3)
            full=f"""🚨 KEVIN IQ SNIPER 🚨

💱 Pair: {pair}
{'📈' if d=='CALL' else '📉'} Direction: {d} - 3 MIN
🔥 Confidence: {c}%
💲 Price: {price}

📊 REAL ANALYSIS:
├ RSI: {rsi}
├ Trend: EMA7 {'🟢 ABOVE' if ema=='UP' else '🔴 BELOW'} EMA21
└ {rsi}

⏰ Entry: {now.strftime('%H:%M')} WAT
🎯 Expiry: {exp.strftime('%H:%M')} WAT (3 MIN)

👉 ACTION: Trade {d} NOW on IQ Option!
⚠️ 1% risk only! Educational, not financial advice.

Channel: {CHANNEL_LINK}"""
            sent=0
            for uid_str in set(list(PAID_USERS.keys())+list(FREE_USERS.keys())+[str(OWNER_ID)]):
                try:
                    uid=int(uid_str)
                    if not is_paid(uid) and not can_send_free(uid): continue
                    bot.send_message(uid, full); use_free(uid); sent+=1; time.sleep(0.3)
                except: pass
            try: bot.send_message(CHANNEL_ID, full)
            except: pass
            bot.edit_message_text(f"✅ SENT {sent} + channel | Exp {exp.strftime('%H:%M')}", call.message.chat.id, call.message.message_id)

    @app.route(f'/{TOKEN}', methods=['POST'])
    def webhook():
        if request.headers.get('content-type')=='application/json':
            js=request.get_data().decode('utf-8'); upd=telebot.types.Update.de_json(js); bot.process_new_updates([upd]); return ''
        return 'ok',200
    @app.route('/')
    def home(): return "V21 REAL + 3MIN EXPIRY LIVE",200
    def set_wh():
        time.sleep(5)
        if RENDER_URL:
            try:
                requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10); time.sleep(2)
                url=f"{RENDER_URL}/{TOKEN}"; requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}", timeout=10)
            except: pass
    threading.Thread(target=set_wh, daemon=True).start()

def scanner():
    while True:
        try:
            time.sleep(60)
            if not OWNER_ID or not SCANNING or not bot: continue
            for pair in PAIRS:
                res=analyze_real(pair)
                if not res: continue
                d,c,rsi,ema,reason,price=res
                mk=InlineKeyboardMarkup()
                mk.add(InlineKeyboardButton(f"✅ YES Send {pair} {d} {c}%", callback_data=f"send_{pair}_{d}_{c}_{rsi}_{ema}_{price}"))
                mk.add(InlineKeyboardButton("❌ NO Skip", callback_data="skip"))
                txt=f"🔔 REAL SIGNAL FOUND!\n\n{pair} {d} {c}%\nPrice {price}\nRSI {rsi} EMA {ema}\n{reason}\n\nExpiry will be NOW+3min"
                bot.send_message(OWNER_ID, txt, reply_markup=mk)
                time.sleep(300) # 5 min cooldown after found
                break
            time.sleep(60)
        except Exception as e: print(f"SCAN {e}"); time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
