import os, time, threading, random, datetime, requests
from flask import Flask
import telebot

print("=== KEVIN BOT V14 FINAL FULL CODE ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

if not TOKEN:
    print("❌ MISSING TELEGRAM_BOT_TOKEN", flush=True)
if not EMAIL:
    print("❌ MISSING IQ_EMAIL", flush=True)

# === SETTINGS ===
BASE_AMOUNT = 10
MAX_MARTINGALE = 3
current_amount = BASE_AMOUNT
martingale_level = 0

OWNER_ID = None
Iq = None
SCANNING = True
LAST_SIGNAL = 0
RESUME_AT = time.time()

WEEKEND_PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "USDJPY-OTC", "AUDUSD-OTC"]
WEEKDAY_PAIRS = ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "XAUUSD-OTC"]

def get_pairs():
    wd = datetime.datetime.now().weekday()
    return WEEKEND_PAIRS if wd >= 5 else WEEKDAY_PAIRS

# === WEBHOOK DELETE - FIX FOR QUIET BOT ===
def delete_webhook():
    try:
        b = telebot.TeleBot(TOKEN)
        b.remove_webhook()
        print("✅ WEBHOOK DELETED (bot)", flush=True)
    except Exception as e:
        print(f"Webhook bot delete err {e}", flush=True)
    try:
        r = requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
        print(f"✅ WEBHOOK DELETED (api) {r.text[:100]}", flush=True)
    except Exception as e:
        print(f"Webhook api delete err {e}", flush=True)

# === INDICATORS - RSI 30-70 ===
def get_rsi(candles, period=14):
    try:
        closes = [c['close'] for c in candles]
        gains = []; losses = []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i-1]
            gains.append(max(d, 0)); losses.append(max(-d, 0))
        if len(gains) < period: return 50
        ag = sum(gains[-period:]) / period
        al = sum(losses[-period:]) / period
        if al == 0: return 70
        rs = ag / al
        return 100 - (100 / (1 + rs))
    except:
        return 50

def get_ema(candles, period):
    try:
        closes = [c['close'] for c in candles]
        ema = closes[0]
        k = 2 / (period + 1)
        for price in closes[1:]:
            ema = price * k + ema * (1 - k)
        return ema
    except:
        return 0

# === IQ CONNECT - WITH AUTO RECONNECT ===
def iq_connect():
    global Iq
    try:
        from iqoptionapi.stable_api import IQ_Option
        if Iq:
            try:
                Iq.close()
            except:
                pass
            Iq = None
            time.sleep(3)
        print(f"🔌 Connecting IQ {EMAIL}...", flush=True)
        Iq = IQ_Option(EMAIL, PASS)
        check, reason = Iq.connect()
        print(f"IQ CONNECT result {check} {reason}", flush=True)
        if check:
            time.sleep(4) # Wait websocket
            try:
                Iq.change_balance("PRACTICE")
            except:
                pass
            try:
                bal = Iq.get_balance()
                print(f"✅ IQ READY BAL {bal}", flush=True)
            except Exception as e:
                print(f"BAL ERR {e}", flush=True)
            return True
        else:
            print("❌ IQ LOGIN FAILED - wrong email/pass", flush=True)
            return False
    except Exception as e:
        print(f"❌ IQ CONNECT EXCEPTION {e}", flush=True)
        return False

# === SAFE CANDLES - FIXES YOUR RED ERROR ===
def get_candles_safe(pair):
    global Iq
    for attempt in range(5):
        try:
            if Iq is None:
                print(f"get_candles_safe {pair} Iq is None -> connecting", flush=True)
                if not iq_connect():
                    time.sleep(3)
                    continue
            candles = Iq.get_candles(pair, 60, 50, time.time())
            if candles and len(candles) >= 25:
                return candles
            else:
                raise Exception(f"Empty candles len {len(candles) if candles else 0}")
        except Exception as e:
            err = str(e).lower()
            print(f"⚠️ get_candles {pair} attempt {attempt+1}/5 err: {e}", flush=True)
            if "need reconnect" in err or "empty" in err or "no candle" in err:
                print("🔄 Reconnecting IQ...", flush=True)
                iq_connect()
            time.sleep(2)
    print(f"❌ FAILED get_candles {pair} after 5 attempts", flush=True)
    return None

def analyze(pair):
    candles = get_candles_safe(pair)
    if not candles:
        return None, "No candles"
    try:
        ema7 = get_ema(candles[-15:], 7)
        ema21 = get_ema(candles, 21)
        rsi = get_rsi(candles, 14)
        close = candles[-1]['close']

        # RSI 30-70 STRATEGY + EMA FILTER
        if close > ema7 > ema21 and 55 < rsi < 75:
            return "call", f"UP EMA7 {round(ema7,5)} > EMA21 {round(ema21,5)} RSI {round(rsi,1)} CLOSE {round(close,5)}"
        elif close < ema7 < ema21 and 25 < rsi < 45:
            return "put", f"DOWN EMA7 {round(ema7,5)} < EMA21 {round(ema21,5)} RSI {round(rsi,1)} CLOSE {round(close,5)}"
        else:
            return None, f"SKIP RSI {round(rsi,1)} EMA7 {round(ema7,5)}"
    except Exception as e:
        return None, f"Analyze err {e}"

# === TELEGRAM BOT ===
delete_webhook()
bot = telebot.TeleBot(TOKEN, threaded=False)

@app.route('/')
def home():
    try:
        b = Iq.get_balance() if Iq else "NO IQ YET"
        b = round(b, 2) if isinstance(b, (int, float)) else b
    except Exception as e:
        b = f"ERR {e}"
    return f"V14 FINAL - BAL {b} - AMT {current_amount} LVL {martingale_level} - SCAN {SCANNING} - OWNER {OWNER_ID}"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook_route():
    # If Render still sends webhook, delete it
    delete_webhook()
    return "WEBHOOK DELETED USE POLLING", 200

@bot.message_handler(commands=['start'])
def cmd_start(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, current_amount, martingale_level
    OWNER_ID = m.chat.id
    RESUME_AT = time.time()
    LAST_SIGNAL = 0
    current_amount = BASE_AMOUNT
    martingale_level = 0
    delete_webhook()
    if not iq_connect():
        bot.send_message(m.chat.id, "❌ IQ login failed. Check IQ_EMAIL / IQ_PASSWORD in Render.\nUse /setaccount email pass")
        return
    try:
        bal = round(Iq.get_balance(), 2)
    except:
        bal = "?"
    bot.send_message(m.chat.id, f"🤖 KEVIN V14 FINAL\n✅ Webhook deleted\n✅ Reconnect fixed\n✅ RSI 30-70 + EMA\nBal ${bal}\nBase ${BASE_AMOUNT} Martingale 3 steps $10->$20->$40\nAuto trades every 2-3 mins\n\nCommands:\n/resume - resume auto\n/pause - pause auto\n/balance - check balance\n/scan - force scan now\n/delete_webhook - fix quiet bot\n/setaccount email pass - change IQ account")

@bot.message_handler(commands=['resume','fix','run'])
def cmd_resume(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING
    OWNER_ID = m.chat.id
    SCANNING = True
    RESUME_AT = time.time()
    LAST_SIGNAL = 0
    delete_webhook()
    if not Iq:
        iq_connect()
    bot.send_message(m.chat.id, f"▶️ RESUMED\nAmt ${current_amount} Lvl {martingale_level}/{MAX_MARTINGALE}\nScanning every 2-3 mins")

@bot.message_handler(commands=['pause','stop'])
def cmd_pause(m):
    global SCANNING
    SCANNING = False
    bot.send_message(m.chat.id, "⏸️ Paused auto trading. Send /resume to start")

@bot.message_handler(commands=['delete_webhook','delwebhook','fixwebhook'])
def cmd_delhook(m):
    global OWNER_ID
    OWNER_ID = m.chat.id
    bot.send_message(m.chat.id, "🔄 Deleting webhook...")
    delete_webhook()
    bot.send_message(m.chat.id, "✅ Webhook deleted! Bot is now polling.\nSend /resume")

@bot.message_handler(commands=['balance','status','pairs','account','bal'])
def cmd_status(m):
    global OWNER_ID
    OWNER_ID = m.chat.id
    if not Iq:
        iq_connect()
    try:
        b = round(Iq.get_balance(), 2) if Iq else "NO IQ"
    except:
        b = "?"
    bot.send_message(m.chat.id, f"💳 BAL ${b}\n💰 Amt ${current_amount} Lvl {martingale_level}/{MAX_MARTINGALE}\n📧 {EMAIL}\n📊 Pairs: {', '.join(get_pairs())}\n🔄 Auto: {'ON' if SCANNING else 'OFF'}")

@bot.message_handler(commands=['scan','now'])
def cmd_scan(m):
    global OWNER_ID
    OWNER_ID = m.chat.id
    bot.send_message(m.chat.id, "🔍 Force scanning now...")
    threading.Thread(target=do_trade, daemon=True).start()

@bot.message_handler(commands=['setaccount'])
def cmd_setaccount(m):
    global EMAIL, PASS, Iq
    OWNER_ID = m.chat.id
    parts = m.text.split()
    if len(parts) < 3:
        bot.send_message(m.chat.id, "Usage:\n/setaccount your_email your_password\nExample:\n/setaccount kevin@gmail.com MyPass123")
        return
    EMAIL = parts[1]
    PASS = parts[2]
    bot.send_message(m.chat.id, f"🔄 Switching IQ to {EMAIL}...")
    if iq_connect():
        try:
            bal = Iq.get_balance()
            bot.send_message(m.chat.id, f"✅ Switched!\n{EMAIL}\nBal ${bal}\n⚠️ To make permanent, update IQ_EMAIL & IQ_PASSWORD in Render Dashboard -> Environment")
        except Exception as e:
            bot.send_message(m.chat.id, f"✅ Connected but bal err {e}")
    else:
        bot.send_message(m.chat.id, "❌ Login failed - wrong email/password or 2FA enabled. Disable 2FA on IQ Option")

# === MAIN TRADING LOGIC ===
def do_trade():
    global LAST_SIGNAL, current_amount, martingale_level
    if not OWNER_ID:
        print("do_trade no OWNER_ID yet", flush=True)
        return
    if not Iq:
        if not iq_connect():
            if OWNER_ID:
                try:
                    bot.send_message(OWNER_ID, "❌ IQ not connected, retry in 60s")
                except:
                    pass
            LAST_SIGNAL = time.time()
            return

    PAIRS = get_pairs()
    random.shuffle(PAIRS)

    try:
        bal = round(Iq.get_balance(), 2)
    except:
        bal = "?"

    print(f"🔍 SCANNING {PAIRS} BAL {bal} AMT {current_amount}", flush=True)
    try:
        bot.send_message(OWNER_ID, f"🔍 Scanning {len(PAIRS)} pairs...\n{', '.join(PAIRS)}\nBal ${bal} Amt ${current_amount} Lvl {martingale_level}")
    except:
        pass

    for pair in PAIRS:
        direction, reason = analyze(pair)
        print(f"ANALYZE {pair} -> {direction} {reason}", flush=True)
        if direction:
            try:
                print(f"TRY BUY {pair} {direction} {current_amount}", flush=True)
                bot.send_message(OWNER_ID, f"📊 SIGNAL FOUND\n{pair} {direction.upper()}\nAmt ${current_amount} Lvl {martingale_level}\n{reason}\nBuying...")

                status, trade_id = Iq.buy(current_amount, pair, direction, 1)

                if not status:
                    print(f"BUY FAILED {pair} {status} {trade_id}", flush=True)
                    bot.send_message(OWNER_ID, f"❌ Buy failed {pair} {trade_id}")
                    continue

                bot.send_message(OWNER_ID, f"✅ BOUGHT\n{pair} {direction.upper()} ${current_amount}\nID {trade_id}\nWait 65s...")
                time.sleep(65)

                try:
                    profit = Iq.check_win_v3(trade_id)
                except Exception as e:
                    print(f"check_win err {e}", flush=True)
                    profit = 0

                try:
                    bal = Iq.get_balance()
                except:
                    bal = "?"

                LAST_SIGNAL = time.time()

                if profit and profit > 0:
                    msg = f"💰 WIN +${round(profit,2)}\n{pair} {direction}\n{reason}\nBal ${bal}\n🔄 Reset to ${BASE_AMOUNT}"
                    print(msg, flush=True)
                    bot.send_message(OWNER_ID, msg)
                    current_amount = BASE_AMOUNT
                    martingale_level = 0
                else:
                    martingale_level += 1
                    if martingale_level >= MAX_MARTINGALE:
                        msg = f"📉 LOSS -${current_amount}\n{pair}\n{reason}\n⚠️ 3 losses -> RESET to ${BASE_AMOUNT}\nBal ${bal}"
                        print(msg, flush=True)
                        bot.send_message(OWNER_ID, msg)
                        current_amount = BASE_AMOUNT
                        martingale_level = 0
                    else:
                        prev = current_amount
                        current_amount = BASE_AMOUNT * (2 ** martingale_level)
                        msg = f"📉 LOSS -${prev}\n{pair}\n{reason}\n📈 Next ${current_amount} Lvl {martingale_level}\nBal ${bal}"
                        print(msg, flush=True)
                        bot.send_message(OWNER_ID, msg)
                return

            except Exception as e:
                print(f"BUY EXCEPTION {pair} {e}", flush=True)
                iq_connect()
                continue

    LAST_SIGNAL = time.time()
    try:
        bal = round(Iq.get_balance(), 2) if Iq else "?"
    except:
        bal = "?"
    print(f"No signal, sleep 2 mins BAL {bal}", flush=True)
    try:
        bot.send_message(OWNER_ID, f"⏭️ No strong trend found\nRSI 30-70 filter skip\nAmt ${current_amount} Lvl {martingale_level} Bal ${bal}\nNext scan in 2-3 mins")
    except:
        pass

def scanner_loop():
    print("🔄 Scanner loop started", flush=True)
    while True:
        try:
            time.sleep(10)
            if not OWNER_ID or not SCANNING:
                continue
            # First run after 2 mins, then every 3 mins
            wait_time = 120 if LAST_SIGNAL == 0 else 180
            if time.time() - (RESUME_AT if LAST_SIGNAL == 0 else LAST_SIGNAL) < wait_time:
                continue
            do_trade()
        except Exception as e:
            print(f"❌ SCANNER LOOP ERR {e}", flush=True)
            time.sleep(5)

def polling_loop():
    print("🔄 Polling loop started", flush=True)
    while True:
        try:
            delete_webhook()
            print("▶️ Starting infinity_polling...", flush=True)
            bot.infinity_polling(none_stop=True, timeout=90, long_polling_timeout=90)
        except Exception as e:
            print(f"❌ Polling died {e}, restart in 5s", flush=True)
            time.sleep(5)

# START THREADS
threading.Thread(target=scanner_loop, daemon=True).start()
threading.Thread(target=polling_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Flask starting on port {port}", flush=True)
    app.run(host="0.0.0.0", port=port)
