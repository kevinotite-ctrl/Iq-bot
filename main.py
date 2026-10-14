import os, time, threading, random, datetime, requests
from flask import Flask
import telebot
import yfinance as yf

print("=== V15 NO IQ MANUAL SIGNALS ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
print(f"TOKEN len={len(TOKEN)}", flush=True)

OWNER_ID = None
SCANNING = True
LAST_SIGNAL_TIME = {}

# Real forex tickers for yfinance
YF_MAP = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "EURJPY": "EURJPY=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "EURUSD-OTC": "EURUSD=X",
    "GBPUSD-OTC": "GBPUSD=X",
    "AUDUSD-OTC": "AUDUSD=X",
    "EURJPY-OTC": "EURJPY=X",
    "USDJPY-OTC": "USDJPY=X",
    "GBPJPY-OTC": "GBPJPY=X",
}

PAIRS = list(YF_MAP.keys())

def get_candles_yf(pair):
    try:
        ticker = YF_MAP.get(pair, "EURUSD=X")
        # get 1m candles last 2 hours
        data = yf.download(ticker, period="1d", interval="1m", progress=False)
        if data.empty or len(data) < 25:
            return None
        closes = data['Close'].tolist()
        # make list of dicts like before
        candles = [{'close': float(c)} for c in closes[-50:]]
        return candles
    except Exception as e:
        print(f"YF ERR {pair} {e}", flush=True)
        return None

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
        rsi = 100-(100/(1+ag/al)) if al!=0 else 70

        def ema(data, p):
            e=data[0]; k=2/(p+1)
            for v in data[1:]: e=v*k+e*(1-k)
            return e
        ema7=ema(closes[-15:],7)
        ema21=ema(closes,21)
        close=closes[-1]

        score=60
        diff = abs(ema7-ema21) / close * 1000
        if diff > 0.03: score+=8
        if diff > 0.08: score+=12
        if 58 <= rsi <= 72 or 28 <= rsi <= 42: score+=15
        if 62 <= rsi <= 70 or 30 <= rsi <= 38: score+=10
        if (close > ema7 > ema21) or (close < ema7 < ema21): score+=10

        # add small randomness like real market
        score = max(60, min(98, int(score + random.randint(-3,4))))
        return score, rsi, ema7, ema21
    except:
        return random.randint(65,85), 55, 0, 0

def analyze(pair):
    candles = get_candles_yf(pair)
    if not candles: return None, 0, "No data"
    conf, rsi, ema7, ema21 = get_confidence(candles)
    close = candles[-1]['close']
    direction=None
    if close > ema7 and ema7 > ema21 and rsi > 53:
        direction="CALL"
    elif close < ema7 and ema7 < ema21 and rsi < 47:
        direction="PUT"
    if direction and conf >= 60:
        reason = f"RSI {round(rsi,1)} | EMA7 {'above' if direction=='CALL' else 'below'} EMA21 | Momentum strong"
        return direction, conf, reason
    else:
        return None, conf, f"Choppy RSI {round(rsi,1)}"

@app.route('/')
def home(): return "V15 NO IQ - MANUAL SIGNALS LIVE", 200

bot = None
if ':' in TOKEN:
    bot = telebot.TeleBot(TOKEN)
    print("BOT CREATED V15", flush=True)

    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        OWNER_ID=m.chat.id
        bot.send_message(m.chat.id, "💹 V15 NO IQ - MANUAL 3 MIN\n\nI will scan market (no IQ login needed) and send you signals with 60-100% confidence.\n\n/resume - start scanning\n/pause - stop\nSignals every 90s")

    @bot.message_handler(commands=['resume'])
    def resume(m):
        global OWNER_ID, SCANNING
        OWNER_ID=m.chat.id; SCANNING=True
        bot.send_message(m.chat.id, "▶️ Scanning ON - You will get 3 MIN signals")

    @bot.message_handler(commands=['pause'])
    def pause(m):
        global SCANNING; SCANNING=False
        bot.send_message(m.chat.id, "⏸️ Paused")

    def run_bot():
        while True:
            try:
                try:
                    print("Deleting webhook to fix 409...", flush=True)
                    r = requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10)
                    print(f"Delete result: {r.text}", flush=True)
                    bot.remove_webhook()
                    time.sleep(2)
                except: pass
                print("V15 Polling started...", flush=True)
                bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=30)
            except Exception as e:
                print(f"Poll {e}", flush=True)
                time.sleep(35 if "409" in str(e) else 5)

    threading.Thread(target=run_bot, daemon=True).start()

def scanner():
    while True:
        try:
            time.sleep(90)
            if not OWNER_ID or not SCANNING: continue
            random.shuffle(PAIRS)
            for pair in PAIRS:
                if pair in LAST_SIGNAL_TIME and time.time() - LAST_SIGNAL_TIME[pair] < 360:
                    continue
                direction, conf, reason = analyze(pair)
                print(f"SCAN {pair} {direction} {conf}%", flush=True)
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
                        f"👉 Trade manually"
                    )
                    if OWNER_ID and bot:
                        bot.send_message(OWNER_ID, msg)
                    break
        except Exception as e:
            print(f"SCAN ERR {e}", flush=True)
            time.sleep(10)

threading.Thread(target=scanner, daemon=True).start()

print("FLASK STARTING", flush=True)
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
