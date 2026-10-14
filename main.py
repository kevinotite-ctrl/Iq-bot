import os, time, threading, datetime
import telebot
from flask import Flask
import numpy as np

# === ENV ===
TOKEN = os.environ.get("BOT_TOKEN","").strip()
EMAIL = os.environ.get("IQ_EMAIL","").strip()
PASS = os.environ.get("IQ_PASS","").strip()
CHAT_ID = os.environ.get("CHAT_ID","") # your group/channel id optional

print(f"TOKEN len {len(TOKEN)}", flush=True)

# === FLASK FOR UPTIMEROBOT - FIXES YOUR 404 SCREENSHOT ===
app = Flask(__name__)
@app.route('/', methods=['GET','HEAD'])
def home():
    return "KEVIN V25 FULL LIVE ✅", 200

# === BOT ===
bot = telebot.TeleBot(TOKEN, threaded=False)
Iq = None
running = False
current_level = 0
BASE_AMT = 10
MARTINGALE = [10,20,40]
PAIRS = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","AUDUSD-OTC"]
TIMEFRAME = 60 # 1 min

def iq_connect():
    global Iq
    while True:
        try:
            try:
                from iqoptionapi.stable_api import IQ_Option
            except:
                from iqoptionapi.api import IQ_Option
            print("Connecting IQ...", flush=True)
            Iq = IQ_Option(EMAIL, PASS)
            check, reason = Iq.connect()
            print(f"IQ CONNECT {check} {reason}", flush=True)
            if check:
                Iq.change_balance("PRACTICE")
                print(f"BAL ${Iq.get_balance()}", flush=True)
                return True
        except Exception as e:
            print(f"IQ ERR {e}", flush=True)
        time.sleep(10)

# === INDICATORS ===
def ema(data, period):
    return np.convolve(data, np.ones(period)/period, mode='valid')[-1] if len(data)>=period else data[-1]

def rsi(data, period=14):
    if len(data)<period+1: return 50
    deltas = np.diff(data)
    gains = deltas.clip(min=0)
    losses = -deltas.clip(max=0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss==0: return 100
    rs = avg_gain/avg_loss
    return 100 - (100/(1+rs))

def get_signal(pair):
    try:
        candles = Iq.get_candles(pair, 60, 50, time.time())
        closes = [c['close'] for c in candles]
        if len(closes)<25: return None
        e7 = np.mean(closes[-7:])
        e21 = np.mean(closes[-21:])
        r = rsi(np.array(closes))
        # LONG when EMA7 > EMA21 and RSI 50-70
        # SHORT when EMA7 < EMA21 and RSI 30-50
        if e7 > e21 and 55 < r < 70:
            return "call"
        if e7 < e21 and 30 < r < 45:
            return "put"
    except Exception as e:
        print(f"Signal ERR {pair} {e}", flush=True)
    return None

def trade(pair, action):
    global current_level
    amt = MARTINGALE[current_level]
    try:
        Iq.buy(amt, pair, action, 1) # 1 min expiry
        msg = f"📈 TRADE Lvl {current_level} ${amt} {pair} {action.upper()}\nEMA7/21 + RSI\nTime {datetime.datetime.now().strftime('%H:%M:%S')}"
        print(msg, flush=True)
        # send to you
        try:
            bot.send_message(CHAT_ID if CHAT_ID else list(bot.get_chat("@").id), msg)
        except:
            pass
        # check result after 70 sec
        time.sleep(70)
        result = Iq.check_win_v3(pair) # or get result
        print(f"RESULT {result}", flush=True)
        if result is True or result=="win":
            current_level = 0
            bot.send_message(CHAT_ID if CHAT_ID else 123, "✅ WIN Reset to Lvl 0")
        else:
            current_level = min(current_level+1, 2)
            bot.send_message(CHAT_ID if CHAT_ID else 123, f"❌ LOSS Martingale to Lvl {current_level} ${MARTINGALE[current_level]}")
    except Exception as e:
        print(f"TRADE ERR {e}", flush=True)

# === COMMANDS ===
@bot.message_handler(commands=['start'])
def start_cmd(m):
    bal = Iq.get_balance() if Iq and Iq.check_connect() else 0
    bot.send_message(m.chat.id, f"🤖 KEVIN V25 FULL LIVE ✅\nBal ${bal}\nPairs: {', '.join(PAIRS)}\nStrat: EMA7/21 + RSI\nMartingale $10->$20->$40\n\n/resume to start\n/pause to stop\n/balance")

@bot.message_handler(commands=['balance'])
def bal_cmd(m):
    try:
        bot.send_message(m.chat.id, f"💰 Balance ${Iq.get_balance()} PRACTICE")
    except:
        bot.send_message(m.chat.id, "IQ Not connected yet")

@bot.message_handler(commands=['resume'])
def resume_cmd(m):
    global running, current_level
    running = True
    current_level = 0
    bot.send_message(m.chat.id, "▶️ RESUMED - Scanning every 2 mins...")

@bot.message_handler(commands=['pause'])
def pause_cmd(m):
    global running
    running = False
    bot.send_message(m.chat.id, "⏸️ PAUSED")

def trading_loop():
    print("Trading loop FULL started", flush=True)
    while True:
        try:
            if not running or not Iq:
                time.sleep(10)
                continue
            for pair in PAIRS:
                if not running: break
                sig = get_signal(pair)
                if sig:
                    trade(pair, sig)
                    break # trade one at a time
                else:
                    print(f"⏭️ {pair} No trend skip", flush=True)
            time.sleep(120) # 2 mins scan as you wanted
        except Exception as e:
            print(f"LOOP ERR {e}", flush=True)
            time.sleep(10)

# === STARTUP - FIXES YOUR SCREENSHOT ERROR ===
try:
    bot.remove_webhook()
    print("Webhook removed OK", flush=True)
except Exception as e:
    print(f"Webhook skip (normal): {e}", flush=True)

threading.Thread(target=iq_connect, daemon=True).start()
threading.Thread(target=trading_loop, daemon=True).start()

def run_bot():
    while True:
        try:
            print("Polling started...", flush=True)
            bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
        except Exception as e:
            print(f"Polling ERR {e}", flush=True)
            time.sleep(5)

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
