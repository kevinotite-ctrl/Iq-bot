import os, time, threading, datetime, json, requests, random
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

print("=== V22 REAL + FIXED TEST + 3MIN EXPIRY ===", flush=True)
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
PRICE_HISTORY = load_json(HISTORY_FILE)

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
    if FREE_USERS[str(uid)] >= 2:
        try: bot.send_message(uid, f"🔒 FREE TRIAL OVER!\nPay {PRICE} to {OWNER_USERNAME} for unlimited 🚀")
        except: pass

def get_expiry(uid):
    if str(uid) not in PAID_USERS: return "Not paid"
    return datetime.datetime.fromtimestamp(PAID_USERS[str(uid)]).strftime('%d %b %Y')

def get_price(pair):
    try:
        r = requests.get(f"https://api.exchangerate.host/convert?from={pair[:3]}&to={pair[3:6]}&amount=1", timeout=8).json()
        if r.get("result"):
            return float(r["result"])
    except: pass
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

def analyze_real(pair):
    price = get_price(pair)
    if not price: return None
    if pair not in PRICE_HISTORY: PRICE_HISTORY[pair]=[]
    PRICE_HISTORY[pair].append(price)
    if len(PRICE_HISTORY[pair])>100: PRICE_HISTORY[pair].pop(0)
    save_json(HISTORY_FILE, PRICE_HISTORY)

    prices = PRICE_HISTORY[pair]
    if len(prices)<30: return None

    rsi = calc_rsi(prices)
    ema7 = calc_ema(prices,7)
    ema21 = calc_ema(prices,21)

    direction=None; confidence=0; reason=""
    if rsi < 35 and prices[-1] < ema7 and ema7 < ema21:
        direction="PUT"; confidence=88 if rsi<30 else 82
        reason=f"Oversold RSI {round(rsi,1)} + Downtrend"
    elif rsi > 65 and prices[-1] > ema7 and ema7 > ema21:
        direction="CALL"; confidence=88 if rsi>70 else 82
        reason=f"Overbought RSI {round(rsi,1)} + Uptrend"
    else:
        return None
    if confidence < 80: return None
    return direction, confidence, round(rsi,1), "UP" if ema7>ema21 else "DOWN", reason, round(price,5)

bot = telebot.TeleBot(TOKEN, threaded=False) if ':' in TOKEN else None

if bot:
    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        if OWNER_ID is None:
            OWNER_ID=m.chat.id
            print(f"Owner set {OWNER_ID}", flush=True)
        uid=m.chat.id
        if OWNER_ID and uid==OWNER_ID:
            bot.send_message(uid, f"👑 OWNER MODE\n/resume - ON\n/pause - OFF\n/test - TEST with YES/NO + Expiry\n/paidlist - list paid\n/approve ID 30 - approve user\n\nChannel: {CHANNEL_LINK}")
            return
        if is_paid(uid):
            bot.send_message(uid, f"✅ ACTIVE till {get_expiry(uid)}\nReal RSI+EMA analysis - 2-5 signals/day. 3 MIN expiry auto.\nChannel: {CHANNEL_LINK}")
            return
        free_left = 2 - FREE_USERS.get(str(uid),0)
        txt=f"""🚀 KEVIN IQ SNIPER - REAL ANALYSIS 💹

I scan real forex price 24/7 - ONLY when RSI + EMA agree!

📊 Filter:
✅ RSI + EMA confluence
✅ Only 80%+ setups
✅ 2-5 quality signals/day
✅ Entry + Expiry (3 MIN) auto

🎁 You have {free_left} FREE signals!

👉 STEP 1: Join Channel: {CHANNEL_LINK}
💼 STEP 2: Register IQ: {IQ_LINK}
⚠️ STEP 3: 1% risk only!

After {free_left} free: Pay {PRICE} to {OWNER_USERNAME}

Educational only - no 100% guarantee."""
        mk=InlineKeyboardMarkup()
        mk.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
        mk.add(InlineKeyboardButton("💼 Register IQ Option", url=IQ_LINK))
        mk.add(InlineKeyboardButton(f"💬 Contact {OWNER_USERNAME}", url=f"https://t.me/kevintraiblazer"))
        bot.send_message(uid, txt, reply_markup=mk)

    @bot.message_handler(commands=['approve','paidlist','resume','pause','test'])
    def other(m):
        global SCANNING, OWNER_ID
        if OWNER_ID and m.chat.id!=OWNER_ID:
            bot.send_message(m.chat.id,"Owner only"); return

        if m.text.startswith("/approve"):
            try:
                p=m.text.split(); uid=p[1]; d=int(p[2]) if len(p)>2 else 30
                PAID_USERS[str(uid)]=time.time()+d*24*3600; save_json(PAID_FILE, PAID_USERS)
                bot.send_message(m.chat.id, f"✅ Approved {uid} for {d} days till {get_expiry(uid)}")
                try: bot.send_message(int(uid), f"✅ ACTIVATED {d} days! Unlimited signals 🚀")
                except: pass
            except: bot.send_message(m.chat.id, "Use: /approve USER_ID 30")

        elif m.text.startswith("/paidlist"):
            if not PAID_USERS: bot.send_message(m.chat.id,"No paid yet"); return
            t="💰 Paid users:\n"
            for k,v in PAID_USERS.items(): t+=f"{k} - {get_expiry(k)}\n"
            bot.send_message(m.chat.id,t)

        elif m.text.startswith("/resume"):
            SCANNING=True; bot.send_message(m.chat.id,"▶️ Scanning ON - Will ask YES/NO before sending")

        elif m.text.startswith("/pause"):
            SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused")

        elif m.text.startswith("/test"):
            pair = random.choice(PAIRS)
            d = random.choice(["CALL","PUT"])
            c = 85
            rsi = 72.5 if d=="CALL" else 28.3
            ema = "UP" if d=="CALL" else "DOWN"
            price = round(random.uniform(1.05,1.35),5)
            reason = "TEST MODE - Buttons + 3MIN Expiry Check"

            mk=InlineKeyboardMarkup()
            mk.add(InlineKeyboardButton(f"✅ YES Send {pair} {d} {c}%", callback_data=f"send_{pair}_{d}_{c}_{rsi}_{ema}_{price}"))
            mk.add(InlineKeyboardButton("❌ NO Skip", callback_data="skip"))

            txt=f"🔔 TEST SIGNAL FOUND!\n\n💱 {pair}\nDirection: {d}\nConf: {c}%\nPrice: {price}\nRSI: {rsi} EMA: {ema}\n{reason}\n\nTap YES to test full send with Entry + Expiry (NOW + 3 MIN)"
            bot.send_message(m.chat.id, txt, reply_markup=mk)

    @bot.callback_query_handler(func=lambda c: True)
    def cb(call):
        if OWNER_ID and call.message.chat.id!=OWNER_ID: return
        if call.data=="skip":
            bot.edit_message_text("❌ Skipped - No one got it", call.message.chat.id, call.message.message_id); return
        if call.data.startswith("send_"):
            try:
                _,pair,d,c,rsi,ema,price = call.data.split("_")
                now=datetime.datetime.now()+datetime.timedelta(hours=1)
                exp=now+datetime.timedelta(minutes=3)
                full=f"""🚨🚨 KEVIN IQ SNIPER 🚨🚨

💱 Pair: {pair}
{'📈' if d=='CALL' else '📉'} Direction: {d} - 3 MIN {'🔺' if d=='CALL' else '🔻'}
🔥 Confidence: {c}% 💎
💲 Price: {price}

📊 ANALYSIS:
├ RSI: {rsi}
├ Trend: EMA7 {'🟢 ABOVE' if ema=='UP' else '🔴 BELOW'} EMA21
└ Momentum: {d} setup 💪

⏰ Entry: {now.strftime('%H:%M')} WAT
🎯 Expiry: {exp.strftime('%H:%M')} WAT (3 MIN)

👉 ACTION: Trade {d} NOW! (3 min)
⚠️ Risk: 1% only! Educational.

#IQOption Paid {PRICE} {OWNER_USERNAME}"""
                sent=0
                all_ids = set(list(PAID_USERS.keys()) + list(FREE_USERS.keys()) + [str(OWNER_ID)])
                for uid_str in all_ids:
                    try:
                        uid=int(uid_str)
                        if not is_paid(uid) and not can_send_free(uid): continue
                        bot.send_message(uid, "‼️ signal alert incoming ‼️💰"); time.sleep(0.2)
                        bot.send_message(uid, full); use_free(uid); sent+=1; time.sleep(0.3)
                    except: pass
                try: bot.send_message(CHANNEL_ID, full)
                except Exception as e: print(f"Channel send fail {e}")
                bot.edit_message_text(f"✅ SENT to {sent} users + channel {CHANNEL_ID}\nEntry {now.strftime('%H:%M')} Exp {exp.strftime('%H:%M')} (3 MIN)", call.message.chat.id, call.message.message_id)
            except Exception as e:
                bot.send_message(call.message.chat.id, f"Error {e}")

    @app.route(f'/{TOKEN}', methods=['POST'])
    def webhook():
        if request.headers.get('content-type')=='application/json':
            js=request.get_data().decode('utf-8'); upd=telebot.types.Update.de_json(js); bot.process_new_updates([upd]); return ''
        return 'ok',200
    @app.route('/')
    def home(): return "V22 REAL + FIXED TEST LIVE",200

    def set_wh():
        time.sleep(5)
        if RENDER_URL:
            try:
                requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10); time.sleep(2)
                url=f"{RENDER_URL}/{TOKEN}"; r=requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}", timeout=10); print(r.text, flush=True)
            except Exception as e: print(e, flush=True)
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
                txt=f"🔔 REAL SIGNAL FOUND!\n\n💱 {pair} {d} {c}%\n💲 Price {price}\n📊 RSI {rsi} EMA {ema}\n{reason}\n\nSend? Expiry will be NOW+3 MIN"
                bot.send_message(OWNER_ID, txt, reply_markup=mk)
                time.sleep(300)
                break
        except Exception as e: print(f"SCAN ERR {e}", flush=True); time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
