import os, time, threading, random, datetime
from flask import Flask
import telebot

print("=== V14 MANUAL SIGNALS 3MIN ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
EMAIL = (os.getenv("IQ_EMAIL") or "").strip()
PASS = (os.getenv("IQ_PASS") or os.getenv("IQ_PASSWORD") or "").strip()

print(f"TOKEN len={len(TOKEN)} EMAIL={EMAIL}", flush=True)

OWNER_ID = None
Iq = None
SCANNING = True
LAST_SIGNAL_TIME = {} # per pair cooldown
PAIRS = ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDUSD", "EURUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "EURJPY-OTC", "USDJPY-OTC"]

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
    # Calculate confidence 60-100 based on trend strength
    try:
        closes = [c['close'] for c in candles]
        # RSI
        gains=[]; losses=[]
        for i in range(1,len(closes)):
            d=closes[i]-closes[i-1]
            gains.append(max(d,0)); losses.append(max(-d,0))
        period=14
        ag=sum(gains[-period:])/period if len(gains)>=period else 0.01
        al=sum(losses[-period:])/period if len(losses)>=period else 0.01
        if al==0: rsi=70
        else:
            rs=ag/al
            rsi=100-(100/(1+rs))

        # EMA
        def ema(data, p):
            e=data[0]; k=2/(p+1)
            for v in data[1:]: e=v*k+e*(1-k)
            return e
        ema7=ema(closes[-15:],7)
        ema21=ema(closes,21)
        close=closes[-1]

        # Confidence logic
        score=60
        # EMA separation
        diff = abs(ema7-ema21) / close * 1000 # pip diff
        if diff > 0.05: score+=10
        if diff > 0.1: score+=10

        # RSI strength
        if 60 <= rsi <= 70 or 30 <= rsi <= 40: score+=15
        if 65 <= rsi <= 72 or 28 <= rsi <= 35: score+=10

        # Trend alignment
        if (close > ema7 > ema21) or (close < ema7 < ema21): score+=10

        # Cap 60-95
        score = max(60, min(95, int(score + random.randint(-3,3))))
        return score, rsi, ema7, ema21
    except:
        return 60, 50, 0, 0

def analyze(pair):
    try:
        if not Iq or not Iq.check_connect():
            if not iq_connect(): return None, 0, "IQ not connected"
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles)<25: return None, 0, "No data"

        closes = [c['close'] for c in candles]
        ema7 = closes[-1] # simplified reused from confidence
        conf, rsi, ema7, ema21 = get_confidence(candles)
        close = closes[-1]

        # Signal logic for 3 MIN expiry - needs stronger trend
        direction=None
        if close > ema7 and ema7 > ema21 and rsi > 55 and rsi < 78:
            direction="CALL"
        elif close < ema7 and ema7 < ema21 and rsi < 45 and rsi > 22:
            direction="PUT"

        if direction and conf >= 60:
            reason = f"RSI {round(rsi,1)} | EMA7 {'above' if direction=='CALL' else 'below'} EMA21 | Trend {'UP' if direction=='CALL' else 'DOWN'}"
            return direction, conf, reason
        else:
            return None, conf, f"Wait RSI {round(rsi,1)}"
    except Exception as e:
        return None, 0, f"Err {e}"

@app.route('/')
def home(): return "V14 MANUAL SIGNALS 3MIN LIVE", 200

bot = None
if ':' in TOKEN:
    bot = telebot.TeleBot(TOKEN)
    print("BOT CREATED V14", flush=True)

    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        OWNER_ID=m.chat.id
        if not Iq or not Iq.check_connect(): iq_connect()
        try: bal = round(Iq.get_balance(),2) if Iq and Iq.check_connect() else "?"
        except: bal="?"
        bot.send_message(m.chat.id, f"💹 V14 MANUAL SIGNALS\nBal ${bal}\n\nI will scan and send you 3 MIN signals with 60-100% confidence.\nYou trade manually on IQ.\n\nCommands:\n/resume - start scanning\n/pause - stop scanning\n/status - balance")

    @bot.message_handler(commands=['resume'])
    def resume(m):
        global OWNER_ID, SCANNING
        OWNER_ID=m.chat.id; SCANNING=True
        bot.send_message(m.chat.id, "▶️ Scanning ON - You will get 3 MIN signals")

    @bot.message_handler(commands=['pause'])
    def pause(m):
        global SCANNING; SCANNING=False
        bot.send_message(m.chat.id, "⏸️ Scanning paused")

    @bot.message_handler(commands=['status','balance'])
    def status(m):
        try: b=round(Iq.get_balance(),2) if Iq and Iq.check_connect() else "?"
        except: b="?"
        bot.send_message(m.chat.id, f"Bal ${b}\nScanning: {SCANNING}")

    def run_bot():
        while True:
            try:
                bot.remove_webhook(); time.sleep(1)
                print("V14 Polling started...", flush=True)
                bot.infinity_polling(skip_pending=True, timeout=60)
            except Exception as e:
                print(f"Poll {e}", flush=True)
                time.sleep(30 if "409" in str(e) else 5)
    threading.Thread(target=run_bot, daemon=True).start()

def scanner():
    while True:
        try:
            time.sleep(90) # scan every 90 sec for 3 min expiry
            if not OWNER_ID or not SCANNING: continue

            random.shuffle(PAIRS)
            for pair in PAIRS:
                # cooldown per pair 8 min
                if pair in LAST_SIGNAL_TIME and time.time() - LAST_SIGNAL_TIME[pair] < 480:
                    continue

                direction, conf, reason = analyze(pair)
                print(f"SCAN {pair} {direction} {conf}% {reason}", flush=True)

                if direction and conf >= 60:
                    LAST_SIGNAL_TIME[pair]=time.time()
                    now = datetime.datetime.now() + datetime.timedelta(hours=1) # GMT+1
                    expire = now + datetime.timedelta(minutes=3)
                    emoji = "📈" if direction=="CALL" else "📉"

                    msg = (
                        f"💹 SIGNAL: {pair}\n"
                        f"{emoji} {direction} - 3 MIN\n"
                        f"🎯 Confidence: {conf}%\n"
                        f"⏰ {now.strftime('%H:%M')} → {expire.strftime('%H:%M')} (GMT+1)\n"
                        f"📊 {reason}\n"
                        f"👉 Trade manually on IQ Option"
                    )
                    if OWNER_ID and bot:
                        bot.send_message(OWNER_ID, msg)
                    time.sleep(2) # small delay between signals
                    break # send 1 signal at a time, then wait 90 sec
        except Exception as e:
            print(f"SCAN ERR {e}", flush=True)
            time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=lambda: (time.sleep(3), iq_connect()), daemon=True).start()

print(f"FLASK STARTING", flush=True)
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
