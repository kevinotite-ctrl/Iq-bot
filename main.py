# V21.4 PRICE ACTION - FINAL FIXED - RENDER READY
import time, json, os, random, threading
from datetime import datetime, timedelta
import telebot

try:
    from iqoptionapi.stable_api import IQ_Option
except ImportError:
    from iqoption.api import IQ_Option

# ========== PUT YOUR DETAILS HERE - KEEP QUOTES ==========
IQ_EMAIL = "YOUR_IQ_EMAIL_HERE"
IQ_PASSWORD = "YOUR_IQ_PASSWORD_HERE"
TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN_HERE"
PRIVATE_CHAT_ID = 123456789
CHANNEL_ID = "@KEVINTRAILBLAZE"
# ==========================================================

# Render Environment will override if set (recommended)
IQ_EMAIL = os.getenv("IQ_EMAIL", IQ_EMAIL).strip()
IQ_PASSWORD = os.getenv("IQ_PASSWORD", IQ_PASSWORD).strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", TELEGRAM_TOKEN).strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", CHANNEL_ID).strip()
try:
    PRIVATE_CHAT_ID = int(os.getenv("PRIVATE_CHAT_ID", str(PRIVATE_CHAT_ID)))
except:
    pass

print(f"Token check: len={len(TELEGRAM_TOKEN)} has_colon={':' in TELEGRAM_TOKEN}")

PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURJPY-OTC"]
AMOUNTS = [100, 200, 400]
SCAN_INTERVAL = 60
DAILY_STOP_LOSS = -600
EXPIRY = 2

DATA_FILE = "daily_trades.json"
STATE_FILE = "bot_state.json"

current_level = 0
DAILY_LOSS = 0
NEXT_SCAN_AT = datetime.now()
is_paused = False
last_reason = "Starting..."

bot = telebot.TeleBot(TELEGRAM_TOKEN)
Iq = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
Iq.connect()
print("IQ Connected:", Iq.check_connect())

def load_json(f, d):
    if os.path.exists(f):
        try:
            with open(f, 'r') as file:
                return json.load(file)
        except:
            return d
    return d

def save_json(f, d):
    with open(f, 'w') as file:
        json.dump(file, d, indent=2)

def get_rsi(c, p=14):
    if len(c) < p + 1:
        return 50
    g = l = 0
    for i in range(1, p + 1):
        diff = c[-i] - c[-i-1]
        if diff > 0:
            g += diff
        else:
            l += abs(diff)
    if l == 0:
        return 100
    rs = g / l if l!= 0 else 0
    return 100 - (100 / (1 + rs))

def send_private(t):
    try:
        bot.send_message(PRIVATE_CHAT_ID, t)
    except Exception as e:
        print(e)

def send_channel(t):
    try:
        bot.send_message(CHANNEL_ID, t)
    except Exception as e:
        print(e)

def analyze_pair(pair):
    global last_reason
    try:
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles) < 20:
            return None
        opens, closes, highs, lows = [], [], [], []
        for c in candles:
            if isinstance(c, dict):
                opens.append(c.get('open', 0))
                closes.append(c.get('close', 0))
                highs.append(c.get('max', c.get('close', 0)))
                lows.append(c.get('min', c.get('close', 0)))
            elif len(c) >= 3:
                opens.append(c[1])
                closes.append(c[2])
                highs.append(c[3] if len(c) > 3 else c[2])
                lows.append(c[4] if len(c) > 4 else c[1])
        if len(closes) < 20:
            return None
        po, pc, co, cc, ch, cl = opens[-2], closes[-2], opens[-1], closes[-1], highs[-1], lows[-1]
        pb, cb = abs(pc - po), abs(cc - co)
        if cb == 0:
            return None
        rsi = get_rsi(closes, 14)
        is_prev_bear = pc < po
        is_curr_bull = cc > co
        bull_eng = is_prev_bear and is_curr_bull and co <= pc and cc >= po and cb > pb * 0.8
        bull_pin = (co - cl if is_curr_bull else cc - cl) > cb * 1.5
        if (bull_eng or bull_pin) and 35 <= rsi <= 65:
            conf = 78 + (12 if bull_eng else 8) + (10 if 45 <= rsi <= 58 else 0)
            return {"pair": pair, "dir": "call", "conf": min(conf, 95), "rsi": rsi, "pattern": "BULL ENGULFING" if bull_eng else "BULL PIN"}
        is_prev_bull = pc > po
        is_curr_bear = cc < co
        bear_eng = is_prev_bull and is_curr_bear and co >= pc and cc <= po and cb > pb * 0.8
        bear_pin = (ch - co if is_curr_bear else ch - cc) > cb * 1.5
        if (bear_eng or bear_pin) and 35 <= rsi <= 65:
            conf = 78 + (12 if bear_eng else 8) + (10 if 42 <= rsi <= 55 else 0)
            return {"pair": pair, "dir": "put", "conf": min(conf, 95), "rsi": rsi, "pattern": "BEAR ENGULFING" if bear_eng else "BEAR PIN"}
        last_reason = f"{pair} No PA RSI {rsi:.1f}"
    except Exception as e:
        last_reason = f"{pair} Err {e}"
    return None

def do_trade(manual=False):
    global current_level, DAILY_LOSS, NEXT_SCAN_AT
    if is_paused:
        return
    if DAILY_LOSS <= DAILY_STOP_LOSS:
        return
    random.shuffle(PAIRS)
    sig = None
    for p in PAIRS:
        sig = analyze_pair(p)
        if sig:
            break
    if not sig:
        NEXT_SCAN_AT = datetime.now() + timedelta(seconds=SCAN_INTERVAL)
        if manual:
            send_private(f"No signal now\n{last_reason}\nNext 01:00")
        return
    amt = AMOUNTS[current_level]
    pair = sig['pair']
    direction = sig['dir']
    conf = sig['conf']
    pattern = sig['pattern']
    rsi = sig['rsi']
    check, trade_id = Iq.buy(amt, pair, direction, EXPIRY)
    if not check:
        send_private(f"Buy FAIL {pair} {direction} {trade_id}")
        NEXT_SCAN_AT = datetime.now() + timedelta(seconds=20)
        return
    send_private(f"✅ {pattern} {conf}%\n{pair} {direction.upper()} ${amt} Lvl {current_level+1}\nRSI {rsi:.1f}")
    msg = f"👑 KEVIN TRAILBLAZE 👑\n{'🟢 CALL' if direction=='call' else '🔴 PUT'} - {pair} \n💰 {pair} | ⏰ {EXPIRY} MIN | 🎯 {conf}% | 💵 ${amt}\n📊 {pattern} RSI {rsi:.1f}\n🔥 PRICE ACTION V21"
    send_channel(msg)
    time.sleep(125)
    result = Iq.check_win_v3(trade_id)
    if result is True or (isinstance(result, (int, float)) and result > 0):
        profit = float(result) if isinstance(result, (int, float)) else amt * 0.85
        if profit < 1:
            profit = amt * 0.85
        send_private(f"WIN +${profit:.2f} {pattern}")
        send_channel(f"👑 WIN +${profit:.2f} {pair} {conf}% {pattern}")
        current_level = 0
    else:
        send_private(f"LOSS -${amt} {pattern}")
        send_channel(f"👑 LOSS -${amt} {pair} {conf}% {pattern}")
        DAILY_LOSS += -amt
        current_level = min(current_level + 1, len(AMOUNTS) - 1)
    save_json(STATE_FILE, {"level": current_level, "daily_loss": DAILY_LOSS})
    NEXT_SCAN_AT = datetime.now() + timedelta(seconds=SCAN_INTERVAL)

@bot.message_handler(func=lambda m: True)
def handle(m):
    global current_level, DAILY_LOSS, is_paused
    if m.chat.id!= PRIVATE_CHAT_ID:
        return
    txt = m.text.strip()
    if txt == "/start":
        send_private(f"🤖 V21.4 PRICE ACTION ONLINE ✅\nBal ${Iq.get_balance():.2f}\nNext ${AMOUNTS[current_level]}")
    elif txt == "/scan":
        do_trade(manual=True)
    elif txt == "/reset":
        current_level = 0
        DAILY_LOSS = 0
        save_json(STATE_FILE, {"level": 0, "daily_loss": 0})
        send_private("Reset done")
    elif txt == "/pause":
        is_paused = True
        send_private("Paused")
    elif txt == "/resume":
        is_paused = False
        send_private("Resumed")

def run_polling():
    while True:
        try:
            bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except Exception as e:
            print(f"Polling err {e}")
            time.sleep(5)

def run_scan():
    while True:
        try:
            if datetime.now() >= NEXT_SCAN_AT and not is_paused:
                do_trade()
        except Exception as e:
            print(f"Scan err {e}")
        time.sleep(5)

if __name__ == "__main__":
    s = load_json(STATE_FILE, {"level": 0, "daily_loss": 0})
    current_level = s.get("level", 0)
    DAILY_LOSS = s.get("daily_loss", 0)
    threading.Thread(target=run_polling, daemon=True).start()
    bal = Iq.get_balance()
    send_private(f"🤖 V21.4 ONLINE ✅\nBal ${bal:.2f} Next ${AMOUNTS[current_level]}")
    print(f"ONLINE Bal ${bal:.2f}")
    run_scan()
