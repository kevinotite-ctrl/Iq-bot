# V20.3 GOLD STYLE + 60s SCAN + DAILY SUMMARY
# Kevin Trailblaze - Binary Bot - Luxury Channel Format
# 👑 KEVIN TRAILBLAZE 👑 Style like Gold Bot

import time, json, os, random, threading
from datetime import datetime, timedelta
import pytz
from iqoptionapi.stable_api import IQ_Option
from telegram import Bot
import asyncio

# ========== CONFIG - EDIT THESE ==========
IQ_EMAIL = "YOUR_IQ_EMAIL"
IQ_PASSWORD = "YOUR_IQ_PASSWORD"
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
PRIVATE_CHAT_ID = 123456789
CHANNEL_ID = "@KEVINTRAILBLAZE"

PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURJPY-OTC"]
AMOUNTS = [100, 200, 400]
SCAN_INTERVAL = 60
DAILY_STOP_LOSS = -600
EXPIRY = 2

DATA_FILE = "daily_trades.json"
STATE_FILE = "bot_state.json"
LAGOS_TZ = pytz.timezone("Africa/Lagos")

current_level = 0
DAILY_LOSS = 0
NEXT_SCAN_AT = datetime.now()
is_paused = False
last_reason = "Starting..."
bot = Bot(token=TELEGRAM_TOKEN)
loop = asyncio.new_event_loop()

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

def get_ema(candles, period):
    closes = [c[2] for c in candles]
    if len(closes) < period: return None
    ema = sum(closes[-period:]) / period
    k = 2 / (period + 1)
    for price in closes[-period:]:
        ema = price * k + ema * (1 - k)
    return ema

def get_rsi(candles, period=14):
    closes = [c[2] for c in candles]
    if len(closes) < period+1: return 50
    gains, losses = 0, 0
    for i in range(1, period+1):
        diff = closes[-i] - closes[-i-1]
        if diff > 0: gains += diff
        else: losses += abs(diff)
    if losses == 0: return 100
    rs = gains / losses
    return 100 - (100 / (1 + rs))

def get_volatility(candles, period=10):
    try:
        highs = [c[2] for c in candles[-period:]]
        lows = [c[2] for c in candles[-period:]]
        return max(highs) - min(lows) if highs else 1
    except: return 1

def send_private(text):
    try:
        try: loop.run_until_complete(bot.send_message(chat_id=PRIVATE_CHAT_ID, text=text))
        except: asyncio.run(bot.send_message(chat_id=PRIVATE_CHAT_ID, text=text))
    except Exception as e: print("Private error:", e)

def send_channel(text):
    try:
        try: loop.run_until_complete(bot.send_message(chat_id=CHANNEL_ID, text=text))
        except: asyncio.run(bot.send_message(chat_id=CHANNEL_ID, text=text))
        print(f"✅ SENT to {CHANNEL_ID}")
    except Exception as e: print("Channel error:", e)

def log_trade(pair, direction, amount, conf, result, profit):
    today = datetime.now(LAGOS_TZ).strftime("%Y-%m-%d")
    data = load_json(DATA_FILE, {})
    if today not in data: data[today] = {"trades": [], "wins":0, "losses":0, "profit":0, "total":0}
    trade = {"time": datetime.now(LAGOS_TZ).strftime("%H:%M"), "pair": pair, "dir": direction, "amount": amount, "conf": conf, "result": result, "profit": profit}
    data[today]["trades"].append(trade)
    data[today]["total"] += 1
    if result == "WIN": data[today]["wins"] += 1
    else: data[today]["losses"] += 1
    data[today]["profit"] += profit
    data[today]["trades"] = data[today]["trades"][-50:]
    save_json(DATA_FILE, data)

def get_summary(date_str=None):
    if not date_str: date_str = datetime.now(LAGOS_TZ).strftime("%Y-%m-%d")
    data = load_json(DATA_FILE, {})
    if date_str not in data: return f"📊 DAILY SUMMARY - {date_str}\nNo trades yet"
    d = data[date_str]
    winrate = (d['wins']/d['total']*100) if d['total']>0 else 0
    msg = f"📊 DAILY SUMMARY - {date_str}\n━━━━━━━━━━━━━━━━━━\n💼 Total Trades: {d['total']}\n✅ Wins: {d['wins']}\n❌ Losses: {d['losses']}\n📈 Win Rate: {winrate:.1f}%\n💰 Profit: ${d['profit']:+.0f}\n\n📝 Last Trades:\n"
    for t in d['trades'][-10:]:
        icon = "✅" if t['result']=="WIN" else "❌"
        msg += f"{icon} {t['time']} {t['pair']} {t['dir']} ${t['amount']} {t['conf']}% {t['result']} {t['profit']:+.0f}\n"
    msg += f"━━━━━━━━━━━━━━━━━━\nNext: ${AMOUNTS[current_level]} Lvl {current_level+1}"
    return msg

def get_channel_summary(date_str=None):
    if not date_str: date_str = datetime.now(LAGOS_TZ).strftime("%Y-%m-%d")
    data = load_json(DATA_FILE, {})
    if date_str not in data: return f"👑 KEVIN TRAILBLAZE 👑\n📊 DAILY SUMMARY - {date_str}\nNo trades yet"
    d = data[date_str]
    winrate = (d['wins']/d['total']*100) if d['total']>0 else 0
    return f"👑 KEVIN TRAILBLAZE 👑\n📊 DAILY SUMMARY - {date_str}\n━━━━━━━━━━━━━━━━━━\n💼 Total: {d['total']} | ✅ {d['wins']} | ❌ {d['losses']}\n📈 Win Rate: {winrate:.1f}%\n💰 Profit: ${d['profit']:+.0f}\n━━━━━━━━━━━━━━━━━━\n🔥 SIMPLE RELIABLE V20.3 🔥"

def analyze_pair(pair):
    global last_reason
    try:
        candles = Iq.get_candles(pair, 60, 100, time.time())
        if not candles or len(candles) < 60: return None
        ema20 = get_ema(candles, 20)
        ema50 = get_ema(candles, 50)
        rsi = get_rsi(candles, 14)
        vol = get_volatility(candles, 10)
        close = candles[-1][2]
        open_ = candles[-1][1]
        last_green = close > open_
        last_red = close < open_
        if ema20 is None or ema50 is None:
            last_reason = f"{pair}: Not enough data"
            return None
        if vol < 0.15:
            last_reason = f"{pair}: FLAT SKIP Vol {vol:.3f}"
            return None
        gap = abs(ema20 - ema50)
        if gap < 0.2:
            last_reason = f"{pair}: Weak gap SKIP {gap:.3f} EMA20 {ema20:.5f} EMA50 {ema50:.5f} RSI {rsi:.1f}"
            return None
        if close > ema20 > ema50:
            dist = abs(close - ema20)
            if dist < 0.6 and 45 <= rsi <= 68 and last_green:
                conf = 78
                if gap > 0.8: conf += 10
                if 50 <= rsi <= 62: conf += 8
                if dist < 0.3: conf += 6
                conf = min(conf, 95)
                if conf >= 75: return {"pair": pair, "dir": "call", "conf": conf, "ema20": ema20, "ema50": ema50, "rsi": rsi, "dist": dist}
        elif close < ema20 < ema50:
            dist = abs(close - ema20)
            if dist < 0.6 and 32 <= rsi <= 55 and last_red:
                conf = 78
                if gap > 0.8: conf += 10
                if 38 <= rsi <= 50: conf += 8
                if dist < 0.3: conf += 6
                conf = min(conf, 95)
                if conf >= 75: return {"pair": pair, "dir": "put", "conf": conf, "ema20": ema20, "ema50": ema50, "rsi": rsi, "dist": dist}
        last_reason = f"{pair}: WAIT EMA20 {ema20:.5f} EMA50 {ema50:.5f} RSI {rsi:.1f}"
    except Exception as e: last_reason = f"{pair}: Error {e}"
    return None

def do_trade(is_manual=False):
    global current_level, DAILY_LOSS, NEXT_SCAN_AT, last_reason
    if is_paused:
        if is_manual: send_private("⏸️ Bot paused - /resume")
        return
    if DAILY_LOSS <= DAILY_STOP_LOSS:
        send_private(f"🛑 DAILY STOP ${DAILY_STOP_LOSS} reached - /reset")
        return
    random.shuffle(PAIRS)
    signal = None
    for pair in PAIRS:
        signal = analyze_pair(pair)
        if signal: break
    if not signal:
        NEXT_SCAN_AT = datetime.now() + timedelta(seconds=SCAN_INTERVAL)
        if is_manual: send_private(f"⏭️ No SIMPLE signal now\nLast: {last_reason}\nNext 01:00 - Good, avoiding bad trades")
        return
    amount = AMOUNTS[current_level]
    pair = signal['pair']
    direction = signal['dir']
    conf = signal['conf']
    ema20 = signal['ema20']
    rsi = signal['rsi']
    dist = signal['dist']
    trend_text = f"EMA20 {ema20:.5f} > EMA50 Pullback {dist:.2f} RSI {rsi:.1f}"
    check, trade_id = Iq.buy(amount, pair, direction, EXPIRY)
    if not check:
        send_private(f"⚠️ Buy FAILED {pair} {direction.upper()} ${amount}\nReason: {trade_id}\nSkip channel")
        NEXT_SCAN_AT = datetime.now() + timedelta(seconds=20)
        return
    send_private(f"✅ SIMPLE {conf}% 💯\n💯 {pair} {direction.upper()} {conf}% | ${amount} Lvl {current_level+1}\n{trend_text}\n✅ TRADE PLACED")
    if direction == "call":
        ch_msg = f"👑 KEVIN TRAILBLAZE 👑\n🟢 CALL UP - {pair} 🟢\n━━━━━━━━━━━━━━━━━━\n💰 Pair: {pair}\n⏰ Expiry: {EXPIRY} MIN\n🎯 Confidence: {conf}%\n💵 Amount: ${amount}\n📊 {trend_text}\n━━━━━━━━━━━━━━━━━━\n🔥 SIMPLE RELIABLE V20.3"
    else:
        ch_msg = f"👑 KEVIN TRAILBLAZE 👑\n🔴 PUT DOWN - {pair} 🔴\n━━━━━━━━━━━━━━━━━━\n💰 Pair: {pair}\n⏰ Expiry: {EXPIRY} MIN\n🎯 Confidence: {conf}%\n💵 Amount: ${amount}\n📊 {trend_text}\n━━━━━━━━━━━━━━━━━━\n🔥 SIMPLE RELIABLE V20.3"
    send_channel(ch_msg)
    time.sleep(125)
    result = Iq.check_win_v3(trade_id)
    if result == True or (isinstance(result, (int,float)) and result>0):
        profit = result if isinstance(result, (int,float)) and result>0 else amount * 0.85
        if profit < 1: profit = amount * 0.85
        send_private(f"💰 WIN +${profit:.2f} {conf}% Bal ${Iq.get_balance():.2f}")
        send_channel(f"👑 KEVIN TRAILBLAZE 👑\n💰 WIN +${profit:.2f} {pair} {conf}% ✅\n━━━━━━━━━━━━━━━━━━\n🔥 SIMPLE RELIABLE")
        log_trade(pair, direction.upper(), amount, conf, "WIN", profit)
        current_level = 0
    else:
        loss = -amount
        send_private(f"📉 LOSS -${amount} Bal ${Iq.get_balance():.2f} Daily {DAILY_LOSS+loss}")
        send_channel(f"👑 KEVIN TRAILBLAZE 👑\n📉 LOSS -${amount} {pair} {conf}%\n━━━━━━━━━━━━━━━━━━\n🔥 SIMPLE RELIABLE")
        log_trade(pair, direction.upper(), amount, conf, "LOSS", loss)
        DAILY_LOSS += loss
        current_level = min(current_level+1, len(AMOUNTS)-1)
    save_json(STATE_FILE, {"level": current_level, "daily_loss": DAILY_LOSS})
    NEXT_SCAN_AT = datetime.now() + timedelta(seconds=SCAN_INTERVAL)

def handle_updates():
    last_update = 0
    while True:
        try:
            updates = loop.run_until_complete(bot.get_updates(offset=last_update+1, timeout=10))
            for u in updates:
                last_update = u.update_id
                if not u.message: continue
                txt = u.message.text.strip()
                chat = u.message.chat.id
                if chat!= PRIVATE_CHAT_ID: continue
                global current_level, DAILY_LOSS, is_paused, NEXT_SCAN_AT
                if txt == "/start":
                    bal = Iq.get_balance()
                    send_private(f"🤖 V20.3 GOLD STYLE + 60s ✅\n👑 KEVIN TRAILBLAZE 👑\nPairs: {'-'.join(PAIRS)}\nBal ${bal:.2f}\nNext ${AMOUNTS[current_level]} Lvl {current_level+1}\nNext in 01:00\n\n/summary /yesterday /balance /reset /scan /pause /resume")
                elif txt == "/scan": do_trade(is_manual=True)
                elif txt in ["/summary","/today"]: send_private(get_summary())
                elif txt == "/yesterday":
                    yest = (datetime.now(LAGOS_TZ)-timedelta(days=1)).strftime("%Y-%m-%d")
                    send_private(get_summary(yest))
                elif txt == "/balance": send_private(f"💰 Balance: ${Iq.get_balance():.2f}\n{get_summary()}")
                elif txt == "/reset":
                    current_level=0; DAILY_LOSS=0; save_json(STATE_FILE, {"level":0,"daily_loss":0}); send_private("✅ Reset done")
                elif txt == "/pause": is_paused=True; send_private("⏸️ Paused")
                elif txt == "/resume": is_paused=False; send_private("▶️ Resumed")
        except Exception as e: print("Update error", e); time.sleep(5)

def auto_reporter():
    while True:
        try:
            now = datetime.now(LAGOS_TZ)
            if now.hour == 23 and now.minute == 59:
                send_private(f"🌙 END OF DAY AUTO SUMMARY\n{get_summary()}")
                send_channel(get_channel_summary())
                time.sleep(70)
            if now.hour == 0 and now.minute == 0:
                global DAILY_LOSS; DAILY_LOSS = 0; save_json(STATE_FILE, {"level": current_level, "daily_loss": 0}); time.sleep(70)
        except: pass
        time.sleep(60)

if __name__ == "__main__":
    state = load_json(STATE_FILE, {"level":0,"daily_loss":0})
    current_level = state.get("level",0)
    DAILY_LOSS = state.get("daily_loss",0)
    threading.Thread(target=handle_updates, daemon=True).start()
    threading.Thread(target=auto_reporter, daemon=True).start()
    bal = Iq.get_balance()
    send_private(f"🤖 V20.3 ONLINE - GOLD STYLE 60s ✅\n👑 KEVIN TRAILBLAZE 👑\nBal ${bal:.2f} Next ${AMOUNTS[current_level]}")
    print(f"🤖 V20.3 ONLINE - Bal ${bal:.2f}")
    while True:
        if datetime.now() >= NEXT_SCAN_AT and not is_paused: do_trade()
        time.sleep(5)
