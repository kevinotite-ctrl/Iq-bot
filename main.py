import os, time, threading, random, datetime
from flask import Flask
import telebot

print("=== KEVIN BOT V13.1 WEBHOOK DELETE + MARTINGALE SAFE ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

# MARTINGALE SETTINGS
BASE_AMOUNT = 10
MAX_MARTINGALE = 3  # $10 -> $20 -> $40 then reset
current_amount = BASE_AMOUNT
martingale_level = 0

OWNER_ID = None
Iq = None
SCANNING = True
LAST_SIGNAL = 0
RESUME_AT = time.time()

WEEKEND_PAIRS = ["EURUSD-OTC", "GBPUSD-OTC"]
WEEKDAY_PAIRS = ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC"]

def get_pairs():
    wd = datetime.datetime.now().weekday()
    return WEEKEND_PAIRS if wd >= 5 else WEEKDAY_PAIRS

def get_rsi(candles, period=14):
    try:
        closes=[c['close'] for c in candles]
        gains=[]; losses=[]
        for i in range(1,len(closes)):
            d=closes[i]-closes[i-1]
            gains.append(max(d,0)); losses.append(max(-d,0))
        if len(gains)<period: return 50
        ag=sum(gains[-period:])/period; al=sum(losses[-period:])/period
        if al==0: return 70
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
        print("Connecting IQ...", flush=True)
        # KILL OLD CONNECTION - FIX FOR get_candles need reconnect
        if Iq:
            try: Iq.close()
            except: pass
            Iq=None
            time.sleep(2)
        Iq = IQ_Option(EMAIL, PASS)
        check, reason = Iq.connect()
        print(f"IQ CONNECT {check} {reason}", flush=True)
        if check:
            time.sleep(3) # Wait for candles channel
            Iq.change_balance("PRACTICE")
            print(f"BAL {Iq.get_balance()}", flush=True)
            return True
    except Exception as e: print(f"IQ ERR {e}", flush=True)
    return False

def analyze(pair):
    try:
        # SAFE get_candles with retry - FIX FOR YOUR LOG
        for _ in range(3):
            try:
                candles = Iq.get_candles(pair, 60, 50, time.time())
                if candles and len(candles)>=25:
                    break
            except Exception as e:
                if "need reconnect" in str(e).lower():
                    print("RECONNECTING IQ...", flush=True)
                    iq_connect()
                    time.sleep(3)
                continue
        else:
            return None, "No candles"
            
        ema7=get_ema(candles[-15:],7); ema21=get_ema(candles,21); rsi=get_rsi(candles,14); close=candles[-1]['close']
        if close>ema7>ema21 and 55<rsi<75: return "call", f"UP EMA7 {round(ema7,5)} > EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        elif close<ema7<ema21 and 25<rsi<45: return "put", f"DOWN EMA7 {round(ema7,5)} < EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        else: return None, f"SKIP RSI {round(rsi,1)}"
    except Exception as e: return None, f"Err {e}"

bot = telebot.TeleBot(TOKEN)

# === DELETE WEBHOOK FUNCTION ===
def delete_webhook():
    try:
        bot.remove_webhook()
        print("✅ WEBHOOK DELETED - Now using polling", flush=True)
        time.sleep(1)
        # Also delete via API directly to be sure
        import requests
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True")
        print("✅ WEBHOOK DELETED VIA API", flush=True)
        return True
    except Exception as e:
        print(f"Webhook delete err {e}", flush=True)
        return False

# DELETE WEBHOOK ON STARTUP
delete_webhook()

@app.route('/')
def home(): 
    try: b=Iq.get_balance() if Iq else "NO IQ"
    except: b="?"
    return f"V13.1 WEBHOOK DELETED BAL {b} AMT {current_amount} LVL {martingale_level}"

# KEEP WEBHOOK ROUTE BUT IT WILL AUTO-DELETE
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    # If webhook still hits, delete it immediately
    delete_webhook()
    return "WEBHOOK DELETED",200

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, current_amount, martingale_level
    OWNER_ID=m.chat.id; RESUME_AT=time.time(); LAST_SIGNAL=0
    current_amount=BASE_AMOUNT; martingale_level=0
    if not Iq: iq_connect()
    try: bal=round(Iq.get_balance(),2)
    except: bal="?"
    bot.send_message(m.chat.id, f"🤖 V13.1 MARTINGALE SAFE\n✅ WEBHOOK DELETED\nBal ${bal}\nBase ${BASE_AMOUNT} Max x{MAX_MARTINGALE}\n$10 -> $20 -> $40 then reset\nEMA+RSI only\n/resume /pause /balance /delete_webhook")

@bot.message_handler(commands=['delete_webhook', 'delwebhook', 'fix'])
def delhook(m):
    global OWNER_ID
    OWNER_ID=m.chat.id
    bot.send_message(m.chat.id, "🔄 Deleting webhook...")
    if delete_webhook():
        bot.send_message(m.chat.id, "✅ Webhook deleted! Bot now using polling.\nNow send /resume")
    else:
        bot.send_message(m.chat.id, "❌ Failed to delete, but polling should still work")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING
    OWNER_ID=m.chat.id; SCANNING=True; RESUME_AT=time.time(); LAST_SIGNAL=0
    delete_webhook() # Ensure webhook deleted on resume
    if not Iq: iq_connect()
    bot.send_message(m.chat.id, f"▶️ RESUMED Martingale Lvl {martingale_level} Amt ${current_amount}")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING; SCANNING=False
    bot.send_message(m.chat.id,"⏸️ Paused")

@bot.message_handler(commands=['balance','status','pairs','account'])
def status(m):
    global OWNER_ID
    OWNER_ID=m.chat.id
    if not Iq: iq_connect()
    try: b=round(Iq.get_balance(),2)
    except: b="?"
    bot.send_message(m.chat.id, f"BAL ${b}\nAmt ${current_amount} Lvl {martingale_level}/{MAX_MARTINGALE}\nEmail: {EMAIL}\nPairs: {', '.join(get_pairs())}")

@bot.message_handler(commands=['scan'])
def scan(m):
    global OWNER_ID; OWNER_ID=m.chat.id; do_trade()

@bot.message_handler(commands=['setaccount'])
def setaccount(m):
    global OWNER_ID, EMAIL, PASS
    OWNER_ID=m.chat.id
    parts=m.text.split()
    if len(parts)<3:
        bot.send_message(m.chat.id, "Usage: /setaccount email pass")
        return
    EMAIL=parts[1]; PASS=parts[2]
    bot.send_message(m.chat.id, f"🔄 Switching to {EMAIL}...")
    if iq_connect():
        bot.send_message(m.chat.id, f"✅ Switched to {EMAIL} Bal ${Iq.get_balance()}\n⚠️ Update Render Env vars to make permanent")
    else:
        bot.send_message(m.chat.id, "❌ Login failed")

def do_trade():
    global LAST_SIGNAL, current_amount, martingale_level
    if not Iq and not iq_connect():
        if OWNER_ID: bot.send_message(OWNER_ID,"❌ IQ login failed")
        LAST_SIGNAL=time.time(); return
    if not OWNER_ID: return
    PAIRS=get_pairs(); random.shuffle(PAIRS)
    for pair in PAIRS:
        direction, reason = analyze(pair)
        print(f"ANALYZE {pair} {direction} {reason} AMT {current_amount} LVL {martingale_level}", flush=True)
        if direction:
            try:
                bot.send_message(OWNER_ID,f"📊 SIGNAL {pair} {direction.upper()}\nAmt ${current_amount} Lvl {martingale_level}\n{reason}")
                status, trade_id = Iq.buy(current_amount, pair, direction, 1)
                if not status: continue
                bot.send_message(OWNER_ID,f"✅ BOUGHT {pair} {direction.upper()} ${current_amount} Lvl {martingale_level}\nWait 65s...")
                time.sleep(65)
                profit=Iq.check_win_v3(trade_id); bal=Iq.get_balance(); LAST_SIGNAL=time.time()

                if profit and profit>0:
                    bot.send_message(OWNER_ID,f"💰 WIN +${round(profit,2)}\n{reason}\nBal ${round(bal,2)}\n🔄 Reset to ${BASE_AMOUNT}")
                    current_amount=BASE_AMOUNT
                    martingale_level=0
                else:
                    martingale_level+=1
                    if martingale_level >= MAX_MARTINGALE:
                        bot.send_message(OWNER_ID,f"📉 LOSS -${current_amount}\n{reason}\n⚠️ 3 losses -> RESET to ${BASE_AMOUNT}\nBal ${round(bal,2)}")
                        current_amount=BASE_AMOUNT
                        martingale_level=0
                    else:
                        current_amount = BASE_AMOUNT * (2 ** martingale_level)
                        bot.send_message(OWNER_ID,f"📉 LOSS\n{reason}\n📈 Next ${current_amount} Lvl {martingale_level}\nBal ${round(bal,2)}")
                return
            except Exception as e: print(f"BUY ERR {e}", flush=True); continue
    LAST_SIGNAL=time.time()
    try: bal=round(Iq.get_balance(),2)
    except: bal="?"
    if OWNER_ID: bot.send_message(OWNER_ID,f"⏭️ No trend Skip | Amt ${current_amount} Lvl {martingale_level} | Bal ${bal}")

def scanner():
    while True:
        try:
            time.sleep(10)
            if not OWNER_ID or not SCANNING: continue
            if time.time() - (RESUME_AT if LAST_SIGNAL==0 else LAST_SIGNAL) < (120 if LAST_SIGNAL==0 else 180): continue
            do_trade()
        except Exception as e: print(f"SCAN ERR {e}", flush=True); time.sleep(5)

threading.Thread(target=scanner, daemon=True).start()

# DELETE WEBHOOK AGAIN BEFORE POLLING
delete_webhook()

# START POLLING IN THREAD
def start_polling():
    while True:
        try:
            print("Starting polling...", flush=True)
            delete_webhook()
            bot.infinity_polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Polling died {e}, restarting in 5s", flush=True)
            time.sleep(5)

threading.Thread(target=start_polling, daemon=True).start()

if __name__=="__main__":
    # On Render, Flask keeps running, polling in background
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
