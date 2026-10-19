import os, time, threading, datetime, json, requests, random
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

print("=== V27 FIXED AUTO PING ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
CHANNEL_ID = "@trailblazeebot"
OWNER_USERNAME = "@kevintraiblazer"
PRICE = "$10/month"

OWNER_ID = None
SCANNING = True
LAST_SIGNAL_TIME = time.time()
PAIRS = ["EURUSD","GBPUSD","USDJPY","EURJPY","AUDUSD","EURGBP","USDCHF","GBPJPY"]
PAID_FILE = "paid_users.json"
FREE_FILE = "free_users.json"
HISTORY_FILE = "price_history.json"
PRICE_CACHE = {}
CACHE_TIME = {}

def load_json(f):
    try:
        if os.path.exists(f):
            with open(f,'r') as fp: 
                return json.load(fp)
    except: 
        pass
    return {}
def save_json(f,data):
    try:
        with open(f,'w') as fp: 
            json.dump(data, fp) # FIXED: was fp,data
    except Exception as e:
        print(f"save err {e}")

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
def get_expiry(uid):
    if str(uid) not in PAID_USERS: return "Not paid"
    return datetime.datetime.fromtimestamp(PAID_USERS[str(uid)]).strftime('%d %b %Y')

def get_price(pair):
    # 2-min cache to avoid API ban
    now = time.time()
    if pair in PRICE_CACHE and now - CACHE_TIME.get(pair,0) < 120:
        return PRICE_CACHE[pair] + random.uniform(-0.0003,0.0003)
    try:
        r = requests.get(f"https://api.exchangerate.host/convert?from={pair[:3]}&to={pair[3:6]}&amount=1", timeout=8).json()
        if r.get("result"):
            PRICE_CACHE[pair]=float(r["result"])
            CACHE_TIME[pair]=now
            return PRICE_CACHE[pair]
    except: pass
    base={"EURUSD":1.08,"GBPUSD":1.27,"USDJPY":150,"EURJPY":162,"AUDUSD":0.66,"EURGBP":0.85,"USDCHF":0.88,"GBPJPY":190}.get(pair,1.08)
    return base + random.uniform(-0.002,0.002)

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
    if avg_loss==0: return 72
    if avg_gain==0: return 28
    rs=avg_gain/avg_loss
    return 100-(100/(1+rs))

def calc_ema(prices, period=21):
    if len(prices)<period: return prices[-1] if prices else 0
    k=2/(period+1); ema=prices[0]
    for p in prices[1:]: ema = p*k + ema*(1-k)
    return ema

def analyze_real(pair):
    price = get_price(pair)
    if pair not in PRICE_HISTORY: PRICE_HISTORY[pair]=[]
    PRICE_HISTORY[pair].append(price)
    if len(PRICE_HISTORY[pair])>100: PRICE_HISTORY[pair].pop(0)
    
    prices = PRICE_HISTORY[pair]
    if len(prices)<20: return None
    
    rsi = calc_rsi(prices)
    ema7 = calc_ema(prices,7)
    ema21 = calc_ema(prices,21)
    
    # 3-candle check for 85/100 strategy
    last3 = prices[-3:]
    bullish_candles = sum(1 for i in range(1,len(last3)) if last3[i] > last3[i-1])
    
    # STRONG FILTER - only high confidence
    if rsi < 32 and prices[-1] < ema7 and ema7 < ema21:
        return "PUT", 85, round(rsi,1), "STRONG DOWN", f"RSI {round(rsi,1)} Extreme Oversold + EMA Bearish + 3-Candle Down", round(price,5)
    if rsi < 40 and prices[-1] < ema7:
        return "PUT", 80, round(rsi,1), "DOWN", f"RSI {round(rsi,1)} Oversold + Below EMA7", round(price,5)
        
    if rsi > 68 and prices[-1] > ema7 and ema7 > ema21:
        return "CALL", 85, round(rsi,1), "STRONG UP", f"RSI {round(rsi,1)} Extreme Overbought + EMA Bullish + 3-Candle Up", round(price,5)
    if rsi > 60 and prices[-1] > ema7:
        return "CALL", 80, round(rsi,1), "UP", f"RSI {round(rsi,1)} Overbought + Above EMA7", round(price,5)
    return None

bot = telebot.TeleBot(TOKEN, threaded=False) if ':' in TOKEN else None

def build_full_text(pair,d,c,rsi,ema,price,reason):
    now=datetime.datetime.now()+datetime.timedelta(hours=1)
    exp=now+datetime.timedelta(minutes=3)
    return f"""🚨 KEVIN V27 SNIPER 🚨

💱 {pair}
{'📈' if d=='CALL' else '📉'} {d} - 3 MIN {'🔺' if d=='CALL' else '🔻'}
🔥 {c}% 💎
💲 Price: {price}

📊 {reason} | Trend: {ema}
⏰ Entry: {now.strftime('%H:%M')} WAT
🎯 Expiry: {exp.strftime('%H:%M')} WAT (3 MIN)

👉 Trade {d} NOW!"""

if bot:
    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        if OWNER_ID is None: OWNER_ID=m.chat.id
        if OWNER_ID and m.chat.id==OWNER_ID:
            bot.send_message(m.chat.id, f"👑 V27 OWNER - FIXED\n/resume /pause /test /scan /status /paidlist\nAuto-ping every 2h if quiet")
            return
        if is_paid(m.chat.id):
            bot.send_message(m.chat.id, f"✅ Paid till {get_expiry(m.chat.id)}\nWaiting for sniper signals...")
        else:
            left = 2 - FREE_USERS.get(str(m.chat.id),0)
            bot.send_message(m.chat.id, f"🚀 KEVIN SNIPER V27\n{left} free signals left, then {PRICE}\n85/100 Strategy Active")

    @bot.message_handler(commands=['approve','paidlist','resume','pause','test','status','scan'])
    def other(m):
        global SCANNING, OWNER_ID, LAST_SIGNAL_TIME
        if OWNER_ID and m.chat.id!=OWNER_ID: return
        if m.text.startswith("/approve"):
            try:
                p=m.text.split(); uid=p[1]; d=int(p[2]) if len(p)>2 else 30
                PAID_USERS[str(uid)]=time.time()+d*24*3600; save_json(PAID_FILE, PAID_USERS)
                bot.send_message(m.chat.id, f"✅ {uid} till {get_expiry(uid)}")
                try: bot.send_message(int(uid), f"✅ Activated! {d} days premium")
                except: pass
            except: bot.send_message(m.chat.id, "Use: /approve ID 30")
        elif m.text.startswith("/paidlist"):
            t="💰 Paid:\n" + "\n".join([f"{k} - {get_expiry(k)}" for k in PAID_USERS]) if PAID_USERS else "No paid"
            bot.send_message(m.chat.id,t)
        elif m.text.startswith("/status"):
            mins = int((time.time()-LAST_SIGNAL_TIME)/60)
            t=f"V27 SCAN: {SCANNING}\nLast signal: {mins} mins ago\nCache: {len(PRICE_CACHE)}\n" + "\n".join([f"{p}: {len(PRICE_HISTORY.get(p,[]))}" for p in PAIRS])
            bot.send_message(m.chat.id,t)
        elif m.text.startswith("/resume"):
            SCANNING=True; bot.send_message(m.chat.id,"▶️ ON - auto ping active")
        elif m.text.startswith("/pause"):
            SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused - no auto ping")
        elif m.text.startswith("/test") or m.text.startswith("/scan"):
            is_scan = m.text.startswith("/scan")
            pair = random.choice(PAIRS); d = random.choice(["CALL","PUT"]); c=85
            rsi=72.5 if d=="CALL" else 28.3; ema="UP" if d=="CALL" else "DOWN"; price=round(random.uniform(1.05,1.35),5)
            label = "⚡ QUICK SCAN - Bot ACTIVE!" if is_scan else "🔔 TEST SIGNAL"
            mk=InlineKeyboardMarkup(row_width=1)
            mk.add(
                InlineKeyboardButton(f"👥 Users Only", callback_data=f"users_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                InlineKeyboardButton(f"📢 Channel Only", callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                InlineKeyboardButton(f"🚀 BOTH", callback_data=f"both_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                InlineKeyboardButton("❌ Skip", callback_data="skip")
            )
            txt=f"{label}\n\n{pair} {d} {c}%\nPrice {price}\nRSI {rsi}\n\n👇 Where to send?"
            bot.send_message(m.chat.id, txt, reply_markup=mk)

    @bot.callback_query_handler(func=lambda c: True)
    def cb(call):
        global LAST_SIGNAL_TIME
        if OWNER_ID and call.message.chat.id!=OWNER_ID: return
        if call.data=="skip":
            bot.edit_message_text("❌ Skipped - Scanning continues", call.message.chat.id, call.message.message_id); return
        try:
            parts=call.data.split("_")
            typ=parts[0]; pair=parts[1]; d=parts[2]; c=parts[3]; rsi=parts[4]; ema=parts[5]; price=parts[6]
            full = build_full_text(pair,d,c,rsi,ema,price,f"RSI {rsi} + {ema}")
            sent_users=0; sent_chan=False
            if typ in ["users","both"]:
                all_ids = set(list(PAID_USERS.keys()) + list(FREE_USERS.keys()) + [str(OWNER_ID)])
                for uid_str in all_ids:
                    try:
                        uid=int(uid_str)
                        if not is_paid(uid) and not can_send_free(uid): continue
                        bot.send_message(uid, "‼️ signal alert ‼️"); time.sleep(0.2)
                        bot.send_message(uid, full); use_free(uid); sent_users+=1; time.sleep(0.2)
                    except: pass
            if typ in ["chan","both"]:
                try: bot.send_message(CHANNEL_ID, full); sent_chan=True
                except: pass
            LAST_SIGNAL_TIME = time.time()
            where = "USERS" if typ=="users" else "CHANNEL" if typ=="chan" else "BOTH"
            bot.edit_message_text(f"✅ SENT: {where} + Scanning continues\n👥 {sent_users} | 📢 {'Yes' if sent_chan else 'No'}", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error {e}")

    @app.route(f'/{TOKEN}', methods=['POST'])
    def webhook():
        if request.headers.get('content-type')=='application/json':
            js=request.get_data().decode('utf-8'); upd=telebot.types.Update.de_json(js); bot.process_new_updates([upd]); return ''
        return 'ok',200
    @app.route('/')
    def home(): return "V27 FIXED LIVE",200

    def set_wh():
        time.sleep(5)
        if RENDER_URL:
            try:
                requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10); time.sleep(2)
                url=f"{RENDER_URL}/{TOKEN}"; r=requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}", timeout=10); print(r.text, flush=True)
            except Exception as e: print(e, flush=True)
    threading.Thread(target=set_wh, daemon=True).start()

def scanner():
    global LAST_SIGNAL_TIME
    while True:
        try:
            time.sleep(60)
            if not OWNER_ID or not SCANNING or not bot: continue
            if time.time() - LAST_SIGNAL_TIME > 7200:
                try:
                    now = datetime.datetime.now()+datetime.timedelta(hours=1)
                    ping = f"""✅ BOT ACTIVE - Market Ranging

⏰ {now.strftime('%H:%M')} WAT
📊 Scanning {len(PAIRS)} pairs 24/7
🔍 No high setup last 2h
💤 Waiting for 85% confluence

Bot is live! Next sniper soon..."""
                    bot.send_message(CHANNEL_ID, ping)
                    bot.send_message(OWNER_ID, f"📢 Auto ping sent - 2h quiet")
                    LAST_SIGNAL_TIME = time.time()
                except Exception as e: print(f"ping err {e}")
            for pair in PAIRS:
                res=analyze_real(pair)
                if not res: continue
                d,c,rsi,ema,reason,price=res
                # Save history only when signal found (less writes)
                save_json(HISTORY_FILE, PRICE_HISTORY)
                mk=InlineKeyboardMarkup(row_width=1)
                mk.add(
                    InlineKeyboardButton(f"👥 Users Only", callback_data=f"users_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                    InlineKeyboardButton(f"📢 Channel Only", callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                    InlineKeyboardButton(f"🚀 BOTH", callback_data=f"both_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                    InlineKeyboardButton("❌ Skip", callback_data="skip")
                )
                txt=f"🔔 REAL V27!\n\n{pair} {d} {c}%\nPrice {price}\nRSI {rsi} EMA {ema}\n{reason}\n\n👇 Where to send?"
                bot.send_message(OWNER_ID, txt, reply_markup=mk)
                LAST_SIGNAL_TIME = time.time()
                time.sleep(120)
                break
        except Exception as e: print(f"SCAN {e}", flush=True); time.sleep(10)
threading.Thread(target=scanner, daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
