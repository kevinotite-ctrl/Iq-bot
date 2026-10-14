import os, time, threading, random, datetime, requests, logging, json
logging.getLogger().setLevel(logging.CRITICAL)
for l in ["", "root", "iqoptionapi", "iqoptionapi.stable_api"]:
    lg = logging.getLogger(l)
    try: lg.setLevel(logging.CRITICAL); lg.propagate=False
    except: pass
from flask import Flask
import telebot
print("=== KEVIN V23 MEMORY ===", flush=True)
app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

STATE_FILE = "kevin_memory.json" # Will stay on Render disk

BASE_AMOUNT=10; MAX_MARTINGALE=3
current_amount=10; martingale_level=0
OWNER_ID=None; Iq=None; SCANNING=True
LAST_SIGNAL=0; RESUME_AT=time.time()
IQ_LOCK=threading.RLock(); BOT_RUNNING=False
LAST_TRADE = {"pair": "None", "dir": "None", "amount": 0, "profit": 0, "time": "Never"}

WEEKEND_PAIRS=["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC","XAUUSD-OTC","EURJPY-OTC","USDJPY-OTC","GBPJPY-OTC"]
WEEKDAY_PAIRS=["EURUSD-OTC","GBPUSD-OTC","AUDUSD-OTC","XAUUSD-OTC","EURJPY-OTC","USDJPY-OTC"]

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
        with open(STATE_FILE, "w") as f:
            json.dump(data, f)
        print(f"💾 SAVED MEMORY {data}", flush=True)
    except Exception as e:
        print(f"save err {e}", flush=True)

def load_memory():
    global current_amount, martingale_level, OWNER_ID, LAST_SIGNAL, RESUME_AT, SCANNING, LAST_TRADE
    try:
        if not os.path.exists(STATE_FILE):
            print("No memory file yet", flush=True)
            return
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        current_amount = data.get("current_amount", 10)
        martingale_level = data.get("martingale_level", 0)
        OWNER_ID = data.get("OWNER_ID")
        LAST_SIGNAL = data.get("LAST_SIGNAL", 0)
        RESUME_AT = data.get("RESUME_AT", time.time())
        SCANNING = data.get("SCANNING", True)
        LAST_TRADE = data.get("LAST_TRADE", LAST_TRADE)
        print(f"🧠 LOADED MEMORY {data}", flush=True)
    except Exception as e:
        print(f"load err {e}", flush=True)

def delete_webhook():
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
        b=telebot.TeleBot(TOKEN); b.remove_webhook()
        time.sleep(1)
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
            ok,reason=Iq.connect()
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
            if Iq is None: return WEEKEND_PAIRS
            all_open=Iq.get_all_open_time()
        if not all_open or not isinstance(all_open, dict): return WEEKEND_PAIRS
        open_dict=all_open.get('turbo', {}) or all_open.get('binary', {}) or {}
        if not open_dict: return WEEKEND_PAIRS
        all_pairs=list(set(WEEKEND_PAIRS+WEEKDAY_PAIRS))
        open_pairs=[]
        for p in all_pairs:
            data=open_dict.get(p)
            if isinstance(data, dict) and data.get('open'): open_pairs.append(p)
            elif data is True: open_pairs.append(p)
        if not open_pairs: return WEEKEND_PAIRS
        return open_pairs
    except: return WEEKEND_PAIRS
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

# Load memory on boot
load_memory()
delete_webhook()
bot=telebot.TeleBot(TOKEN, threaded=False)

@app.route('/')
def home():
    return f"V23 MEMORY BAL {current_amount} LVL {martingale_level} LAST {LAST_TRADE}"

@app.route(f'/{TOKEN}', methods=['POST'])
def wh(): delete_webhook(); return "DELETED",200

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, current_amount, martingale_level
    OWNER_ID=m.chat.id; RESUME_AT=time.time()
    # Don't reset amount if we have memory!
    if os.path.exists(STATE_FILE):
        load_memory()
        bot.send_message(m.chat.id,f"🧠 💾 MEMORY RESTORED! 💾 🧠\n\n💵 Amount: ${current_amount} 🎯\n🪜 Level: {martingale_level}\n📊 Last Trade: {LAST_TRADE['pair']} {LAST_TRADE['dir']} ${LAST_TRADE['amount']} → {LAST_TRADE['profit']}\n⏰ Time: {LAST_TRADE['time']}\n\n🚀 Resuming where we left off! 🔥")
    else:
        current_amount=BASE_AMOUNT; martingale_level=0
        LAST_SIGNAL=0
        bot.send_message(m.chat.id,"✨ 🤖 KEVIN V23 ONLINE ✨\n💾 Memory enabled!")
    save_memory()
    if not iq_connect_force():
        bot.send_message(m.chat.id,"❌ 😭 IQ login failed!")
        return
    open_pairs=get_open_pairs()
    bot.send_message(m.chat.id,f"💰 Balance: ${Iq.get_balance()}\n📊 Open: {', '.join(open_pairs[:4])} 🔥\n\n🚀 /scan 🧪 /testbuy 💳 /balance ⏸️ /pause ▶️ /resume 🧠 /memory")

@bot.message_handler(commands=['memory', 'last'])
def memory_cmd(m):
    global OWNER_ID
    OWNER_ID=m.chat.id
    load_memory()
    bot.send_message(m.chat.id,f"🧠 💾 SAVED MEMORY 💾 🧠\n\n💵 Current Amount: ${current_amount} 🎯\n🪜 Martingale Level: {martingale_level} / {MAX_MARTINGALE}\n📊 Last Trade:\n 📈 Pair: {LAST_TRADE['pair']}\n 🎯 Dir: {LAST_TRADE['dir']}\n 💵 Amount: ${LAST_TRADE['amount']}\n 💰 Profit: {LAST_TRADE['profit']}\n ⏰ Time: {LAST_TRADE['time']}\n\n🤖 Scanning: {'🟢 Active' if SCANNING else '🔴 Paused'} ⏰")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING
    OWNER_ID=m.chat.id; SCANNING=True; RESUME_AT=time.time()
    load_memory()
    save_memory()
    iq_connect_force()
    bot.send_message(m.chat.id,f"▶️ ✅ Resumed from MEMORY! 🧠\n💵 Amount: ${current_amount} (not reset!)\n🪜 Level: {martingale_level}\n📊 Last: {LAST_TRADE['pair']} {LAST_TRADE['profit']}\n🔍 Scanning... 👀")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING
    SCANNING=False
    save_memory()
    bot.send_message(m.chat.id,f"⏸️ 🛌 Paused & Saved! 💾\n💵 Amount ${current_amount} saved!\n📊 Last: {LAST_TRADE['pair']}\nSend /resume to continue same level! ☀️")

@bot.message_handler(commands=['balance','status'])
def status(m):
    global OWNER_ID; OWNER_ID=m.chat.id
    try:
        with IQ_LOCK: bal=Iq.get_balance() if Iq else None
        if bal is None:
            iq_connect_force()
            with IQ_LOCK: bal=Iq.get_balance()
        bot.send_message(m.chat.id,f"💳 💰 WALLET 💰 💳\n\n💵 Balance: ${round(bal,2)} 💎\n💸 Trade Amount: ${current_amount} 🎯 (REMEMBERED! 🧠)\n📈 Level: {martingale_level}\n📊 Last Trade: {LAST_TRADE['pair']} {LAST_TRADE['dir']} → {LAST_TRADE['profit']}\n⏰ {LAST_TRADE['time']}\n\n🤖 {'🟢 Active' if SCANNING else '🔴 Paused'}")
    except:
        bot.send_message(m.chat.id,f"💳 Wallet 💾\n💵 Amt ${current_amount} Lvl {martingale_level}\n📊 Last {LAST_TRADE}")

@bot.message_handler(commands=['scan'])
def scan(m):
    global OWNER_ID; OWNER_ID=m.chat.id; save_memory()
    bot.send_message(m.chat.id,"🔍 👀 Scanning... 📡")
    threading.Thread(target=do_trade, daemon=True).start()

@bot.message_handler(commands=['testbuy'])
def testbuy(m):
    global OWNER_ID; OWNER_ID=m.chat.id
    bot.send_message(m.chat.id,"🧪 🔬 TEST BUY... 🚀")
    try:
        open_pairs=get_open_pairs()
        test_pair=open_pairs[0] if open_pairs else "EURUSD-OTC"
        with IQ_LOCK:
            if Iq is None: iq_connect_force()
            status,tid=Iq.buy(10,test_pair,"call",1)
        if status:
            bot.send_message(m.chat.id,f"✅ 🎉 BUY {test_pair} ID {tid} ⏳ 65s...")
            time.sleep(65)
            with IQ_LOCK: profit=Iq.check_win_v3(tid); bal=Iq.get_balance()
            bot.send_message(m.chat.id,f"{'🏆 WIN' if profit>0 else '📉 LOSS'} {profit} Bal ${round(bal,2)}")
        else:
            bot.send_message(m.chat.id,f"❌ Failed {test_pair}: {tid}")
    except Exception as e:
        bot.send_message(m.chat.id,f"❌ {e}")

def do_trade():
    global LAST_SIGNAL, current_amount, martingale_level, LAST_TRADE
    if not OWNER_ID: return
    if Iq is None: iq_connect_force()
    PAIRS=get_open_pairs(); random.shuffle(PAIRS)
    try: bot.send_message(OWNER_ID,f"🔍 📡 Scanning {len(PAIRS)}... 💵 ${current_amount} 🧠 Remembered!")
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
                LAST_TRADE = {
                    "pair": pair,
                    "dir": direction.upper(),
                    "amount": current_amount,
                    "profit": round(profit,2) if profit else 0,
                    "time": datetime.datetime.now().strftime("%H:%M:%S %d/%m")
                }
                if profit and profit>0:
                    bot.send_message(OWNER_ID,f"💰 🎉 JACKPOT! +${round(profit,2)} 🤑\n💳 ${round(bal,2)} 💎\n🔄 Reset to ${BASE_AMOUNT} ✨")
                    current_amount=BASE_AMOUNT; martingale_level=0
                else:
                    martingale_level+=1
                    if martingale_level>=MAX_MARTINGALE:
                        bot.send_message(OWNER_ID,f"📉 😭 LOSS! Reset! 🌱\n💳 ${round(bal,2)}")
                        current_amount=BASE_AMOUNT; martingale_level=0
                    else:
                        current_amount=BASE_AMOUNT*(2**martingale_level)
                        bot.send_message(OWNER_ID,f"📉 😢 Loss! Next ${current_amount} 🪜 {martingale_level}")
                save_memory() # SAVE AFTER EVERY TRADE!
                return
            except: continue
    LAST_SIGNAL=time.time()
    save_memory()
    try: bot.send_message(OWNER_ID,f"⏭️ 💤 No signal 💵 ${current_amount} 🧠")
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
