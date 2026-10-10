import os, time, threading
from flask import Flask
import telebot
from telebot import types

print("=== KEVIN TRAILBLAZER BOT V8 MARTINGALE ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

BASE_AMOUNT = 10
current_amount = BASE_AMOUNT
martingale_level = 0
OWNER_ID = None
Iq = None

# --- IQ CONNECT ---
try:
    from iqoptionapi.stable_api import IQ_Option
    Iq = IQ_Option(EMAIL, PASS)
    check, reason = Iq.connect()
    print(f"IQ CONNECT: {check} | {reason}", flush=True)
    if check:
        Iq.change_balance("PRACTICE") # change to REAL
        print(f"BAL: ${Iq.get_balance()}")
except Exception as e:
    print(f"IQ ERROR: {e}")

@app.route('/')
def home():
    bal = Iq.get_balance() if Iq else "NOT CONNECTED"
    return f"KEVIN TRAILBLAZER BOT LIVE - BAL: ${bal} | AMOUNT: ${current_amount} | LEVEL: {martingale_level}"

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

bot = telebot.TeleBot(TOKEN)
PAIRS = ["EURUSD-OTC", "EURUSD", "GBPUSD-OTC"]
pending_trades = {}

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, current_amount, martingale_level
    OWNER_ID = m.chat.id
    current_amount = BASE_AMOUNT
    martingale_level = 0
    bal = Iq.get_balance() if Iq else "?"
    bot.send_message(m.chat.id, f"🔥 KEVIN TRAILBLAZER BOT ACTIVE\nID: {OWNER_ID}\nBalance: ${bal}\nBase: ${BASE_AMOUNT}\nCurrent: ${current_amount}\nMartingale: ON\nPairs: EUR/USD OTC & REAL")

@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    global current_amount, martingale_level
    trade_id = call.data.replace("execute_","").replace("skip_","")
    if trade_id not in pending_trades:
        bot.answer_callback_query(call.id, "Expired")
        return
    data = pending_trades[trade_id]

    if "skip" in call.data:
        bot.edit_message_text(f"⏭️ SKIPPED {data['pair']} {data['direction']}", call.message.chat.id, call.message.message_id)
        del pending_trades[trade_id]
        return

    # EXECUTE
    pair = data['pair']
    direction = data['direction']
    bot.edit_message_text(f"⏳ Kevin Trailblazer Executing {direction.upper()} on {pair} for ${current_amount}... (Level {martingale_level})", call.message.chat.id, call.message.message_id)

    try:
        status, id = Iq.buy(current_amount, pair, direction, 1)
        if not status:
            bot.send_message(call.message.chat.id, f"❌ Failed: {id}")
            return

        bot.send_message(call.message.chat.id, f"✅ TRADE EXECUTED\n{pair} | {direction.upper()} | ${current_amount}\nID: {id}\nWaiting 65s...")

        time.sleep(65)
        profit = Iq.check_win_v3(id)

        if profit > 0:
            bot.send_message(call.message.chat.id, f"💰 WIN! PROFIT: +${round(profit,2)}\nPair: {pair}\nBalance: ${round(Iq.get_balance(),2)}\n🔄 Resetting to ${BASE_AMOUNT}")
            current_amount = BASE_AMOUNT
            martingale_level = 0
        else:
            martingale_level += 1
            loss_amount = current_amount
            current_amount = current_amount * 2
            # safety cap to avoid blowing account
            if current_amount > 160: # max 4 levels: 10,20,40,80,160
                current_amount = BASE_AMOUNT
                martingale_level = 0
                bot.send_message(call.message.chat.id, f"📉 LOSS: -${loss_amount}\nPair: {pair}\n⚠️ Martingale cap reached. Reset to ${BASE_AMOUNT}\nBalance: ${round(Iq.get_balance(),2)}")
            else:
                bot.send_message(call.message.chat.id, f"📉 LOSS: -${loss_amount}\nPair: {pair}\nNext amount doubled to ${current_amount} (Level {martingale_level})\nBalance: ${round(Iq.get_balance(),2)}")

    except Exception as e:
        bot.send_message(call.message.chat.id, f"Error: {e}")

    if trade_id in pending_trades:
        del pending_trades[trade_id]

def scanner():
    while True:
        if not OWNER_ID or not Iq:
            time.sleep(5)
            continue
        for pair in PAIRS:
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
                    trade_id = f"{pair}_{int(time.time())}"
                    pending_trades[trade_id] = {"pair": pair, "direction": signal}
                    markup = types.InlineKeyboardMarkup()
                    btn_exec = types.InlineKeyboardButton(f"✅ EXECUTE {signal.upper()} ${current_amount}", callback_data=f"execute_{trade_id}")
                    btn_skip = types.InlineKeyboardButton("⏭️ SKIP", callback_data=f"skip_{trade_id}")
                    markup.add(btn_exec, btn_skip)
                    bot.send_message(OWNER_ID, f"📊 KEVIN SIGNAL\nPair: {pair}\nDirection: {signal.upper()} ({'BUY' if signal=='call' else 'SELL'})\nRSI: {rsi:.1f}\nLevel: {martingale_level} | Amount: ${current_amount}", reply_markup=markup)
                    time.sleep(30)
            except Exception as e:
                print(f"Scan {pair}: {e}")
        time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
