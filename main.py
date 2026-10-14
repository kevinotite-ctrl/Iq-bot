import os, time, threading, random, datetime, requests, logging, json
logging.getLogger().setLevel(logging.CRITICAL)
for l in ["", "root", "iqoptionapi", "iqoptionapi.stable_api"]:
    lg = logging.getLogger(l)
    try: lg.setLevel(logging.CRITICAL); lg.propagate=False
    except: pass
from flask import Flask
import telebot
print("=== KEVIN V24 WAKE ROUTE ===", flush=True)
app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

STATE_FILE = "kevin_memory.json"
BASE_AMOUNT=10; MAX_MARTINGALE=3
current_amount=10; martingale_level=0
OWNER_ID=None; Iq=None; SCANNING=True
LAST_SIGNAL=0; RESUME_AT=time.time()
IQ_LOCK=threading.RLock(); BOT_RUNNING=False
LAST_TRADE = {"pair": "None", "dir": "None", "amount": 0, "profit": 0, "time": "Never"}
WAKE_COUNT = 0

def save_memory():
    try:
        data = {
            "current_amount": current_amount,
            "martingale_level": martingale_level,
            "OWNER_ID": OWNER_ID,
            "LAST_SIGNAL": LAST_SIGNAL,
            "RESUME_AT": RESUME_AT,
            "SCANNING": SCANNING,
            "LAST_TRADE": LAST_TRADE,
            "saved_at": time.time()
        }
        with open(STATE_FILE, "w") as f: json.dump(data, f)
    except: pass

def load_memory():
    global current_amount, martingale_level, OWNER_ID, LAST_SIGNAL, RESUME_AT, SCANNING, LAST_TRADE
    try:
        if not os.path.exists(STATE_FILE): return
        with open(STATE_FILE, "r") as f: data = json.load(f)
        current_amount = data.get("current_amount", 10)
        martingale_level = data.get("martingale_level", 0)
        OWNER_ID = data.get("OWNER_ID")
        LAST_SIGNAL = data.get("LAST_SIGNAL", 0)
        RESUME_AT = data.get("RESUME_AT", time.time())
        SCANNING = data.get("SCANNING", True)
        LAST_TRADE = data.get("LAST_TRADE", LAST_TRADE)
    except: pass

def delete_webhook():
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
        b=telebot.TeleBot(TOKEN); b.remove_webhook()
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
            Iq=IQ_Option(EMAIL,PASS)
            ok,_=Iq.connect()
            if ok:
                time.sleep(5)
                try: Iq.change_balance("PRACTICE")
                except: pass
                return True
            return False
        except: return False
def get_open_pairs():
    try:
        with IQ_LOCK:
            if Iq is None: return ["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC"]
            all_open=Iq.get_all_open_time()
        if not all_open or not isinstance(all_open, dict): return ["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC"]
        open_dict=all_open.get('turbo', {}) or all_open.get('binary', {}) or {}
        if not open_dict: return ["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC"]
        return [k for k,v in open_dict.items() if (isinstance(v,dict) and v.get('open')) or v is True][:7] or ["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC"]
    except: return ["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC"]
def get_candles_safe(pair):
    global Iq
    for _ in range(3):
        try:
            with IQ_LOCK:
                if Iq is None: raise Exception("Iq None")
                c=Iq.get_candles(pair,60,50,time.time())
            if c and len(c)>=20: return c
        except: pass
        iq_connect_force(); time.sleep(2)
    return None
def analyze_loose(pair):
    candles=get_candles_safe(pair)
    if not candles: return None,"No candles"
    ema7=get_ema(candles[-15:],7); rsi=get_rsi(candles,14); close=candles[-1]['close']
    if close>ema7 and 40<rsi<85: return "call",f"UP 📈 RSI {round(rsi,1)}"
    elif close<ema7 and 15<rsi<60: return "put",f"DOWN 📉 RSI {round(rsi,1)}"
    else:
        if rsi>52: return "call",f"LOOSE UP 🚀 RSI {round(rsi,1)}"
        elif rsi<48: return "put",f"LOOSE DOWN 🧸 RSI {round(rsi,1)}"
        return None,f"SKIP 💤 RSI {round(rsi,1)}"

load_memory()
delete_webhook()
bot=telebot.TeleBot(TOKEN, threaded=False)

# === NEW ROUTES TO WAKE BOT FROM PHONE ===

@app.route('/')
def home():
    return f"✅ V24 AWAKE ✅<br>💵 Amt ${current_amount} Lvl {martingale_level}<br>📊 Last {LAST_TRADE}<br><br>🔗 <a href='/wake'>CLICK HERE TO WAKE BOT</a><br>🔗 <a href='/status'>STATUS PAGE</a><br>🔗 <a href='/ping'>PING (for UptimeRobot)</a>"

@app.route('/ping')
def ping():
    # For UptimeRobot - keeps bot awake
    return f"pong {datetime.datetime.now()} - Bot Alive Amt ${current_amount}"

@app.route('/status')
def status_page():
    try:
        with IQ_LOCK: bal = Iq.get_balance() if Iq else "No IQ"
    except: bal = "?"
    return f"""
    <html><body style='font-family:sans-serif; padding:20px'>
    <h2>🤖 KEVIN V24 STATUS 🧠</h2>
    <p>💵 Trade Amount: <b>${current_amount}</b> 🎯</p>
    <p>🪜 Martingale Level: <b>{martingale_level}</b></p>
    <p>💳 IQ Balance: <b>{bal}</b></p>
    <p>📊 Last Trade: <b>{LAST_TRADE}</b></p>
    <p>🤖 Scanning: <b>{'🟢 Active' if SCANNING else '🔴 Paused'}</b></p>
    <p>⏰ Woke: {WAKE_COUNT} times</p>
    <br>
    <a href='/wake' style='background:green;color:white;padding:15px;text-decoration:none;border-radius:10px'>🚀 WAKE BOT NOW</a>
    <br><br>
    <a href='/'>Home</a>
    </body></html>
    """

@app.route('/wake')
def wake():
    global WAKE_COUNT, BOT_RUNNING, SCANNING, RESUME_AT
    WAKE_COUNT += 1
    load_memory()
    RESUME_AT = time.time()
    SCANNING = True
    # Ensure polling is running
    if not BOT_RUNNING:
        threading.Thread(target=polling_loop, daemon=True).start()
        threading.Thread(target=scanner_loop, daemon=True).start()
        msg = "🔄 Bot was DEAD, restarting polling... ⏳"
    else:
        msg = "✅ Bot already awake, forcing scan... 🔍"
        threading.Thread(target=do_trade, daemon=True).start()

    # Notify owner on Telegram if possible
    try:
        if OWNER_ID:
            bot.send_message(OWNER_ID, f"📱 🌅 WAKE SIGNAL from browser! 🚀\n💵 Amt ${current_amount} Lvl {martingale_level}\n📊 Last {LAST_TRADE['pair']} → {LAST_TRADE['profit']}\n🔍 Scanning now... 👀")
    except: pass

    return f"""
    <html><body style='font-family:sans-serif; padding:20px; text-align:center'>
    <h1>🚀 BOT WOKEN UP! 🚀</h1>
    <h2>{msg}</h2>
    <p>💵 Amount: ${current_amount}</p>
    <p>🪜 Level: {martingale_level}</p>
    <p>📊 Last: {LAST_TRADE}</p>
    <p>⏰ Time: {datetime.datetime.now()}</p>
    <br>
    <p>✅ Now go to Telegram and send /balance</p>
    <p>🤖 Bot should reply in 5 seconds!</p>
    <br>
    <a href='/status' style='background:blue;color:white;padding:15px;text-decoration:none;border-radius:10px'>📊 VIEW STATUS</a>
    <br><br>
    <p style='color:gray'>Wake count: {WAKE_COUNT}</p>
    </body></html>
    """

@app.route(f'/{TOKEN}', methods=['POST'])
def wh(): delete_webhook(); return "DELETED",200

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT
    OWNER_ID=m.chat.id; RESUME_AT=time.time()
    load_memory()
    save_memory()
    bot.send_message(m.chat.id,f"✨ 🤖 KEVIN V24 ONLINE + WAKE ROUTE ✨\n\n💾 🧠 Memory: ${current_amount} Lvl {martingale_level}\n📊 Last: {LAST_TRADE['pair']} → {LAST_TRADE['profit']}\n\n🔗 Wake link: https://{os.getenv('RENDER_EXTERNAL_HOSTNAME','your-app.onrender.com')}/wake\n📱 Save this link! Open in phone browser to wake bot without Render login! 🚀\n\n🎮 /scan /testbuy /balance /memory /pause")
    if not iq_connect_force():
        bot.send_message(m.chat.id,"❌ IQ login failed!")
        return
    bot.send_message(m.chat.id,f"💰 Balance: ${Iq.get_balance()} 💎")

@bot.message_handler(commands=['memory','last'])
def memory_cmd(m):
    global OWNER_ID; OWNER_ID=m.chat.id; load_memory()
    bot.send_message(m.chat.id,f"🧠 💾 MEMORY 💾 🧠\n💵 ${current_amount} 🪜 {martingale_level}\n📊 {LAST_TRADE}\n🔗 Wake: /wake")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, RESUME_AT, SCANNING
    OWNER_ID=m.chat.id; SCANNING=True; RESUME_AT=time.time(); load_memory(); save_memory(); iq_connect_force()
    bot.send_message(m.chat.id,f"▶️ ✅ Resumed from MEMORY 🧠\n💵 ${current_amount} Lvl {martingale_level}\n📱 Wake link works! 🚀")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING; SCANNING=False; save_memory()
    bot.send_message(m.chat.id,f"⏸️ 🛌 Paused & Saved 💾\n💵 ${current_amount}\n📱 Wake with link: /wake")

@bot.message_handler(commands=['balance','status'])
def status_cmd(m):
    global OWNER_ID; OWNER_ID=m.chat.id
    try:
        with IQ_LOCK: bal=Iq.get_balance() if Iq else None
        if bal is None:
            iq_connect_force()
            with IQ_LOCK: bal=Iq.get_balance()
        bot.send_message(m.chat.id,f"💳 💰 WALLET 💰 💳\n💵 ${round(bal,2)} 💎\n💸 Amt ${current_amount} 🧠\n📈 Lvl {martingale_level}\n📊 Last {LAST_TRADE['pair']} → {LAST_TRADE['profit']}\n⏰ {LAST_TRADE['time']}\n\n🔗 Wake: https://{os.getenv('RENDER_EXTERNAL_HOSTNAME','-')}/wake")
    except:
        bot.send_message(m.chat.id,f"💳 Wallet 💾 ${current_amount} Lvl {martingale_level}")

@bot.message_handler(commands=['scan'])
def scan(m):
    global OWNER_ID; OWNER_ID=m.chat.id; save_memory()
    bot.send_message(m.chat.id,"🔍 👀 Scanning... 📡")
    threading.Thread(target=do_trade, daemon=True).start()
@bot.message_handler(commands=['testbuy'])
def testbuy(m):
    global OWNER_ID; OWNER_ID=m.chat.id
    bot.send_message(m.chat.id,"🧪 TEST BUY... 🚀")
    try:
        open_pairs=get_open_pairs(); test_pair=open_pairs[0]
        with IQ_LOCK:
            if Iq is None: iq_connect_force()
            status,tid=Iq.buy(10,test_pair,"call",1)
        if status:
            bot.send_message(m.chat.id,f"✅ BUY {test_pair} ID {tid} ⏳ 65s...")
            time.sleep(65)
            with IQ_LOCK: profit=Iq.check_win_v3(tid); bal=Iq.get_balance()
            bot.send_message(m.chat.id,f"{'🏆 WIN' if profit>0 else '📉 LOSS'} {profit} Bal ${round(bal,2)}")
        else: bot.send_message(m.chat.id,f"❌ Failed {test_pair}: {tid}")
    except Exception as e: bot.send_message(m.chat.id,f"❌ {e}")

def do_trade():
    global LAST_SIGNAL, current_amount, martingale_level, LAST_TRADE
    if not OWNER_ID: return
    if Iq is None: iq_connect_force()
    PAIRS=get_open_pairs(); random.shuffle(PAIRS)
    try: bot.send_message(OWNER_ID,f"🔍 Scanning {len(PAIRS)}... 💵 ${current_amount} 🧠")
    except: pass
    for pair in PAIRS:
        direction,reason=analyze_loose(pair)
        if direction:
            try:
                with IQ_LOCK:
                    if Iq is None: raise Exception("Iq None")
                    status,tid=Iq.buy(current_amount,pair,direction,1)
                if not status: continue
                emoji = "📈 🚀" if direction=="call" else "📉 🧸"
                bot.send_message(OWNER_ID,f"✅ {emoji} TRADE PLACED!\n📊 {pair}\n🎯 {direction.upper()}\n💵 ${current_amount}\n📝 {reason}")
                time.sleep(65)
                with IQ_LOCK: profit=Iq.check_win_v3(tid); bal=Iq.get_balance()
                LAST_SIGNAL=time.time()
                LAST_TRADE = {"pair": pair,"dir": direction.upper(),"amount": current_amount,"profit": round(profit,2) if profit else 0,"time": datetime.datetime.now().strftime("%H:%M:%S %d/%m")}
                if profit and profit>0:
                    bot.send_message(OWNER_ID,f"💰 🎉 WIN +${round(profit,2)} 🤑\n💳 ${round(bal,2)} 🔄 Reset ${BASE_AMOUNT}")
                    current_amount=BASE_AMOUNT; martingale_level=0
                else:
                    martingale_level+=1
                    if martingale_level>=MAX_MARTINGALE:
                        bot.send_message(OWNER_ID,f"📉 LOSS Reset! 💳 ${round(bal,2)}"); current_amount=BASE_AMOUNT; martingale_level=0
                    else:
                        current_amount=BASE_AMOUNT*(2**martingale_level)
                        bot.send_message(OWNER_ID,f"📉 Loss! Next ${current_amount} 🪜 {martingale_level}")
                save_memory(); return
            except: continue
    LAST_SIGNAL=time.time(); save_memory()
    try: bot.send_message(OWNER_ID,f"⏭️ No signal 💵 ${current_amount} 🧠")
    except: pass

def scanner_loop():
    while True:
        try:
            time.sleep(10)
            if not OWNER_ID or not SCANNING: continue
            wait_time=120 if LAST_SIGNAL==0 else 180
            if time.time()-(RESUME_AT if LAST_SIGNAL==0 else LAST_SIGNAL) < wait_time: continue
            do_trade()
        except: time.sleep(5)

def polling_loop():
    global BOT_RUNNING
    if BOT_RUNNING: return
    BOT_RUNNING=True; delete_webhook(); time.sleep(3)
    while True:
        try: bot.infinity_polling(none_stop=True, timeout=90, long_polling_timeout=90, skip_pending=True)
        except Exception as e:
            if "409" in str(e).lower(): delete_webhook(); time.sleep(15)
            else: time.sleep(5)

threading.Thread(target=scanner_loop, daemon=True).start()
threading.Thread(target=polling_loop, daemon=True).start()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)), use_reloader=False)
