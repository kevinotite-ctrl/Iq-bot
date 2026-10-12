import os, time, threading, random
from flask import Flask
import telebot

print("=== KEVIN TRAILBLAZER BOT V10 AUTO ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

print(f"TOKEN exists: {bool(TOKEN)}", flush=True)

BASE_AMOUNT = 10
current_amount = BASE_AMOUNT
martingale_level = 0
OWNER_ID = None
Iq = None
SCANNING = True
CURRENT_BALANCE_MODE = "PRACTICE"

try:
    try:
        from iqoptionapi.stable_api import IQ_Option
    except:
        from iqoptionapi.api import IQ_Option
    Iq = IQ_Option(EMAIL, PASS)
    check, reason = Iq.connect()
    print(f"IQ CONNECT: {check} | {reason}", flush=True)
    if check:
        Iq.change_balance(CURRENT_BALANCE_MODE)
        print(f"BAL: ${Iq.get_balance()}", flush=True)
except Exception as e:
    print(f"IQ ERROR: {e}", flush=True)

@app.route('/')
def home():
    bal = Iq.get_balance() if Iq else "?"
    return f"V10 AUTO LIVE - MODE:{CURRENT_BALANCE_MODE} BAL:${bal} AMT:${current_amount} LVL:{martingale_level} SCAN:{SCANNING}"

def get_rsi(prices, period=14):
    if len(prices) < period+1: return 50
    gains = [max(prices[i]-prices[i-1],0) for i in range(1,len(prices))]
    losses = [max(prices[i-1]-prices[i],0) for i in range(1,len(prices))]
    ag = sum(gains[-period:])/period
    al = sum(losses[-period:])/period
    if al == 0: return 100
    return 100-(100/(1+(ag/al)))

def get_ema(prices, period):
    if len(prices) < period: return prices[-1]
    k = 2/(period+1)
    ema = sum(prices[:period])/period
    for p in prices[period:]:
        ema = p*k + ema*(1-k)
    return ema

def get_confidence(rsi, ema9, ema21):
    rsi_strength = abs(rsi - 50)
    ema_gap = abs(ema9 - ema21) * 10000
    base = 60 + (rsi_strength * 0.6) + min(ema_gap*5, 15)
    return int(min(95, max(58, base + random.randint(-3,3))))

bot = telebot.TeleBot(TOKEN)
print("Deleting webhook...", flush=True)
try:
    bot.delete_webhook()
    bot.remove_webhook()
    print("Webhook deleted! Polling active", flush=True)
    time.sleep(2)
except Exception as e:
    print(f"Webhook error: {e}", flush=True)

PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "EURUSD", "GBPUSD"]

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID
    OWNER_ID = m.chat.id
    print(f"/start from {OWNER_ID}", flush=True)
    bal = Iq.get_balance() if Iq else "?"
    bot.send_message(m.chat.id, f"🔥 KEVIN TRAILBLAZER V10 AUTO ACTIVE 🔥\n\nID: {OWNER_ID}\nMode: {CURRENT_BALANCE_MODE}\nBal: ${bal}\nBase: ${BASE_AMOUNT}\nCurrent: ${current_amount}\n\n🤖 AUTO TRADING: ON\n- Alert 10s before\n- Auto places trade\n- Sends WIN/LOSS + Confidence%\n- 2 mins loop\n\n/pause - Stop\n/resume - Resume\n/amount 5 - Set $5\n/balance - Status")

@bot.message_handler(commands=['pause','stop'])
def pause_scan(m):
    global SCANNING
    SCANNING = False
    bot.send_message(m.chat.id, "⏸️ PAUSED")

@bot.message_handler(commands=['resume','startauto'])
def resume_scan(m):
    global SCANNING
    SCANNING = True
    bot.send_message(m.chat.id, "▶️ RESUMED - Scanning...")

@bot.message_handler(commands=['amount'])
def set_amount(m):
    global BASE_AMOUNT, current_amount, martingale_level
    try:
        BASE_AMOUNT = int(m.text.split()[1])
        current_amount = BASE_AMOUNT
        martingale_level = 0
        bot.send_message(m.chat.id, f"✅ Base ${BASE_AMOUNT}")
    except:
        bot.send_message(m.chat.id, "Use: /amount 20")

@bot.message_handler(commands=['balance','status'])
def check_bal(m):
    bal = Iq.get_balance() if Iq else "?"
    bot.send_message(m.chat.id, f"📊 Bal:${bal} Amt:${current_amount} Lvl:{martingale_level} Scan:{SCANNING}")

def execute_trade(pair, direction, rsi, ema9, ema21):
    global current_amount, martingale_level
    conf = get_confidence(rsi, ema9, ema21)
    bot.send_message(OWNER_ID, f"‼️signal alert incoming ‼️\nGet ready‼️‼️💯\n\nPair: {pair}\nDir: {direction.upper()}\nConf: {conf}%")
    time.sleep(10)
    bot.send_message(OWNER_ID, f"📈 AUTO PLACING TRADE\n{pair} {direction.upper()}\nAmt: ${current_amount} Lvl:{martingale_level}\nRSI: {rsi:.1f} Conf: {conf}% 🔥")
    try:
        status, tid = Iq.buy(current_amount, pair, direction, 1)
        if not status:
            bot.send_message(OWNER_ID, f"❌ Failed: {tid}")
            return False
        bot.send_message(OWNER_ID, f"✅ PLACED {pair} {direction.upper()} ${current_amount}\nID:{tid}\nConf:{conf}%\nWaiting 65s...")
        time.sleep(65)
        profit = Iq.check_win_v3(tid)
        if profit > 0:
            bot.send_message(OWNER_ID, f"🥇 WIN 🥇\n{pair} {direction.upper()}\nProfit: +${round(profit,2)}\nConf: {conf}% ✅\nBal: ${round(Iq.get_balance(),2)}")
            time.sleep(1)
            bot.send_message(OWNER_ID, f"🤑 Profit secured! Reset to ${BASE_AMOUNT}. Next in 2 mins...")
            current_amount = BASE_AMOUNT
            martingale_level = 0
        else:
            bot.send_message(OWNER_ID, f"❌ LOSS\n{pair} {direction.upper()}\nLoss: -${current_amount}\nConf:{conf}%\nBal:${round(Iq.get_balance(),2)}")
            time.sleep(1)
            martingale_level += 1
            current_amount = current_amount * 2
            if current_amount > 160:
                bot.send_message(OWNER_ID, f"😮‍💨 Cap $160. Reset to ${BASE_AMOUNT}. Next 2 mins...")
                current_amount = BASE_AMOUNT
                martingale_level = 0
            else:
                bot.send_message(OWNER_ID, f"😮‍💨 Next: ${current_amount} Lvl {martingale_level}. Next 2 mins...")
        return True
    except Exception as e:
        bot.send_message(OWNER_ID, f"Error: {e}")
        return False

def scanner():
    print("Scanner started...", flush=True)
    while True:
        if not OWNER_ID or not Iq or not SCANNING:
            time.sleep(5)
            continue
        for pair in PAIRS:
            if not SCANNING: break
            try:
                candles = Iq.get_candles(pair, 60, 30, time.time())
                if not candles: continue
                prices = [c['close'] for c in candles]
                rsi = get_rsi(prices)
                ema9 = get_ema(prices, 9)
                ema21 = get_ema(prices, 21)
                signal = None
                if rsi < 32 and ema9 > ema21: signal = "call"
                elif rsi > 68 and ema9 < ema21: signal = "put"
                if signal:
                    print(f"SIGNAL {pair} {signal} RSI {rsi:.1f}", flush=True)
                    execute_trade(pair, signal, rsi, ema9, ema21)
                    time.sleep(120)
                    break
            except Exception as e:
                print(f"Scan err {pair}: {e}", flush=True)
        time.sleep(5)

def run_bot():
    print("Starting polling...", flush=True)
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"Polling error: {e} - retry in 5s", flush=True)
            time.sleep(5)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=run_bot, daemon=True).start()
print("All threads started", flush=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
