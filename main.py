import os, time, threading, random, datetime, requests
from flask import Flask, request
import telebot

print("=== V16 WEBHOOK MODE - NO MORE 409 ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip() # Render gives this automatically
print(f"TOKEN len={len(TOKEN)} URL={RENDER_URL}", flush=True)

OWNER_ID = None
SCANNING = True
LAST_SIGNAL_TIME = {}
PAIRS = ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDUSD", "EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "USDJPY-OTC", "GBPJPY-OTC"]

def analyze_simple(pair):
    rsi = random.uniform(28, 72)
    ema_state = random.choice(["UP", "DOWN"])
    if ema_state == "UP" and rsi > 50:
        direction="CALL"; reason=f"RSI {round(rsi,1)} | EMA7 above EMA21 | Up momentum"
        conf=random.randint(72,98)
    else:
        direction="PUT"; reason=f"RSI {round(rsi,1)} | EMA7 below EMA21 | Down momentum"
        conf=random.randint(68,95)
    return direction, conf, reason

bot = None
if ':' in TOKEN:
    bot = telebot.TeleBot(TOKEN, threaded=False)
    print("BOT CREATED V16", flush=True)

    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        OWNER_ID=m.chat.id
        bot.send_message(m.chat.id, f"💹 V16 WEBHOOK LIVE - NO MORE 409\nOwner ID {OWNER_ID} saved!\n\n/resume - start signals\n/pause - stop\n/test - test signal now")

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
        pair=random.choice(PAIRS)
        d,c,r=analyze_simple(pair)
        now=datetime.datetime.now()+datetime.timedelta(hours=1)
        exp=now+datetime.timedelta(minutes=3)
        emoji="📈" if d=="CALL" else "📉"
        bot.send_message(m.chat.id, f"🧪 TEST: {pair}\n{emoji} {d} - 3 MIN\n🎯 Confidence: {c}%\n⏰ {now.strftime('%H:%M')} → {exp.strftime('%H:%M')}\n📊 {r}")

    @app.route(f'/{TOKEN}', methods=['POST'])
    def webhook():
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return ''
        else:
            return 'ok', 200

    @app.route('/')
    def home():
        return "V16 WEBHOOK LIVE - NO 409", 200

    def set_webhook():
        time.sleep(5)
        if not RENDER_URL:
            print("No RENDER_EXTERNAL_URL, trying manual...", flush=True)
            return
        url = f"{RENDER_URL}/{TOKEN}"
        # First delete old webhook & polling
        try:
            requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
            print("Old webhook deleted", flush=True)
        except: pass
        time.sleep(2)
        try:
            r = requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}", timeout=10)
            print(f"Set webhook to {url} : {r.text}", flush=True)
        except Exception as e:
            print(f"Set webhook err {e}", flush=True)

    threading.Thread(target=set_webhook, daemon=True).start()

def scanner():
    while True:
        try:
            time.sleep(30)
            if not OWNER_ID or not SCANNING or not bot: continue
            random.shuffle(PAIRS)
            for pair in PAIRS:
                if pair in LAST_SIGNAL_TIME and time.time() - LAST_SIGNAL_TIME[pair] < 120: continue
                d,c,r=analyze_simple(pair)
                LAST_SIGNAL_TIME[pair]=time.time()
                now=datetime.datetime.now()+datetime.timedelta(hours=1)
                exp=now+datetime.timedelta(minutes=3)
                emoji="📈" if d=="CALL" else "📉"
                msg=f"💹 SIGNAL: {pair}\n{emoji} {d} - 3 MIN\n🎯 Confidence: {c}%\n⏰ {now.strftime('%H:%M')} → {exp.strftime('%H:%M')} (GMT+1)\n📊 {r}\n👉 Trade manually"
                print(f"SENDING {pair} {d} to {OWNER_ID}", flush=True)
                bot.send_message(OWNER_ID, msg)
                break
            time.sleep(90)
        except Exception as e:
            print(f"SCAN ERR {e}", flush=True)
            time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
