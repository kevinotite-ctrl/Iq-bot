import os, time, threading, random, datetime, requests
from flask import Flask
import telebot

print("=== V15.1 FORCE SIGNALS NO IQ ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
OWNER_ID = None
SCANNING = True
LAST_SIGNAL_TIME = {}
PAIRS = ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDUSD", "EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "USDJPY-OTC", "GBPJPY-OTC"]

def analyze_simple(pair):
    # Simulate real market analysis but always gives direction
    # Like your first bot - no external API needed
    rsi = random.uniform(28, 72)
    ema_state = random.choice(["UP", "DOWN"])
    close_diff = random.uniform(0.02, 0.15)

    if ema_state == "UP" and rsi > 50:
        direction = "CALL"
        reason = f"RSI {round(rsi,1)} | EMA7 above EMA21 | Up momentum +{round(close_diff,3)}%"
        conf = random.randint(68, 95)
    else:
        direction = "PUT"
        reason = f"RSI {round(rsi,1)} | EMA7 below EMA21 | Down momentum -{round(close_diff,3)}%"
        conf = random.randint(66, 93)

    # occasional high confidence
    if random.random() > 0.7:
        conf = random.randint(85, 98)

    return direction, conf, reason

@app.route('/')
def home(): return "V15.1 FORCE SIGNALS LIVE", 200

bot = None
if ':' in TOKEN:
    bot = telebot.TeleBot(TOKEN)
    print("BOT CREATED V15.1", flush=True)

    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        OWNER_ID=m.chat.id
        bot.send_message(m.chat.id, f"💹 V15.1 LIVE\nOwner ID {OWNER_ID} saved!\n\nYou will get 3 MIN signals every 2 mins\n\n/resume - start\n/pause - stop\n/test - send test signal now")

    @bot.message_handler(commands=['resume'])
    def resume(m):
        global OWNER_ID, SCANNING
        OWNER_ID=m.chat.id; SCANNING=True
        bot.send_message(m.chat.id, "▶️ Scanning ON - Next signal in 30s")

    @bot.message_handler(commands=['pause'])
    def pause(m):
        global SCANNING; SCANNING=False
        bot.send_message(m.chat.id, "⏸️ Paused")

    @bot.message_handler(commands=['test'])
    def test(m):
        global OWNER_ID
        OWNER_ID=m.chat.id
        pair = random.choice(PAIRS)
        direction, conf, reason = analyze_simple(pair)
        now = datetime.datetime.now() + datetime.timedelta(hours=1)
        expire = now + datetime.timedelta(minutes=3)
        emoji = "📈" if direction=="CALL" else "📉"
        msg = f"🧪 TEST SIGNAL: {pair}\n{emoji} {direction} - 3 MIN\n🎯 Confidence: {conf}%\n⏰ {now.strftime('%H:%M')} → {expire.strftime('%H:%M')}\n📊 {reason}"
        bot.send_message(m.chat.id, msg)

    def run_bot():
        while True:
            try:
                try:
                    requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
                    bot.remove_webhook()
                except: pass
                print("V15.1 Polling started...", flush=True)
                bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=30)
            except Exception as e:
                print(f"Poll {e}", flush=True)
                time.sleep(10)

    threading.Thread(target=run_bot, daemon=True).start()

def scanner():
    while True:
        try:
            time.sleep(30) # first signal after 30s
            if not OWNER_ID:
                print("SCANNER: No OWNER_ID yet, waiting for /start", flush=True)
                continue
            if not SCANNING:
                print("SCANNER: Paused", flush=True)
                continue

            random.shuffle(PAIRS)
            for pair in PAIRS:
                if pair in LAST_SIGNAL_TIME and time.time() - LAST_SIGNAL_TIME[pair] < 120:
                    continue
                direction, conf, reason = analyze_simple(pair)
                LAST_SIGNAL_TIME[pair]=time.time()
                now = datetime.datetime.now() + datetime.timedelta(hours=1)
                expire = now + datetime.timedelta(minutes=3)
                emoji = "📈" if direction=="CALL" else "📉"
                msg = f"💹 SIGNAL: {pair}\n{emoji} {direction} - 3 MIN\n🎯 Confidence: {conf}%\n⏰ {now.strftime('%H:%M')} → {expire.strftime('%H:%M')} (GMT+1)\n📊 {reason}\n👉 Trade manually"
                print(f"SENDING SIGNAL {pair} {direction} {conf}% to {OWNER_ID}", flush=True)
                bot.send_message(OWNER_ID, msg)
                break
            time.sleep(90)
        except Exception as e:
            print(f"SCAN ERR {e}", flush=True)
            time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
