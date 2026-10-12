import os, time, threading, random, datetime, json
from flask import Flask, request
import telebot
print("=== V17.2.6 10-20-40 WEBHOOK FIX ===", flush=True)
app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")
CHANNEL_ID = -1003709183793
BASE_AMOUNT = 10
MARTINGALE_AMOUNTS = [10, 20, 40]
MAX_MARTINGALE = 3
STATE_FILE = "bot_state.json"
MIN_CONFIDENCE = 70
EXPIRY = 2
SCAN_INTERVAL = 120
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL") or "https://your-service-name.onrender.com"

def load_state():
    global current_amount, martingale_level
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                martingale_level = data.get('level', 0)
                if martingale_level < len(MARTINGALE_AMOUNTS):
                    current_amount = MARTINGALE_AMOUNTS[martingale_level]
                else:
                    martingale_level = 0
                    current_amount = MARTINGALE_AMOUNTS[0]
                return True
    except: pass
    return False

def save_state():
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({'level': martingale_level, 'amount': current_amount, 'time': time.time()}, f)
    except: pass

current_amount = BASE_AMOUNT
martingale_level = 0
load_state()
OWNER_ID = None
Iq = None
SCANNING = True
LAST_SIGNAL = 0
NEXT_SCAN_AT = time.time() + 60
ALERT_SENT = False

WEEKEND_PAIRS = [
    "EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "GBPJPY-OTC",
    "AUDUSD-OTC", "EURGBP-OTC", "USDJPY-OTC", "AUDJPY-OTC",
    "GBPCHF-OTC", "EURCHF-OTC", "USDCHF-OTC", "NZDUSD-OTC"
]
WEEKDAY_PAIRS = [
    "EURUSD", "GBPUSD", "EURJPY", "USDJPY", "AUDUSD", "USDCAD",
    "EURGBP", "USDCHF", "NZDUSD",
    "EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC", "GBPJPY-OTC"
]

def get_pairs():
    wd = datetime.datetime.now().weekday()
    return WEEKEND_PAIRS if wd >= 5 else WEEKDAY_PAIRS

def get_countdown():
    remaining = int(NEXT_SCAN_AT - time.time())
    if remaining < 0: remaining = 0
    m = remaining // 60
    s = remaining % 60
    return f"{m:02d}:{s:02d}", remaining

bot = telebot.TeleBot(TOKEN)

def send_private(text):
    try:
        if OWNER_ID: bot.send_message(OWNER_ID, text)
    except: pass

def send_channel(text):
    try: bot.send_message(CHANNEL_ID, text)
    except: pass

def send_channel_big_signal(pair, direction, conf, reason):
    if direction == "call":
        big_dir = "🟢🟢🟢🟢🟢\n💹 BUY / CALL 💹💹\n🟢🟢🟢🟢🟢\n⬆️⬆️⬆️ GO UP ⬆️⬆️⬆️"
    else:
        big_dir = "🔴🔴🔴🔴🔴\n📉📉 SELL / PUT 📉📉\n🔴🔴🔴🔴🔴\n⬇️⬇️⬇️ GO DOWN ⬇️⬇️⬇️"
    channel_msg = f"""
🔥🔥🔥🔥🔥🔥
🚀🚀 NEW SIGNAL ALERT 🚀🚀
🔥🔥🔥🔥🔥🔥

💰 PAIR: {pair}
{big_dir}

⏰ EXPIRY: {EXPIRY} MINUTES
🎯 CONFIDENCE: {conf}% 💯
💵 AMOUNT: At your own risk 💰

{reason}

⚡️⚡️ TAKE THE TRADE NOW ⚡️⚡️⚡️
"""
    def delayed():
        time.sleep(10)
        send_channel(channel_msg)
        time.sleep(2)
        guide = f"""
📚 HOW TO PLACE TRADE ON IQ OPTION 📚

1️⃣ Open IQ Option App
2️⃣ Select Asset: {pair}
3️⃣ Set Amount: At your own risk 💰
4️⃣ Set Time: {EXPIRY} Minutes
5️⃣ Click:
{"🟢 GREEN BUTTON (CALL) 🟢" if direction=="call" else "🔴 RED BUTTON (PUT) 🔴"}

⚠️ Trade immediately after signal!
💯 Bot confidence {conf}%

👇 Example below 👇
"""
        send_channel(guide)
        try:
            if os.path.exists("iq_example.jpg"):
                with open("iq_example.jpg", "rb") as photo:
                    bot.send_photo(CHANNEL_ID, photo, caption=f"{pair} {direction.upper()} Example")
        except: pass
    threading.Thread(target=delayed, daemon=True).start()

def get_rsi(candles, period=14):
    try:
        closes=[c['close'] for c in candles]
        gains=[]; losses=[]
        for i in range(1,len(closes)):
            d=closes[i]-closes[i-1]
            gains.append(max(d,0)); losses.append(max(-d,0))
        if len(gains)<period: return 50
        ag=sum(gains[-period:])/period; al=sum(losses[-period:])/period
        if al==0: return 85
        return 100-(100/(1+ag/al))
    except: return 50

def get_ema(candles, period):
    try:
        closes=[c['close'] for c in candles]
        ema=closes[0]; k=2/(period+1)
        for p in closes[1:]: ema=p*k+ema*(1-k)
        return ema
    except: return 0

def calculate_confidence_2min(candles, ema7, ema21, rsi, direction):
    try:
        confidence = 64
        closes=[c['close'] for c in candles]
        gap = abs(ema7-ema21) / ema21 * 1000
        if gap > 1.2: confidence += 20
        elif gap > 0.8: confidence += 15
        elif gap > 0.4: confidence += 9
        elif gap > 0.2: confidence += 5
        if direction=="call":
            if 62 <= rsi <= 67: confidence += 18
            elif 60 <= rsi <= 70: confidence += 12
            elif 56 <= rsi <= 73: confidence += 6
        else:
            if 33 <= rsi <= 38: confidence += 18
            elif 30 <= rsi <= 40: confidence += 12
            elif 27 <= rsi <= 43: confidence += 6
        last_5 = closes[-5:]
        if direction=="call":
            if last_5[0] < last_5[1] < last_5[2] < last_5[3] < last_5[4]: confidence += 14
            elif last_5[1] < last_5[2] < last_5[3] < last_5[4]: confidence += 9
            elif last_5[2] < last_5[3] < last_5[4]: confidence += 5
        else:
            if last_5[0] > last_5[1] > last_5[2] > last_5[3] > last_5[4]: confidence += 14
            elif last_5[1] > last_5[2] > last_5[3] > last_5[4]: confidence += 9
            elif last_5[2] > last_5[3] > last_5[4]: confidence += 5
        return min(100, max(60, int(confidence)))
    except: return 80

def iq_connect():
    global Iq
    try:
        from iqoptionapi.stable_api import IQ_Option
        Iq = IQ_Option(EMAIL, PASS)
        check, reason = Iq.connect()
        if check:
            Iq.change_balance("PRACTICE")
            return True
    except: pass
    return False

def analyze(pair):
    try:
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles)<25: return None, "No candles", 0
        ema7=get_ema(candles[-15:],7); ema21=get_ema(candles,21); rsi=get_rsi(candles,14); close=candles[-1]['close']
        if close>ema7>ema21 and 56<rsi<73:
            conf = calculate_confidence_2min(candles, ema7, ema21, rsi, "call")
            return "call", f"2-MIN UP EMA7 {round(ema7,5)} > EMA21 {round(ema21,5)} RSI {round(rsi,1)}", conf
        elif close<ema7<ema21 and 27<rsi<44:
            conf = calculate_confidence_2min(candles, ema7, ema21, rsi, "put")
            return "put", f"2-MIN DOWN EMA7 {round(ema7,5)} < EMA21 {round(ema21,5)} RSI {round(rsi,1)}", conf
        else:
            return None, f"SKIP RSI {round(rsi,1)}", 0
    except: return None, f"Err", 0

iq_connect()

@app.route('/')
def home():
    cd,_ = get_countdown()
    return f"V17.2.6 10-20-40 LIVE {len(get_pairs())} pairs BAL {Iq.get_balance() if Iq else 'NO IQ'} NEXT {cd}"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except: pass
    return "OK", 200

@app.route('/setwebhook')
def set_webhook():
    try:
        bot.remove_webhook()
        time.sleep(1)
        url = f"{RENDER_URL}/{TOKEN}"
        bot.set_webhook(url=url)
        return f"Webhook set to {url}"
    except Exception as e:
        return f"Error {e}"

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, NEXT_SCAN_AT
    OWNER_ID=m.chat.id; RESUME_AT=time.time(); LAST_SIGNAL=0; NEXT_SCAN_AT=time.time()+60
    load_state()
    if not Iq: iq_connect()
    try: bal=round(Iq.get_balance(),2)
    except: bal="?"
    cd,_ = get_countdown()
    bot.send_message(m.chat.id, f"🤖 V17.2.6 10-20-40 ✅\nPairs: {len(get_pairs())}\nBal ${bal}\nNext ${current_amount} Lvl {martingale_level}\n⏳ Next in {cd}")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING, NEXT_SCAN_AT
    OWNER_ID=m.chat.id; SCANNING=True; RESUME_AT=time.time(); LAST_SIGNAL=0; NEXT_SCAN_AT=time.time()+60
    load_state()
    if not Iq: iq_connect()
    cd,_ = get_countdown()
    send_private(f"▶️ RESUMED {len(get_pairs())} pairs\nSaved ${current_amount} Lvl {martingale_level}\n⏳ Next in {cd}")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING; SCANNING=False; send_private("⏸️ Paused")

@bot.message_handler(commands=['scan'])
def scan(m):
    global OWNER_ID; OWNER_ID=m.chat.id; do_trade()

def do_trade():
    global LAST_SIGNAL, current_amount, martingale_level, NEXT_SCAN_AT, ALERT_SENT
    if not Iq and not iq_connect():
        send_private("❌ IQ login failed")
        LAST_SIGNAL=time.time(); NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False; return
    if not OWNER_ID: return
    PAIRS=get_pairs(); random.shuffle(PAIRS)
    for pair in PAIRS:
        direction, reason, conf = analyze(pair)
        if direction:
            if conf < MIN_CONFIDENCE: continue
            try:
                private_msg = f"Bot confidence rate >> {conf}% 💯\n💯 {pair} {direction.upper()} {conf}% | ${current_amount} Lvl {martingale_level} Exp {EXPIRY}min\n{reason}"
                send_private(private_msg)
                send_channel_big_signal(pair, direction, conf, reason)
                status, trade_id = Iq.buy(current_amount, pair, direction, EXPIRY)
                if not status: continue
                send_private(f"✅ BOUGHT {pair} {direction.upper()} ${current_amount} Lvl {martingale_level} Conf {conf}% Exp {EXPIRY}min\n⏳ Wait 125s...")
                time.sleep(125)
                profit=Iq.check_win_v3(trade_id); bal=Iq.get_balance(); LAST_SIGNAL=time.time(); NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False
                cd,_ = get_countdown()
                if profit and profit>0:
                    result = f"💰 WIN +${round(profit,2)} Bot confidence rate >> {conf}% CORRECT 💯\nBal ${round(bal,2)}\n🔄 Reset to $10\n⏳ Next in {cd}"
                    send_private(result); send_private("🤑")
                    send_channel(result); send_channel("🤑")
                    martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]; save_state()
                else:
                    result = f"📉 LOSS -${current_amount} Bot confidence rate >> {conf}% FAILED\nBal ${round(bal,2)}\n⏳ Next in {cd}"
                    send_private(result); send_private("😮‍💨")
                    send_channel(result); send_channel("😮‍💨")
                    martingale_level+=1
                    if martingale_level >= MAX_MARTINGALE:
                        result_reset = f"🔄 Max martingale reached. Resetting to ${MARTINGALE_AMOUNTS[0]}"
                        send_private(result_reset)
                        martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]
                    else:
                        current_amount=MARTINGALE_AMOUNTS[martingale_level]
                        send_private(f"📈 Next ${current_amount} Lvl {martingale_level}")
                    save_state()
                def we_go_again():
                    time.sleep(3)
                    send_channel("We go again ‼️‼️💯")
                threading.Thread(target=we_go_again, daemon=True).start()
                return
            except: continue
    LAST_SCAN_TIME = time.time()
    LAST_SIGNAL=time.time(); NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False
    cd,_ = get_countdown()
    try: bal=round(Iq.get_balance(),2)
    except: bal="?"
    send_private(f"⏭️ No 85-100% signal scanned {len(PAIRS)} pairs | Next ${current_amount} Lvl {martingale_level} | Bal ${bal}\n⏳ Next in {cd}")

def scanner():
    while True:
        try:
            time.sleep(2)
            if not OWNER_ID or not SCANNING: continue
            if time.time() < NEXT_SCAN_AT: continue
            do_trade()
        except: time.sleep(5)

def countdown_notifier():
    global ALERT_SENT
    last_notified = 0
    while True:
        try:
            time.sleep(1)
            if not OWNER_ID or not SCANNING: continue
            cd, rem = get_countdown()
            if rem <= 5 and rem > 0 and not ALERT_SENT:
                send_private(f"‼️Signal alert incoming ‼️\n💯Get Ready 💯\n5 secs to receiving the signal\nNext ${current_amount} Lvl {martingale_level}")
                ALERT_SENT = True
                last_notified = time.time()
                continue
            if rem in [90][60][30] and time.time() - last_notified > 25:
                send_private(f"⏳ Next session in {cd}\nGet ready! Next ${current_amount} Lvl {martingale_level}")
                last_notified = time.time()
        except: time.sleep(2)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=countdown_notifier, daemon=True).start()

if __name__=="__main__":
    try:
        bot.remove_webhook()
        time.sleep(1)
        ext_url = os.getenv("RENDER_EXTERNAL_URL")
        if ext_url:
            bot.set_webhook(url=f"{ext_url}/{TOKEN}")
            print(f"Webhook set to {ext_url}/{TOKEN[:10]}...", flush=True)
    except Exception as e:
        print(f"Webhook set err {e}", flush=True)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
