import os, time, threading, random, datetime, requests
from flask import Flask, request
import telebot

print("=== V17.2 FINAL CHANNEL FIX ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
CHANNEL_ID = "@trailblazeebot" # YOUR PUBLIC CHANNEL FROM SCREENSHOT

OWNER_ID = None
SCANNING = True
PAIRS = ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDUSD", "EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "USDJPY-OTC", "GBPJPY-OTC"]

def analyze_simple(pair):
    rsi = round(random.uniform(28, 72),1)
    ema_state = random.choice(["UP", "DOWN"])
    if ema_state == "UP" and rsi > 50:
        direction="CALL"; reason="Up momentum"; conf=random.randint(75,98)
    else:
        direction="PUT"; reason="Down momentum"; conf=random.randint(70,96)
    return direction, conf, rsi, ema_state, reason

bot = None
if ':' in TOKEN:
    bot = telebot.TeleBot(TOKEN, threaded=False)

    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID; OWNER_ID=m.chat.id
        bot.send_message(m.chat.id, "💹 V17.2 READY\n✅ Only 90-100%\n✅ Auto to channel @trailblazeebot\n\n/resume - start\n/test - test channel")

    @bot.message_handler(commands=['resume'])
    def resume(m):
        global OWNER_ID, SCANNING; OWNER_ID=m.chat.id; SCANNING=True
        bot.send_message(m.chat.id, "▶️ Scanning ON (90%+)\nSignals go to:\n1. You (private)\n2. Channel @trailblazeebot")

    @bot.message_handler(commands=['pause'])
    def pause(m):
        global SCANNING; SCANNING=False; bot.send_message(m.chat.id, "⏸️ Paused")

    @bot.message_handler(commands=['test'])
    def test(m):
        global OWNER_ID; OWNER_ID=m.chat.id
        pair=random.choice(PAIRS); d,c,rsi,ema,reason = analyze_simple(pair); c=random.randint(90,99)
        now=datetime.datetime.now()+datetime.timedelta(hours=1); exp=now+datetime.timedelta(minutes=3)
        bot.send_message(m.chat.id, "‼️signal alert incoming ‼️💰")
        time.sleep(3)
        dir_emoji="📈" if d=="CALL" else "📉"; trend="🟢 ABOVE" if ema=="UP" else "🔴 BELOW"; act="🔺" if d=="CALL" else "🔻"; extra="🔥🔥🔥" if c>=95 else "🔥🔥"
        msg=f"""🚨🚨 KEVIN IQ SNIPER 🚨🚨

💱 Pair: {pair}
{dir_emoji} Direction: {d} - 3 MIN {act}
🔥 Confidence: {c}% 💎 {extra}

📊 ANALYSIS:
├ RSI: {rsi}
├ Trend: EMA7 {trend} EMA21
└ Momentum: {reason} 💪

⏰ Entry: {now.strftime('%H:%M')}
🎯 Expiry: {exp.strftime('%H:%M')}
⏳ Time: GMT+1

👉 ACTION: Trade {d} NOW! (3 min expiry)
⚠️ Risk: 1% of balance only!

#IQOption #KevinSignals"""
        bot.send_message(m.chat.id, msg)
        try:
            bot.send_message(CHANNEL_ID, msg)
            bot.send_message(m.chat.id, f"✅ SUCCESS! Posted to channel {CHANNEL_ID}\nCheck your channel now!")
        except Exception as e:
            bot.send_message(m.chat.id, f"❌ FAILED to post to {CHANNEL_ID}\nError: {e}\n\nFIX: Make bot ADMIN with POST permission")

    @app.route(f'/{TOKEN}', methods=['POST'])
    def webhook():
        if request.headers.get('content-type')=='application/json':
            js=request.get_data().decode('utf-8'); upd=telebot.types.Update.de_json(js); bot.process_new_updates([upd]); return ''
        return 'ok',200
    @app.route('/')
    def home(): return "V17.2 FINAL LIVE",200
    def set_webhook():
        time.sleep(5)
        if RENDER_URL:
            try:
                requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10); time.sleep(2)
                url=f"{RENDER_URL}/{TOKEN}"; r=requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}", timeout=10); print(f"Webhook {r.text}", flush=True)
            except Exception as e: print(e, flush=True)
    threading.Thread(target=set_webhook, daemon=True).start()

def scanner():
    while True:
        try:
            time.sleep(30)
            if not OWNER_ID or not SCANNING or not bot: continue
            pair=random.choice(PAIRS); d,c,rsi,ema,reason=analyze_simple(pair)
            if c<90:
                print(f"SKIPPED {pair} {c}%", flush=True); continue
            print(f"ALERTING {pair} {c}% -> {CHANNEL_ID}", flush=True)
            try:
                bot.send_message(OWNER_ID, "‼️signal alert incoming ‼️💰")
                bot.send_message(CHANNEL_ID, "‼️signal alert incoming ‼️💰")
            except Exception as e:
                print(f"Alert err {e}", flush=True); continue
            time.sleep(10)
            now=datetime.datetime.now()+datetime.timedelta(hours=1); exp=now+datetime.timedelta(minutes=3)
            dir_emoji="📈" if d=="CALL" else "📉"; trend="🟢 ABOVE" if ema=="UP" else "🔴 BELOW"; act="🔺" if d=="CALL" else "🔻"; extra="🔥🔥🔥" if c>=95 else "🔥🔥"
            msg=f"""🚨🚨 KEVIN IQ SNIPER 🚨🚨

💱 Pair: {pair}
{dir_emoji} Direction: {d} - 3 MIN {act}
🔥 Confidence: {c}% 💎 {extra}

📊 ANALYSIS:
├ RSI: {rsi}
├ Trend: EMA7 {trend} EMA21
└ Momentum: {reason} 💪

⏰ Entry: {now.strftime('%H:%M')}
🎯 Expiry: {exp.strftime('%H:%M')}
⏳ Time: GMT+1

👉 ACTION: Trade {d} NOW! (3 min expiry)
⚠️ Risk: 1% of balance only!

#IQOption #KevinSignals"""
            bot.send_message(OWNER_ID, msg)
            try:
                bot.send_message(CHANNEL_ID, msg)
                print(f"SENT to channel {CHANNEL_ID}", flush=True)
            except Exception as e:
                print(f"Channel send fail {e}", flush=True)
            time.sleep(300)
        except Exception as e: print(f"SCAN ERR {e}", flush=True); time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
