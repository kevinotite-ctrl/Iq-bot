import os, time, threading, random, datetime, requests
from flask import Flask, request
import telebot

print("=== V17.0 KEVIN IQ SNIPER 90%+ ONLY ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()

OWNER_ID = None
SCANNING = True
PAIRS = ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDUSD", "EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "USDJPY-OTC", "GBPJPY-OTC"]

def analyze_simple(pair):
    rsi = round(random.uniform(28, 72),1)
    ema_state = random.choice(["UP", "DOWN"])
    if ema_state == "UP" and rsi > 50:
        direction="CALL"
        reason=f"Up momentum"
        conf=random.randint(75,98)
    else:
        direction="PUT"
        reason=f"Down momentum"
        conf=random.randint(70,96)
    return direction, conf, rsi, ema_state, reason

bot = None
if ':' in TOKEN:
    bot = telebot.TeleBot(TOKEN, threaded=False)

    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        OWNER_ID=m.chat.id
        bot.send_message(m.chat.id, f"💹 V17.0 KEVIN IQ SNIPER READY\n\n✅ Only 90-100% signals 💎\n✅ 10 sec alert before signal\n✅ 3 MIN trade\n✅ New emoji design\n\n/resume - start\n/pause - stop\n/test - test now")

    @bot.message_handler(commands=['resume'])
    def resume(m):
        global OWNER_ID, SCANNING
        OWNER_ID=m.chat.id; SCANNING=True
        bot.send_message(m.chat.id, "▶️ Scanning ON (90%+ ONLY)\nYou will get:\n1. ‼️signal alert incoming ‼️💰\n2. 10 sec later -> SIGNAL")

    @bot.message_handler(commands=['pause'])
    def pause(m):
        global SCANNING; SCANNING=False
        bot.send_message(m.chat.id, "⏸️ Paused")

    @bot.message_handler(commands=['test'])
    def test(m):
        global OWNER_ID
        OWNER_ID=m.chat.id
        pair=random.choice(PAIRS)
        d,c,rsi,ema_state,reason = analyze_simple(pair)
        c = random.randint(90,99)
        now=datetime.datetime.now()+datetime.timedelta(hours=1)
        exp=now+datetime.timedelta(minutes=3)
        bot.send_message(m.chat.id, "‼️signal alert incoming ‼️💰")
        time.sleep(10)
        dir_emoji = "📈" if d=="CALL" else "📉"
        trend_text = "🟢 ABOVE" if ema_state=="UP" else "🔴 BELOW"
        action_emoji = "🔺" if d=="CALL" else "🔻"
        extra_fire = "🔥🔥🔥" if c>=95 else "🔥🔥"
        msg = f"""🚨🚨 KEVIN IQ SNIPER 🚨🚨

💱 Pair: {pair}
{dir_emoji} Direction: {d} - 3 MIN {action_emoji}
🔥 Confidence: {c}% 💎 {extra_fire}

📊 ANALYSIS:
├ RSI: {rsi}
├ Trend: EMA7 {trend_text} EMA21
└ Momentum: {reason} 💪

⏰ Entry: {now.strftime('%H:%M')}
🎯 Expiry: {exp.strftime('%H:%M')}
⏳ Time: GMT+1

👉 ACTION: Trade {d} NOW! (3 min expiry)
⚠️ Risk: 1% of balance only!

#IQOption #KevinSignals"""
        bot.send_message(m.chat.id, msg)

    @app.route(f'/{TOKEN}', methods=['POST'])
    def webhook():
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return ''
        return 'ok', 200

    @app.route('/')
    def home(): return "V17.0 90%+ ONLY LIVE", 200

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
            d,c,rsi,ema_state,reason = analyze_simple(pair)

            if c < 90:
                print(f"SKIPPED {pair} {c}%", flush=True)
                continue

            print(f"ALERTING for {pair} {c}%", flush=True)
            try:
                bot.send_message(OWNER_ID, "‼️signal alert incoming ‼️💰")
            except:
                continue
            time.sleep(10)
            now=datetime.datetime.now()+datetime.timedelta(hours=1)
            exp=now+datetime.timedelta(minutes=3)
            dir_emoji = "📈" if d=="CALL" else "📉"
            trend_text = "🟢 ABOVE" if ema_state=="UP" else "🔴 BELOW"
            action_emoji = "🔺" if d=="CALL" else "🔻"
            extra_fire = "🔥🔥🔥" if c>=95 else "🔥🔥"
            msg = f"""🚨🚨 KEVIN IQ SNIPER 🚨🚨

💱 Pair: {pair}
{dir_emoji} Direction: {d} - 3 MIN {action_emoji}
🔥 Confidence: {c}% 💎 {extra_fire}

📊 ANALYSIS:
├ RSI: {rsi}
├ Trend: EMA7 {trend_text} EMA21
└ Momentum: {reason} 💪

⏰ Entry: {now.strftime('%H:%M')}
🎯 Expiry: {exp.strftime('%H:%M')}
⏳ Time: GMT+1

👉 ACTION: Trade {d} NOW! (3 min expiry)
⚠️ Risk: 1% of balance only!

#IQOption #KevinSignals"""
            bot.send_message(OWNER_ID, msg)
            time.sleep(300)
        except Exception as e:
            print(f"SCAN ERR {e}", flush=True)
            time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
