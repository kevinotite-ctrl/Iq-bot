import telebot
import time
import threading
from iqoptionapi.stable_api import IQ_Option

# ===== PUT YOUR DETAILS HERE =====
BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
EMAIL = "PUT_YOUR_IQ_EMAIL_HERE"
PASSWORD = "PUT_YOUR_IQ_PASSWORD_HERE"
# ==================================

OWNER_ID = None
PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "EURUSD", "GBPUSD"]
base_amount = 5
current_amount = base_amount
martingale_level = 0
MAX_MARTINGALE = 3
SCANNING = True
Iq = None
account_type = "PRACTICE"

bot = telebot.TeleBot(BOT_TOKEN)

def get_rsi(prices, period=14):
    if len(prices) < period+1:
        return 50
    deltas = [prices[i]-prices[i-1] for i in range(1, len(prices))]
    gains = [d if d>0 else 0 for d in deltas]
    losses = [-d if d<0 else 0 for d in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_ema(prices, period):
    if not prices:
        return 0
    k = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = price * k + ema * (1 - k)
    return ema

def execute_trade(pair, signal, rsi, ema9, ema21):
    global current_amount, martingale_level, Iq
    try:
        gap = abs(ema9 - ema21) * 100000
        conf = min(95, 58 + abs(rsi-50)*0.6 + gap*2)
        fire = " 🔥" if conf > 71 else ""
        bot.send_message(OWNER_ID, f"📈 AUTO PLACING TRADE\n{pair} {signal.upper()}\nAmt: ${current_amount} Lvl:{martingale_level}\nRSI: {rsi:.1f} Conf: {conf:.0f}%{fire}")
        status, id = Iq.buy(current_amount, pair, signal, 1)
        if not status:
            bot.send_message(OWNER_ID, f"❌ Trade failed {pair}")
            return
        time.sleep(1.5)
        bot.send_message(OWNER_ID, f"✅ PLACED {pair} {signal.upper()} ${current_amount}\nID:{id}\nRSI:{rsi:.1f} Conf:{conf:.0f}%\nWaiting 65s...")
        time.sleep(65)
        try:
            result = Iq.check_win_v4(id)
            if result > 0:
                bot.send_message(OWNER_ID, f"🥇 WIN 🥇\n{pair} {signal.upper()}\nProfit: +${result:.2f}\nConf: {conf:.0f}% ✅\nBal: ${Iq.get_balance():.2f}")
                current_amount = base_amount
                martingale_level = 0
                bot.send_message(OWNER_ID, f"🤑 Reset to ${base_amount}. Next in 2 mins...")
            else:
                loss = result if result < 0 else -current_amount
                bot.send_message(OWNER_ID, f"❌ LOSS\n{pair} {signal.upper()}\nLoss: ${loss:.2f}\nConf: {conf:.0f}%\nBal: ${Iq.get_balance():.2f}")
                martingale_level += 1
                if martingale_level > MAX_MARTINGALE:
                    current_amount = base_amount
                    martingale_level = 0
                    bot.send_message(OWNER_ID, f"⚠️ Max martingale hit. Reset to ${base_amount}")
                else:
                    current_amount = round(current_amount * 2.2, 2)
                    bot.send_message(OWNER_ID, f"😮‍💨 Next: ${current_amount} Lvl {martingale_level}. Next 2 mins...")
        except Exception as e:
            bot.send_message(OWNER_ID, f"⏳ Result check error: {e}\nCheck IQ app manually. Balance: ${Iq.get_balance():.2f}")
            current_amount = base_amount
            martingale_level = 0
    except Exception as e:
        if OWNER_ID:
            bot.send_message(OWNER_ID, f"Trade error {pair}: {e}")

def scanner():
    print("Scanner started...", flush=True)
    while True:
        if not OWNER_ID or not Iq or not SCANNING:
            time.sleep(3)
            continue
        for pair in PAIRS:
            if not SCANNING:
                break
            try:
                candles = Iq.get_candles(pair, 60, 30, time.time())
                if not candles or len(candles) < 25:
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
                    time.sleep(120)
                    break
            except Exception as e:
                print(f"Scan err {pair}: {e}", flush=True)
        time.sleep(5)

@bot.message_handler(commands=['start'])
def start_cmd(m):
    global OWNER_ID
    OWNER_ID = m.chat.id
    bot.send_message(m.chat.id, f"✅ Bot activated!\nID: {OWNER_ID}\nAmt: ${base_amount}\nPairs: {', '.join(PAIRS)}\n\nCommands:\n/level - Show LIVE RSI levels\n/balance - Balance\n/pause - Pause bot\n/resume - Resume bot\n/amount - Set amount e.g /amount 5\n/real - Real account\n/practice - Demo account")

@bot.message_handler(commands=['level','rsi','levels'])
def show_levels(m):
    if not Iq:
        bot.send_message(m.chat.id, "❌ IQ not connected yet, wait 10 sec")
        return
    try:
        msg = "📊 LIVE LEVELS\n\n"
        for pair in PAIRS:
            candles = Iq.get_candles(pair, 60, 30, time.time())
            if not candles:
                msg += f"{pair}: No data\n\n"
                continue
            prices = [c['close'] for c in candles]
            rsi = get_rsi(prices)
            ema9 = get_ema(prices, 9)
            ema21 = get_ema(prices, 21)
            if rsi < 32:
                status = "🟢 OVERSOLD - CALL READY"
            elif rsi > 68:
                status = "🔴 OVERBOUGHT - PUT READY"
            elif rsi < 40:
                status = "🟡 Approaching CALL"
            elif rsi > 60:
                status = "🟡 Approaching PUT"
            else:
                status = "⚪ Neutral"
            trend = "UP 📈" if ema9 > ema21 else "DOWN 📉"
            msg += f"{pair}\nRSI: {rsi:.1f} | {status}\nEMA9: {ema9:.5f}\nEMA21: {ema21:.5f} {trend}\n\n"
        msg += f"Current: ${current_amount} Lvl:{martingale_level}\nScanning: {'ON ✅' if SCANNING else 'OFF ⏸️'}\nBal: ${Iq.get_balance():.2f} {account_type}"
        bot.send_message(m.chat.id, msg)
    except Exception as e:
        bot.send_message(m.chat.id, f"Error in /level: {e}")

@bot.message_handler(commands=['balance'])
def balance_cmd(m):
    try:
        bal = Iq.get_balance() if Iq else 0
        bot.send_message(m.chat.id, f"💰 Balance: ${bal:.2f}\nType: {account_type}\nAmt: ${current_amount} Lvl:{martingale_level}\nScanning: {SCANNING}\nPairs: {', '.join(PAIRS)}")
    except Exception as e:
        bot.send_message(m.chat.id, f"Error: {e}")

@bot.message_handler(commands=['pause'])
def pause_cmd(m):
    global SCANNING
    SCANNING = False
    bot.send_message(m.chat.id, "⏸️ Paused. No new trades.")

@bot.message_handler(commands=['resume'])
def resume_cmd(m):
    global SCANNING
    SCANNING = True
    bot.send_message(m.chat.id, "▶️ Resumed. Scanning...")

@bot.message_handler(commands=['amount'])
def amount_cmd(m):
    global base_amount, current_amount, martingale_level
    try:
        parts = m.text.split()
        new_amt = float(parts[1])
        base_amount = new_amt
        current_amount = new_amt
        martingale_level = 0
        bot.send_message(m.chat.id, f"✅ Base amount set to ${base_amount}")
    except:
        bot.send_message(m.chat.id, "Use: /amount 5")

@bot.message_handler(commands=['real','practice'])
def switch_acc(m):
    global account_type
    try:
        if not Iq:
            bot.send_message(m.chat.id, "IQ not connected")
            return
        if "real" in m.text:
            Iq.change_balance("REAL")
            account_type = "REAL"
        else:
            Iq.change_balance("PRACTICE")
            account_type = "PRACTICE"
        bot.send_message(m.chat.id, f"✅ Switched to {account_type} Bal: ${Iq.get_balance():.2f}")
    except Exception as e:
        bot.send_message(m.chat.id, f"Error: {e}")

def iq_connect():
    global Iq
    while True:
        try:
            print("Connecting IQ...", flush=True)
            Iq = IQ_Option(EMAIL, PASSWORD)
            check, reason = Iq.connect()
            if check:
                print(f"IQ Connected Bal {Iq.get_balance()}", flush=True)
                Iq.change_balance(account_type)
                if OWNER_ID:
                    try:
                        bot.send_message(OWNER_ID, f"✅ IQ Connected\nBal: ${Iq.get_balance():.2f} {account_type}")
                    except:
                        pass
            else:
                print(f"IQ Fail {reason}", flush=True)
                time.sleep(15)
        except Exception as e:
            print(f"IQ Connect err {e}", flush=True)
            time.sleep(15)
        time.sleep(30)

threading.Thread(target=iq_connect, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()

print("Bot polling started...", flush=True)
bot.infinity_polling(none_stop=True, timeout=60, long_polling_timeout=60)
