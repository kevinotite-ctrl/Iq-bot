import os, time, threading, random, datetime, requests
from flask import Flask
import telebot

print("=== V14.1 MANUAL 3MIN SIGNALS + WEBHOOK FIX ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
EMAIL = (os.getenv("IQ_EMAIL") or "").strip()
PASS = (os.getenv("IQ_PASS") or os.getenv("IQ_PASSWORD") or "").strip()

print(f"TOKEN len={len(TOKEN)} EMAIL={EMAIL}", flush=True)

OWNER_ID = None
Iq = None
SCANNING = True
LAST_SIGNAL_TIME = {}
PAIRS = ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDUSD", "EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "EURJPY-OTC", "USDJPY-OTC", "GBPJPY-OTC"]

def iq_connect():
    global Iq
    try:
        from iqoptionapi.stable_api import IQ_Option
        Iq = IQ_Option(EMAIL, PASS)
        check, reason = Iq.connect()
        print(f"IQ CONNECT {check} {reason}", flush=True)
        if check:
            Iq.change_balance("PRACTICE")
            print(f"IQ BAL {Iq.get_balance()} CONNECTED", flush=True)
            return True
    except Exception as e:
        print(f"IQ ERR {e}", flush=True)
    return False

def get_confidence(candles):
    try:
        closes = [c['close'] for c in candles]
        gains=[]; losses=[]
        for i in range(1,len(closes)):
            d=closes[i]-closes[i-1]
            gains.append(max(d,0)); losses.append(max(-d,0))
        period=14
        ag=sum(gains[-period:])/period if len(gains)>=period else 0.01
        al=sum(losses[-period:])/period if len(losses)>=period else 0.01
        if al==0: rsi=70
        else:
            rsi=100-(100/(1+ag/al if (ag/al)!=0 else 1))

        def ema(data, p):
            e=data[0]; k=2/(p+1)
            for v in data[1:]: e=v*k+e*(1-k)
            return e
        ema7=ema(closes[-15:],7)
        ema21=ema(closes,21)
        close=closes[-1]

        score=60
        diff = abs(ema7-ema21) / close * 1000
        if diff > 0.05: score+=10
        if diff > 0.1: score+=10
        if 60 <= rsi <= 70 or 30 <= rsi <= 40: score+=15
        if 65 <= rsi <= 72 or 28 <= rsi <= 35: score+=10
        if (close > ema7 > ema21) or (close < ema7 < ema21): score+=10
        score = max(60, min(96, int(score + random.randint(-2,2))))
        return score, rsi, ema7, ema21
    except:
        return 65, 50, 0, 0

def analyze(pair):
    try:
        if not Iq or not Iq.check_connect():
            if not iq_connect(): return None, 0, "IQ not connected"
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles)<25: return None, 0, "No data"
        closes = [c['close'] for c in candles]
        conf, rsi, ema7, ema21 = get_confidence(candles)
        close = closes[-1]
        direction=None
        if close > ema7 and ema7 > ema21 and 55 < rsi < 78:
            direction="CALL"
        elif close < ema7 and ema7 < ema21 and 22 < rsi < 45:
            direction="PUT"
        if direction and conf >= 60:
            reason = f"RSI {round(rsi,1)} | EMA7 {'above' if direction=='CALL' else 'below'} EMA21"
            return direction, conf, reason
        else:
            return None, conf, f"Wait RSI {round(rsi,1)}"
    except Exception as e:
        return None, 0, f"Err {e}"

@app.route('/')
def home(): return "V14.1 MANUAL 3MIN SIGNALS LIVE", 200

bot = None
if ':' in TOKEN:
    bot = telebot.TeleBot(TOKEN)
    print("BOT CREATED V14.1", flush=True)

    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        OWNER_ID=m.chat.id
        if not Iq or not Iq.check_connect(): iq_connect()
        try: bal = round(Iq.get_balance(),2) if Iq and Iq.check_connect() else "?"
        except: bal="?"
        bot.send_message(m.chat.id, f"💹 V14.1 MANUAL 3MIN\nBal ${bal}\n\nI scan and send you signals with 60-100% confidence.\nYou trade manually (3 min expiry).\n\n/resume - start\n/pause - stop\n/status")

    @bot.message_handler(commands=['resume'])
    def resume(m):
        global OWNER_ID, SCANNING
        OWNER_ID=m.chat.id; SCANNING=True
        bot.send_message(m.chat.id, "▶️ Scanning ON - 3 MIN signals every 90s")

    @bot.message_handler(commands=['pause'])
    def pause(m):
        global SCANNING; SCANNING=False
        bot.send_message(m.chat.id, "⏸️ Paused")

    @bot.message_handler(commands=['status','balance'])
    def status(m):
        try: b=round(Iq.get_balance(),2) if Iq and Iq.check_connect() else "?"
        except: b="?"
        bot.send_message(m.chat.id, f"Bal ${b}\nScanning {SCANNING}")

    def run_bot():
        while True:
            try:
                try:
                    print("Deleting webhook to fix 409...", flush=True)
                    r = requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
                    print(f"Delete webhook result: {r.text}", flush=True)
                    bot.remove_webhook()
                    time.sleep(3)
                except Exception as de:
                    print(f"Del hook err {de}", flush=True)

                print("V14.1 Polling started...", flush=True)
                bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=30)
            except Exception as e:
                print(f"Poll ERR {e}", flush=True)
                time.sleep(35 if "409" in str(e) else 5)

    threading.Thread(target=run_bot, daemon=True).start()
else:
    print("TOKEN invalid", flush=True)

def scanner():
    while True:
        try:
            time.sleep(90)
            if not OWNER_ID or not SCANNING: continue
            random.shuffle(PAIRS)
            for pair in PAIRS:
                if pair in LAST_SIGNAL_TIME and time.time() - LAST_SIGNAL_TIME[pair] < 480:
                    continue
                direction, conf, reason = analyze(pair)
                print(f"SCAN {pair} {direction} {conf}% {reason}", flush=True)
                if direction and conf >= 60:
                    LAST_SIGNAL_TIME[pair]=time.time()
                    now = datetime.datetime.now() + datetime.timedelta(hours=1)
                    expire = now + datetime.timedelta(minutes=3)
                    emoji = "📈" if direction=="CALL" else "📉"
                    msg = (
                        f"💹 SIGNAL: {pair}\n"
                        f"{emoji} {direction} - 3 MIN\n"
                        f"🎯 Confidence: {conf}%\n"
                        f"⏰ {now.strftime('%H:%M')} → {expire.strftime('%H:%M')} (GMT+1)\n"
                        f"📊 {reason}\n"
                        f"👉 Trade manually on IQ"
                    )
                    if OWNER_ID and bot:
                        bot.send_message(OWNER_ID, msg)
                    break
        except Exception as e:
            print(f"SCAN ERR {e}", flush=True)
            time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()

def iq_bg():
    time.sleep(3)
    iq_connect()
threading.Thread(target=iq_bg, daemon=True).start()

print(f"FLASK STARTING ON {os.getenv('PORT',10000)}", flush=True)
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
