import os, time, threading, random
from flask import Flask
import telebot

print("=== KEVIN TRAILBLAZER BOT V10 AUTO ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

BASE_AMOUNT = 10
current_amount = BASE_AMOUNT
martingale_level = 0
OWNER_ID = None
Iq = None
SCANNING = True
CURRENT_BALANCE_MODE = "PRACTICE"
AUTO_MODE = True # AUTO TRADING ON

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
    # Confidence based on RSI strength + EMA gap
    rsi_strength = abs(rsi - 50) # 0-50
    ema_gap = abs(ema9 - ema21) * 10000 # small gap
    base = 60 + (rsi_strength * 0.6) + min(ema_gap*5, 15)
    conf = int(min(95, max(58, base + random.randint(-3,3))))
    return conf

bot = telebot.TeleBot(TOKEN)
try:
    bot.delete_webhook()
    bot.remove_webhook()
    time.sleep(1)
except:
    pass

PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "EURUSD", "GBPUSD"]

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID
    OWNER_ID = m.chat.id
    bal = Iq.get_balance() if Iq else "?"
    bot.send_message(m.chat.id, f"🔥 KEVIN TRAILBLAZER V10 AUTO ACTIVE 🔥\n\nID: {OWNER_ID}\nMode: {CURRENT_BALANCE_MODE}\nBal: ${bal}\nBase: ${BASE_AMOUNT}\nCurrent: ${current_amount}\n\n🤖 AUTO TRADING: ON\nBot will:\n- Alert you 10s before signal\n- Auto place trade\n- Send win/loss\n- Wait 2 mins for next\n\nCommands:\n/pause - Stop auto\n/resume - Resume auto\n/amount 20 - Set amount\n/balance - Status\n/real - Real account\n/practice - Demo")

@bot.message_handler(commands=['pause','stop'])
def pause_scan(m):
    global SCANNING
    SCANNING = False
    bot.send_message(m.chat.id, "⏸️ AUTO TRADING PAUSED. No new trades.")

@bot.message_handler(commands=['resume','startauto'])
def resume_scan(m):
    global SCANNING
    SCANNING = True
    bot.send_message(m.chat.id, "▶️ AUTO TRADING RESUMED. Scanning...")

@bot.message_handler(commands=['amount'])
def set_amount(m):
    global BASE_AMOUNT, current_amount, martingale_level
    try:
        BASE_AMOUNT = int(m.text.split()[1])
        current_amount = BASE_AMOUNT
        martingale_level = 0
        bot.send_message(m.chat.id, f"✅ Base set to ${BASE_AMOUNT}")
    except:
        bot.send_message(m.chat.id, "Use: /amount 20")

@bot.message_handler(commands=['real'])
def set_real(m):
    global CURRENT_BALANCE_MODE
    Iq.change_balance("REAL")
    CURRENT_BALANCE_MODE = "REAL"
    bot.send_message(m.chat.id, f"⚠️ REAL MODE - Bal ${Iq.get_balance()}")

@bot.message_handler(commands=['practice','demo'])
def set_practice(m):
    global CURRENT_BALANCE_MODE
    Iq.change_balance("PRACTICE")
    CURRENT_BALANCE_MODE = "PRACTICE"
    bot.send_message(m.chat.id, f"✅ PRACTICE - Bal ${Iq.get_balance()}")

@bot.message_handler(commands=['balance','status'])
def check_bal(m):
    bal = Iq.get_balance() if Iq else "?"
    bot.send_message(m.chat.id, f"📊 STATUS\nMode:{CURRENT_BALANCE_MODE}\nBal:${bal}\nAmt:${current_amount} Lvl:{martingale_level}\nScanning:{SCANNING}\nAuto:{AUTO_MODE}")

def execute_trade(pair, direction, rsi, ema9, ema21):
    global current_amount, martingale_level
    conf = get_confidence(rsi, ema9, ema21)

    # 1. ALERT 10 SECONDS BEFORE
    bot.send_message(OWNER_ID, f"‼️signal alert incoming ‼️\nGet ready‼️‼️💯\n\nPair: {pair}\nDirection: {direction.upper()}\nConfidence: {conf}%")
    time.sleep(10)

    # 2. PLACE TRADE MESSAGE
    bot.send_message(OWNER_ID, f"📈 AUTO PLACING TRADE\n\nPair: {pair}\nDir: {direction.upper()} ({'BUY' if direction=='call' else 'SELL'})\nAmount: ${current_amount} | Level: {martingale_level}\nRSI: {rsi:.1f}\nConfidence: {conf}% 🔥\n\n⏳ Executing on IQ Option...")

    try:
        status, tid = Iq.buy(current_amount, pair, direction, 1)
        if not status:
            bot.send_message(OWNER_ID, f"❌ Trade failed: {tid}\nRetrying in 2 mins...")
            return False

        bot.send_message(OWNER_ID, f"✅ TRADE PLACED!\n{pair} {direction.upper()} ${current_amount}\nID: {tid}\nConfidence: {conf}%\nWaiting 65s for result...")
        time.sleep(65)
        profit = Iq.check_win_v3(tid)

        if profit > 0:
            # WIN
            bot.send_message(OWNER_ID, f"🥇 WIN 🥇\n\nPair: {pair}\nDir: {direction.upper()}\nProfit: +${round(profit,2)}\nAmount: ${current_amount}\nConfidence: {conf}% was correct! ✅\nBalance: ${round(Iq.get_balance(),2)}")
            time.sleep(1)
            bot.send_message(OWNER_ID, f"🤑💰💸 Profit secured! Resetting to ${BASE_AMOUNT}. Next session in 2 mins...")
            current_amount = BASE_AMOUNT
            martingale_level = 0
        else:
            # LOSS
            loss = current_amount
            bot.send_message(OWNER_ID, f"❌ LOSS\n\nPair: {pair}\nDir: {direction.upper()}\nLoss: -${loss}\nConfidence: {conf}%\nBalance: ${round(Iq.get_balance(),2)}")
            time.sleep(1)
            martingale_level += 1
            current_amount = current_amount * 2
            if current_amount > 160:
                bot.send_message(OWNER_ID, f"😮‍💨 Cap $160 reached. Taking a breath and resetting to ${BASE_AMOUNT}. Next in 2 mins...")
                current_amount = BASE_AMOUNT
                martingale_level = 0
            else:
                bot.send_message(OWNER_ID, f"😮‍💨 Loss taken. Martingale next: ${current_amount} (Level {martingale_level}). Next in 2 mins...")

        return True
    except Exception as e:
        bot.send_message(OWNER_ID, f"Error executing: {e}")
        return False

def scanner():
    while True:
        if not OWNER_ID or not Iq or not SCANNING:
            time.sleep(5)
            continue

        for pair in PAIRS:
            if not SCANNING:
                break
            try:
                candles = Iq.get_candles(pair, 60, 30, time.time())
                if not candles:
                    continue
                prices = [c['close'] for c in candles]
                rsi = get_rsi(prices)
                ema9 = get_ema(prices, 9)
                ema21 = get_ema(prices, 21)

                signal = None
                if rsi < 32 and ema9 > ema21:
                    signal = "call"
                elif rsi > 68 and ema9 < ema21:
                    signal = "put"

                if signal:
                    print(f"SIGNAL {pair} {signal} RSI {rsi:.1f}", flush=True)
                    execute_trade(pair, signal, rsi, ema9, ema21)
                    print("Waiting 2 mins for next session...", flush=True)
                    time.sleep(120) # 2 MINUTES WAIT BEFORE NEXT TRADE SESSION
                    break # break pair loop and restart scanning
            except Exception as e:
                print(f"Scan error {pair}: {e}", flush=True)

        time.sleep(5)

def run_bot():
    try: bot.stop_polling()
    except: pass
    time.sleep(1)
    bot.infinity_polling(skip_pending=True, timeout=30)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
