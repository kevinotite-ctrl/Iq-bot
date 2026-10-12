# V21.2 RENDER FIXED - NO CRASH
import time, json, os, random, threading
from datetime import datetime, timedelta
import telebot

# FIXED IMPORT - tries both ways
try:
    from iqoptionapi.stable_api import IQ_Option
except:
    try:
        from iqoption.api import IQ_Option
    except:
        print("Trying pip iqoptionapi...")
        from iqoptionapi.stable_api import IQ_Option

# ========== CONFIG ==========
IQ_EMAIL = "YOUR_IQ_EMAIL"
IQ_PASSWORD = "YOUR_IQ_PASSWORD"
TELEGRAM_TOKEN = "8976204524:AAEcQXl3F1Tsu7YigXr3oBYar8MPe1PHVFo"


Use this token to access the HTTP API:
8976204524:AAEcQXl3F1Tsu7YigXr3oBYar8MPe1PHVFo
Keep your token secure and store it safely, it can be used by anyone to control your bot.

For a description of the Bot API, see this page: https://core.telegram.org/bots/api"
PRIVATE_CHAT_ID = 123456789
CHANNEL_ID = "@KEVINTRAILBLAZE"

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

def load_json(file, default):
    if os.path.exists(file):
        try:
            with open(file, 'r') as f: return json.load(f)
        except: return default
    return default

def save_json(file, data):
    with open(file, 'w') as f: json.dump(f, data, indent=2)

def get_rsi(closes, period=14):
    if len(closes) < period+1: return 50
    gains, losses = 0, 0
    for i in range(1, period+1):
        diff = closes[-i] - closes[-i-1]
        if diff > 0: gains += diff
        else: losses += abs(diff)
    if losses == 0: return 100
    rs = gains / losses if losses!=0 else 0
    return 100 - (100 / (1 + rs))

def send_private(text):
    try: bot.send_message(PRIVATE_CHAT_ID, text)
    except Exception as e: print("Private err", e)

def send_channel(text):
    try: bot.send_message(CHANNEL_ID, text)
    except Exception as e: print("Channel err", e)

def log_trade(pair, direction, amount, conf, result, profit, pattern=""):
    today = datetime.now().strftime("%Y-%m-%d")
    data = load_json(DATA_FILE, {})
    if today not in data: data[today] = {"trades": [], "wins":0, "losses":0, "profit":0, "total":0}
    data[today]["trades"].append({"time": datetime.now().strftime("%H:%M"), "pair": pair, "dir": direction, "amount": amount, "conf": conf, "result": result, "profit": profit, "pattern": pattern})
    data[today]["total"] += 1
    if result == "WIN": data[today]["wins"] += 1
    else: data[today]["losses"] += 1
    data[today]["profit"] += profit
    data[today]["trades"] = data[today]["trades"][-50:]
    save_json(DATA_FILE, data)

def get_summary(date_str=None):
    if not date_str: date_str = datetime.now().strftime("%Y-%m-%d")
    data = load_json(DATA_FILE, {})
    if date_str not in data: return f"📊 DAILY SUMMARY - {date_str}\nNo trades yet"
    d = data[date_str]
    winrate = (d['wins']/d['total']*100) if d['total']>0 else 0
    return f"📊 DAILY SUMMARY - {date_str}\nTotal: {d['total']} | ✅ {d['wins']} | ❌ {d['losses']}\nWin Rate: {winrate:.1f}%\nProfit: ${d['profit']:+.0f}"

def analyze_price_action(pair):
    global last_reason
    try:
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles) < 20: return None
        opens, closes, highs, lows = [], [], [], []
        for c in candles:
            if isinstance(c, dict):
                opens.append(c.get('open', 0)); closes.append(c.get('close', 0)); highs.append(c.get('max', c.get('close',0))); lows.append(c.get('min', c.get('close',0)))
            elif isinstance(c, (list,tuple)) and len(c)>=3:
                opens.append(c[1]); closes.append(c[2]); highs.append(c[3] if len(c)>3 else c[2]); lows.append(c[4] if len(c)>4 else c[1])
        if len(closes) < 20: return None
        prev_open, prev_close = opens[-2], closes[-2]
        curr_open, curr_close, curr_high, curr_low = opens[-1], closes[-1], highs[-1], lows[-1]
        prev_body = abs(prev_close - prev_open)
        curr_body = abs(curr_close - curr_open)
        rsi = get_rsi(closes, 14)
        is_prev_bearish = prev_close < prev_open
        is_curr_bullish = curr_close > curr_open
        is_bullish_engulfing = is_prev_bearish and is_curr_bullish and (curr_open <= prev_close) and (curr_close >= prev_open) and (curr_body > prev_body * 0.8)
        lower_wick = curr_open - curr_low if is_curr_bullish else curr_close - curr_low
        is_bullish_pin = lower_wick > curr_body * 1.5
        if (is_bullish_engulfing or is_bullish_pin) and (35 <= rsi <= 65):
            conf = 78 + (12 if is_bullish_engulfing else 8) + (10 if 45 <= rsi <= 58 else 0)
            pattern = "BULL ENGULFING" if is_bullish_engulfing else "BULL PIN BAR"
            return {"pair": pair, "dir": "call", "conf": min(conf,95), "rsi": rsi, "pattern": pattern}
        is_prev_bullish = prev_close > prev_open
        is_curr_bearish = curr_close < curr_open
        is_bearish_engulfing = is_prev_bullish and is_curr_bearish and (curr_open >= prev_close) and (curr_close <= prev_open) and (curr_body > prev_body * 0.8)
        upper_wick = curr_high - curr_open if is_curr_bearish else curr_high - curr_close
        is_bearish_pin = upper_wick > curr_body * 1.5
        if (is_bearish_engulfing or is_bearish_pin) and (35 <= rsi <= 65):
            conf = 78 + (12 if is_bearish_engulfing else 8) + (10 if 42 <= rsi <= 55 else 0)
            pattern = "BEAR ENGULFING" if is_bearish_engulfing else "BEAR PIN BAR"
            return {"pair": pair, "dir": "put", "conf": min(conf,95), "rsi": rsi, "pattern": pattern}
        last_reason = f"{pair}: No PA RSI {rsi:.1f}"
    except Exception as e:
        last_reason = f"{pair}: Error {e}"
    return None

def do_trade(is_manual=False):
    global current_level, DAILY_LOSS, NEXT_SCAN_AT
    if is_paused: return
    if DAILY_LOSS <= DAILY_STOP_LOSS: send_private(f"🛑 DAILY STOP ${DAILY_STOP_LOSS}"); return
    random.shuffle(PAIRS)
    signal = None
    for pair in PAIRS:
        signal = analyze_price_action(pair)
        if signal: break
    if not signal:
        NEXT_SCAN_AT = datetime.now() + timedelta(seconds=SCAN_INTERVAL)
        if is_manual: send_private(f"⏭️ No signal now\nLast: {last_reason}\nNext 01:00")
        return
    amount = AMOUNTS[current_level]
    pair, direction, conf, pattern, rsi = signal['pair'], signal['dir'], signal['conf'], signal['pattern'], signal['rsi']
    check, trade_id = Iq.buy(amount, pair, direction, EXPIRY)
    if not check:
        send_private(f"⚠️ Buy FAILED {pair} {direction.upper()} ${amount}\nReason: {trade_id}")
        NEXT_SCAN_AT = datetime.now() + timedelta(seconds=20)
        return
    send_private(f"✅ {pattern} {conf}%\n{pair} {direction.upper()} ${amount} Lvl {current_level+1}\nRSI {rsi:.1f}")
    if direction == "call":
        ch_msg = f"👑 KEVIN TRAILBLAZE 👑\n🟢 CALL UP - {pair} 🟢\n━━━━━━━━━━━━━━━━━━\n💰 Pair: {pair}\n⏰ Expiry: {EXPIRY} MIN\n🎯 Confidence: {conf}%\n💵 Amount: ${amount}\n📊 Pattern: {pattern}\n📈 RSI: {rsi:.1f}\n━━━━━━━━━━━━━━━━━━\n🔥 PRICE ACTION V21"
    else:
        ch_msg = f"👑 KEVIN TRAILBLAZE 👑\n🔴 PUT DOWN - {pair} 🔴\n━━━━━━━━━━━━━━━━━━\n💰 Pair: {pair}\n⏰ Expiry: {EXPIRY} MIN\n🎯 Confidence: {conf}%\n💵 Amount: ${amount}\n📊 Pattern: {pattern}\n📉 RSI: {rsi:.1f}\n━━━━━━━━━━━━━━━━━━\n🔥 PRICE ACTION V21"
    send_channel(ch_msg)
    time.sleep(125)
    result = Iq.check_win_v3(trade_id)
    if result is True or (isinstance(result,(int,float)) and result>0):
        profit = float(result) if isinstance(result,(int,float)) else amount*0.85
        if profit < 1: profit = amount*0.85
        send_private(f"💰 WIN +${profit:.2f} {conf}% {pattern}")
        send_channel(f"👑 KEVIN TRAILBLAZE 👑\n💰 WIN +${profit:.2f} {pair} {conf}% ✅ {pattern}")
        log_trade(pair, direction.upper(), amount, conf, "WIN", profit, pattern)
        current_level = 0
    else:
        send_private(f"📉 LOSS -${amount} {pattern}")
        send_channel(f"👑 KEVIN TRAILBLAZE 👑\n📉 LOSS -${amount} {pair} {conf}% {pattern}")
        log_trade(pair, direction.upper(), amount, conf, "LOSS", -amount, pattern)
        DAILY_LOSS += -amount
        current_level = min(current_level+1, len(AMOUNTS)-1)
    save_json(STATE_FILE, {"level": current_level, "daily_loss": DAILY_LOSS})
    NEXT_SCAN_AT = datetime.now() + timedelta(seconds=SCAN_INTERVAL)

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    global current_level, DAILY_LOSS, is_paused
    if message.chat.id!= PRIVATE_CHAT_ID: return
    txt = message.text.strip()
    if txt == "/start": send_private(f"🤖 V21.2 RENDER FIXED ✅\nBal ${Iq.get_balance():.2f}\nNext ${AMOUNTS[current_level]}")
    elif txt == "/scan": do_trade(is_manual=True)
    elif txt in ["/summary","/today"]: send_private(get_summary())
    elif txt == "/balance": send_private(f"💰 Balance: ${Iq.get_balance():.2f}\n{get_summary()}")
    elif txt == "/reset": current_level=0; DAILY_LOSS=0; save_json(STATE_FILE, {"level":0,"daily_loss":0}); send_private("✅ Reset done")
    elif txt == "/pause": is_paused=True; send_private("⏸️ Paused")
    elif txt == "/resume": is_paused=False; send_private("▶️ Resumed")

def run_bot_polling():
    while True:
        try: bot.infinity_polling(timeout=10, long_polling_timeout=5)
        except: time.sleep(5)

def run_scan_loop():
    while True:
        try:
            if datetime.now() >= NEXT_SCAN_AT and not is_paused: do_trade()
        except: pass
        time.sleep(5)

if __name__ == "__main__":
    state = load_json(STATE_FILE, {"level":0,"daily_loss":0})
    current_level = state.get("level",0)
    DAILY_LOSS = state.get("daily_loss",0)
    threading.Thread(target=run_bot_polling, daemon=True).start()
    bal = Iq.get_balance()
    send_private(f"🤖 V21.2 ONLINE RENDER FIXED ✅\nBal ${bal:.2f} Next ${AMOUNTS[current_level]}")
    print(f"🤖 V21.2 ONLINE Bal ${bal:.2f}")
    run_scan_loop()
