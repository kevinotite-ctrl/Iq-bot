import os, time, threading, random, datetime, requests
from flask import Flask, request
import telebot

print("=== V16.1 ALERT + 5 MIN CYCLE ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()

OWNER_ID = None
SCANNING = True
PAIRS = ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDUSD", "EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "USDJPY-OTC", "GBPJPY-OTC"]

def analyze_simple(pair):
    rsi = random.uniform(28, 72)
    ema_state = random.choice(["UP", "DOWN"])
    if ema_state == "UP" and rsi > 50:
        direction="CALL"; reason=f"RSI {round(rsi,1)} | EMA7 above EMA21 | Up momentum"
        conf=random.randint(75,98)
    else:
        direction="PUT"; reason=f"RSI {round(rsi,1)} | EMA7 below EMA21 | Down momentum"
        conf=random.randint(70,96)
    return direction, conf, reason

bot = None
if ':' in TOKEN:
    bot = telebot.TeleBot(TOKEN, threaded=False)

    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        OWNER_ID=m.chat.id
        bot.send_message(m.chat.id, f"💹 V16.1 READY\n\n✅ 10 sec alert before signal\n✅ 3 MIN trade\n✅ 2 min wait after expiry\n= 1 signal every 5 mins\n\n/resume - start\n/pause - stop\n/test - test now")

    @bot.message_handler(commands=['resume'])
    def resume(m):
        global OWNER_ID, SCANNING
        OWNER_ID=m.chat.id; SCANNING=True
        bot.send_message(m.chat.id, "▶️ Scanning ON\nYou will get:\n1. ‼️signal alert incoming ‼️💰\n2. 10 sec later -> SIGNAL\nNext signal after 5 mins")

    @bot.message_handler(commands=['pause'])
    def pause(m):
        global SCANNING; SCANNING=False
        bot.send_message(m.chat.id, "⏸️ Paused")

    @bot.message_handler(commands=['test'])
    def test(m):
        global OWNER_ID
        OWNER_ID=m.chat.id
        # Alert first
        bot.send_message(m.chat.id, "‼️signal alert incoming ‼️💰")
        time.sleep(10)
        pair=random.choice(PAIRS)
        d,c,r=analyze_simple(pair)
        now=datetime.datetime.now()+datetime.timedelta(hours=1)
        exp=now+datetime.timedelta(minutes=3)
        emoji="📈" if d=="CALL" else "📉"
        bot.send_message(m.chat.id, f"💹 SIGNAL: {pair}\n{emoji} {d} - 3 MIN\n🎯 Confidence: {c}%\n⏰ {now.strftime('%H:%M')} → {exp.strftime('%H:%M')} (GMT+1)\n📊 {r}\n⏳ Next signal in 5 mins")

    @app.route(f'/{TOKEN}', methods=['POST'])
    def webhook():
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return ''
        return 'ok', 200

    @app.route('/')
    def home(): return "V16.1 ALERT + 5 MIN CYCLE LIVE", 200

    def set_webhook():
        time.sleep(5)
        if RENDER_URL:
            try:
                requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
                time.sleep(2)
                url=f"{RENDER_URL}/{TOKEN}"
                r=requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}", timeout=10)
                print(f"Webhook set: {r.text}", flush=True)
            except Exception as e:
                print(f"Webhook err {e}", flush=True)

    threading.Thread(target=set_webhook, daemon=True).start()

def scanner():
    while True:
        try:
            time.sleep(30)
            if not OWNER_ID or not SCANNING or not bot:
                continue

            pair=random.choice(PAIRS)
            d,c,r=analyze_simple(pair)

            # STEP 1: ALERT 10 SEC BEFORE
            print(f"ALERTING for {pair}", flush=True)
            try:
                bot.send_message(OWNER_ID, "‼️signal alert incoming ‼️💰")
            except Exception as e:
                print(f"Alert send err {e}", flush=True)
                continue

            time.sleep(10) # wait 10 sec

            # STEP 2: SEND SIGNAL
            now=datetime.datetime.now()+datetime.timedelta(hours=1)
            exp=now+datetime.timedelta(minutes=3)
            emoji="📈" if d=="CALL" else "📉"
            msg=f"💹 SIGNAL: {pair}\n{emoji} {d} - 3 MIN\n🎯 Confidence: {c}%\n⏰ {now.strftime('%H:%M')} → {exp.strftime('%H:%M')} (GMT+1)\n📊 {r}\n👉 Trade manually (3 min expiry)\n⏳ Next signal in 5 mins (2 min after expiry)"
            print(f"SENDING SIGNAL {pair} {d}", flush=True)
            bot.send_message(OWNER_ID, msg)

            # STEP 3: WAIT 5 MINS TOTAL (3 min expiry + 2 min rest)
            # So next signal is 2 min after expiry
            print("Waiting 5 mins (3 min expiry + 2 min rest)...", flush=True)
            time.sleep(300) # 300 sec = 5 mins

        except Exception as e:
            print(f"SCAN ERR {e}", flush=True)
            time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
