import os, re, time, threading, random
from flask import Flask
print("=== BOT V6 AUTO SIGNAL - SCAN + CONFIRM + RESULT ===", flush=True)
app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

OWNER_ID = None
Iq = None
LAST_SIGNAL_TIME = 0
SCANNING = True

# === IQ CONNECT ===
try:
    try: from iqoptionapi.stable_api import IQ_Option
    except: from iqoptionapi.api import IQ_Option
    print("Connecting IQ...", flush=True)
    Iq = IQ_Option(EMAIL, PASS)
    check, reason = Iq.connect()
    print(f"IQ CONNECT: {check} | {reason}", flush=True)
    if check:
        Iq.change_balance("PRACTICE")
        time.sleep(1)
        print(f"IQ BALANCE PRACTICE: ${Iq.get_balance()}", flush=True)
    else: Iq = None
except Exception as e:
    print(f"IQ EXCEPTION: {e}", flush=True)
    Iq = None

@app.route('/')
def home(): return f"V6 AUTO SIGNAL LIVE - BAL: ${Iq.get_balance() if Iq else 'NOT CONNECTED'}"

# === INDICATORS ===
def get_rsi(prices, period=14):
    if len(prices) < period+1: return 50
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i]-prices[i-1]
        if diff>0: gains.append(diff); losses.append(0)
        else: gains.append(0); losses.append(-diff)
    avg_gain = sum(gains[-period:])/period
    avg_loss = sum(losses[-period:])/period
    if avg_loss==0: return 100
    rs = avg_gain/avg_loss
    return 100 - (100/(1+rs))

def get_ema(prices, period):
    if len(prices) < period: return prices[-1]
    k = 2/(period+1)
    ema = sum(prices[:period])/period
    for p in prices[period:]:
        ema = p*k + ema*(1-k)
    return ema

def analyze_pair(pair):
    try:
        # Get 1min candles
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles)<30: return None
        closes = [c['close'] for c in candles]
        rsi = get_rsi(closes, 14)
        ema9 = get_ema(closes, 9)
        ema21 = get_ema(closes, 21)
        price = closes[-1]

        # STRONG SIGNALS ONLY
        if rsi < 35 and price > ema9 and ema9 > ema21:
            return {"pair":pair, "dir":"call", "rsi":round(rsi,1), "reason":f"RSI Oversold {round(rsi,1)} + Uptrend"}
        if rsi > 65 and price < ema9 and ema9 < ema21:
            return {"pair":pair, "dir":"put", "rsi":round(rsi,1), "reason":f"RSI Overbought {round(rsi,1)} + Downtrend"}
        if rsi < 28:
            return {"pair":pair, "dir":"call", "rsi":round(rsi,1), "reason":f"Extreme Oversold {round(rsi,1)}"}
        if rsi > 72:
            return {"pair":pair, "dir":"put", "rsi":round(rsi,1), "reason":f"Extreme Overbought {round(rsi,1)}"}
    except Exception as e:
        print(f"Analyze {pair} error: {e}", flush=True)
    return None

# === TELEGRAM ===
def run_telegram():
    import telebot
    from telebot import types
    global OWNER_ID, LAST_SIGNAL_TIME, SCANNING
    bot = telebot.TeleBot(TOKEN)

    PAIRS = ["EURUSD-OTC","GBPUSD-OTC","USDJPY-OTC","AUDUSD-OTC","EURGBP-OTC","GBPJPY-OTC","USDCHF-OTC","EURJPY-OTC","EURUSD","GBPUSD"]

    @bot.message_handler(commands=['start'])
    def start_cmd(msg):
        global OWNER_ID
        OWNER_ID = msg.chat.id
        bal = Iq.get_balance() if Iq else "Not connected"
        print(f"OWNER ID SAVED: {OWNER_ID}", flush=True)
        bot.reply_to(msg, f"✅ V6 AUTO SIGNAL ACTIVE\nID: {OWNER_ID}\nBalance: ${bal}\n\n🤖 I will SCAN market every 2 mins and send you BUY/SELL signals.\nYou just tap EXECUTE or SKIP.\n\nCommands:\n/start - activate\n/balance - check balance\n/scan - force scan now\n/stop - stop auto scan\n/go - resume auto scan")

    @bot.message_handler(commands=['balance'])
    def bal_cmd(msg): bot.reply_to(msg, f"Balance: ${Iq.get_balance() if Iq else 'Not connected'}")

    @bot.message_handler(commands=['scan'])
    def force_scan(msg):
        bot.reply_to(msg, "🔍 Scanning market now...")
        threading.Thread(target=auto_scan_once, args=(bot,), daemon=True).start()

    @bot.message_handler(commands=['stop'])
    def stop_scan(msg):
        global SCANNING
        SCANNING=False
        bot.reply_to(msg, "⏸️ Auto scan stopped. Use /go to resume")

    @bot.message_handler(commands=['go'])
    def go_scan(msg):
        global SCANNING
        SCANNING=True
        bot.reply_to(msg, "▶️ Auto scan resumed - signal every 2 mins")

    def check_result(trade_id, pair, direction, chat_id):
        time.sleep(65)
        try:
            result = Iq.check_win_v3(trade_id)
            bal = Iq.get_balance()
            print(f"RESULT {trade_id}: {result}", flush=True)
            if isinstance(result, (int,float)) and result>0:
                bot.send_message(chat_id, f"✅ VICTORY!\nPair: {pair}\nDir: {direction.upper()}\nProfit: +${round(result,2)}\nBalance: ${bal}")
            elif result==True:
                bot.send_message(chat_id, f"✅ VICTORY! {pair} {direction.upper()}\nBalance: ${bal}")
            else:
                bot.send_message(chat_id, f"❌ LOSS!\nPair: {pair}\nDir: {direction.upper()}\nLost: -$10\nBalance: ${bal}")
        except Exception as e:
            bot.send_message(chat_id, f"Trade {pair} finished. Check IQ. {e}")

    @bot.callback_query_handler(func=lambda c: True)
    def on_confirm(call):
        data = call.data
        if data.startswith("skip_"):
            bot.answer_callback_query(call.id, "Skipped")
            bot.edit_message_text("⏭️ Skipped - scanning for next signal in 2 mins...", call.message.chat.id, call.message.message_id)
            return
        if data.startswith("trade_"):
            _, pair, direction = data.split("_")
            bot.answer_callback_query(call.id, "Executing...")
            bot.edit_message_text(f"⏳ Executing {pair} {direction.upper()} $10...", call.message.chat.id, call.message.message_id)
            if not Iq:
                bot.send_message(call.message.chat.id, "❌ IQ not connected!")
                return
            ok, _id = Iq.buy(10, pair, direction, 1)
            print(f"TRADE EXECUTED: {pair} {direction} -> {ok} {_id}", flush=True)
            if ok:
                bot.send_message(call.message.chat.id, f"🚀 TRADE EXECUTED\nPair: {pair}\nDirection: {direction.upper()}\nAmount: $10\nID: {_id}\nExpiry: 1 MIN\nWaiting for result...")
                threading.Thread(target=check_result, args=(_id, pair, direction, call.message.chat.id), daemon=True).start()
            else:
                bot.send_message(call.message.chat.id, f"❌ FAILED: {_id}")

    def auto_scan_once(bot_instance):
        global LAST_SIGNAL_TIME
        if not Iq or not OWNER_ID: return
        print("AUTO SCAN START...", flush=True)
        best = None
        random.shuffle(PAIRS)
        for p in PAIRS[:6]: # scan 6 pairs per cycle for speed
            sig = analyze_pair(p)
            if sig:
                best = sig
                break
        if best:
            LAST_SIGNAL_TIME = time.time()
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton(f"✅ EXECUTE TRADE $10 {best['pair']} {best['dir'].upper()}", callback_data=f"trade_{best['pair']}_{best['dir']}"),
                types.InlineKeyboardButton("❌ SKIP", callback_data=f"skip_{best['pair']}")
            )
            bal = Iq.get_balance()
            action_text = "BUY 🟢" if best['dir']=="call" else "SELL 🔴"
            bot_instance.send_message(OWNER_ID, f"📡 NEW SIGNAL\n\nPair: {best['pair']}\nSignal: {best['dir'].upper()} - {action_text}\nAnalysis: {best['reason']}\nRSI: {best['rsi']}\nAmount: $10\nBalance: ${bal}\n\n👇 Place trade?", reply_markup=markup)
            print(f"SIGNAL SENT: {best}", flush=True)
        else:
            print("No strong signal this scan", flush=True)

    def auto_loop():
        while True:
            time.sleep(120) # every 2 mins
            if SCANNING and OWNER_ID and Iq:
                try: auto_scan_once(bot)
                except Exception as e: print(f"Auto loop error: {e}", flush=True)

    threading.Thread(target=auto_loop, daemon=True).start()
    bot.infinity_polling(skip_pending=True)

threading.Thread(target=run_telegram, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))
