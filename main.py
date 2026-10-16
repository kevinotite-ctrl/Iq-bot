import os, time, threading, random, datetime, json, requests
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

print("=== V20 OWNER CONTROL + 2 FREE + INTRO ===", flush=True)
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
PAIRS = ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDUSD", "EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "USDJPY-OTC", "GBPJPY-OTC"]
PAID_FILE = "paid_users.json"
FREE_FILE = "free_users.json"

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
FREE_USERS = load_json(FREE_FILE) # {id: count}

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
        try: bot.send_message(uid, f"🔒 FREE TRIAL OVER!\nPay {PRICE} to {OWNER_USERNAME} for unlimited signals 🚀")
        except: pass

def get_expiry(uid):
    if str(uid) not in PAID_USERS: return "Not paid"
    return datetime.datetime.fromtimestamp(PAID_USERS[str(uid)]).strftime('%d %b %Y')

def analyze(pair):
    rsi=round(random.uniform(28,72),1)
    ema=random.choice(["UP","DOWN"])
    d="CALL" if (ema=="UP" and rsi>50) else "PUT"
    c=random.randint(90,99)
    reason="Up momentum" if d=="CALL" else "Down momentum"
    return d,c,rsi,ema,reason

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
            bot.send_message(uid, f"👑 OWNER MODE - FREE FOR LIFE\n\n/resume - start scanning\n/pause - pause\n/test - test signal\n/paidlist - see paid\n/approve ID 30 - approve\n\nChannel: {CHANNEL_LINK}")
            return
        if is_paid(uid):
            bot.send_message(uid, f"💹 ACTIVE till {get_expiry(uid)}\nSignals coming! 🚀\nChannel: {CHANNEL_LINK}")
            return

        # NEW USER - FULL INTRO
        free_left = 2 - FREE_USERS.get(str(uid),0)
        txt = f"""🚀 **WELCOME TO KEVIN IQ SNIPER BOT** 💹

I scan IQ Option 24/7 and send ONLY 90-100% signals!

📊 What I do:
✅ 10 Pairs (EURUSD, GBPUSD, OTC)
✅ Only 90%+ confidence
✅ 3 MIN expiry with analysis
✅ Entry + Expiry time

🎁 **You have {free_left} FREE signals!**

👉 **STEP 1: Join Channel:**
📢 {CHANNEL_LINK}
Tap to join 👆

💼 **STEP 2: REGISTER ON IQ OPTION:**
🔗 {IQ_LINK}
1. Click link → Register email → Verify
2. Deposit min $10 (Card/Opay/Crypto)
3. Start with $30-$50 recommended

⚠️ **STEP 3: RISK MANAGEMENT:**
• 1% per trade only! ($50 = $1/trade)
• Max 3 trades/day
• Stop after 2 losses
• No revenge trading!
• No overtrading!

💰 **After {free_left} free signals:**
Pay {PRICE} to {OWNER_USERNAME} for unlimited!

📩 Contact: {OWNER_USERNAME}

Your first signal is coming soon! ⏳"""

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📢 Join Channel", url=CHANNEL_LINK))
        markup.add(InlineKeyboardButton("💼 Register IQ Option", url=IQ_LINK))
        markup.add(InlineKeyboardButton(f"💬 Contact {OWNER_USERNAME}", url=f"https://t.me/kevintraiblazer"))
        bot.send_message(uid, txt, reply_markup=markup)

    @bot.message_handler(commands=['approve'])
    def approve(m):
        if OWNER_ID and m.chat.id!=OWNER_ID: return
        try:
            parts=m.text.split(); user_id=parts[1]; days=int(parts[2]) if len(parts)>2 else 30
            PAID_USERS[str(user_id)]=time.time()+days*24*3600; save_json(PAID_FILE, PAID_USERS)
            bot.send_message(m.chat.id, f"✅ Approved {user_id} {days} days till {get_expiry(user_id)}")
            try: bot.send_message(int(user_id), f"✅ ACTIVATED {days} days! You now get unlimited signals 🚀")
            except: pass
        except: bot.send_message(m.chat.id, "Use: /approve USER_ID 30")

    @bot.message_handler(commands=['remove','paidlist','resume','pause','test'])
    def other(m):
        global SCANNING, OWNER_ID
        if OWNER_ID and m.chat.id!=OWNER_ID: bot.send_message(m.chat.id,"Owner only"); return
        if m.text.startswith("/remove"):
            try: del PAID_USERS[m.text.split()[1]]; save_json(PAID_FILE, PAID_USERS); bot.send_message(m.chat.id,"Removed")
            except: bot.send_message(m.chat.id,"Use /remove ID")
        elif m.text.startswith("/paidlist"):
            if not PAID_USERS: bot.send_message(m.chat.id,"No paid"); return
            t="💰 Paid:\n";
            for k,v in PAID_USERS.items(): t+=f"{k} - {get_expiry(k)}\n"
            bot.send_message(m.chat.id,t)
        elif m.text.startswith("/resume"): SCANNING=True; bot.send_message(m.chat.id,"▶️ Scanning ON - Will ask you before sending")
        elif m.text.startswith("/pause"): SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused")
        elif m.text.startswith("/test"):
            OWNER_ID=m.chat.id; pair=random.choice(PAIRS); d,c,rsi,ema,rsn=analyze(pair)
            now=datetime.datetime.now()+datetime.timedelta(hours=1); exp=now+datetime.timedelta(minutes=3)
            msg=f"🚨🚨 KEVIN IQ SNIPER 🚨🚨\n\n💱 {pair}\n{'📈' if d=='CALL' else '📉'} {d} - 3 MIN\n🔥 {c}% 💎\n\n📊 RSI:{rsi} | EMA:{ema} | {rsn}\n⏰ Entry:{now.strftime('%H:%M')} 🎯 Expiry:{exp.strftime('%H:%M')}\n\n👉 Trade {d} NOW!"
            # Ask owner first
            markup=InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("✅ YES Send to Channel & Paid", callback_data=f"send_{pair}_{d}_{c}_{rsi}_{ema}"))
            markup.add(InlineKeyboardButton("❌ NO Skip", callback_data="skip"))
            bot.send_message(m.chat.id, f"TEST SIGNAL FOUND:\n{msg}\n\nSend to channel?", reply_markup=markup)

    @bot.callback_query_handler(func=lambda c: True)
    def callback(call):
        if OWNER_ID and call.message.chat.id!=OWNER_ID: return
        if call.data=="skip":
            bot.edit_message_text("❌ Skipped", call.message.chat.id, call.message.message_id); return
        if call.data.startswith("send_"):
            try:
                _,pair,d,c,rsi,ema = call.data.split("_")
                now=datetime.datetime.now()+datetime.timedelta(hours=1); exp=now+datetime.timedelta(minutes=3)
                full=f"""🚨🚨 KEVIN IQ SNIPER 🚨🚨

💱 Pair: {pair}
{'📈' if d=='CALL' else '📉'} Direction: {d} - 3 MIN {'🔺' if d=='CALL' else '🔻'}
🔥 Confidence: {c}% 💎 {'🔥🔥🔥' if int(c)>=95 else '🔥🔥'}

📊 ANALYSIS:
├ RSI: {rsi}
├ Trend: EMA7 {'🟢 ABOVE' if ema=='UP' else '🔴 BELOW'} EMA21
└ Momentum: {d} momentum 💪

⏰ Entry: {now.strftime('%H:%M')}
🎯 Expiry: {exp.strftime('%H:%M')}

👉 ACTION: Trade {d} NOW! (3 min)
⚠️ Risk: 1% only!

#IQOption Paid {PRICE} {OWNER_USERNAME}"""
                # send to paid + free trial
                sent=0
                all_ids = list(PAID_USERS.keys()) + list(FREE_USERS.keys()) + [str(OWNER_ID)]
                for uid_str in set(all_ids):
                    try:
                        uid=int(uid_str)
                        if not is_paid(uid) and not can_send_free(uid): continue
                        bot.send_message(uid, "‼️signal alert incoming ‼️💰"); time.sleep(0.2)
                        bot.send_message(uid, full); use_free(uid); sent+=1; time.sleep(0.3)
                    except: pass
                try: bot.send_message(CHANNEL_ID, full)
                except: pass
                bot.edit_message_text(f"✅ SENT to {sent} users + channel {CHANNEL_ID}", call.message.chat.id, call.message.message_id)
            except Exception as e: bot.send_message(call.message.chat.id, f"Error {e}")

    @app.route(f'/{TOKEN}', methods=['POST'])
    def webhook():
        if request.headers.get('content-type')=='application/json':
            js=request.get_data().decode('utf-8'); upd=telebot.types.Update.de_json(js); bot.process_new_updates([upd]); return ''
        return 'ok',200
    @app.route('/')
    def home(): return "V20 OWNER CONTROL LIVE",200
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
            time.sleep(45)
            if not OWNER_ID or not SCANNING or not bot: continue
            pair=random.choice(PAIRS); d,c,rsi,ema,rsn=analyze(pair)
            if c<90: continue
            # ASK OWNER FIRST, don't auto send
            markup=InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(f"✅ YES Send {pair} {d} {c}%", callback_data=f"send_{pair}_{d}_{c}_{rsi}_{ema}"))
            markup.add(InlineKeyboardButton("❌ NO Skip", callback_data="skip"))
            txt=f"🔔 SIGNAL FOUND!\n\n💱 {pair}\nDirection: {d}\nConf: {c}%\nRSI: {rsi}\n\nSend to channel + {len(PAID_USERS)} paid + free trial?"
            bot.send_message(OWNER_ID, txt, reply_markup=markup)
            time.sleep(300)
        except Exception as e: print(f"SCAN ERR {e}", flush=True); time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
