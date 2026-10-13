import os, time, threading, random, datetime, json
from flask import Flask, request
import telebot
print("=== V17.4.2 BALANCE FIX + 3 PAIRS + RSI 30-70 ===", flush=True)
app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")
CHANNEL_ID = -1003709183793
BASE_AMOUNT = 10
MARTINGALE_AMOUNTS = [10, 20, 40]
MAX_MARTINGALE = 3
STATE_FILE = "bot_state.json"
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

# 3 PAIRS ONLY - OTC 24/7 NO "ASSET NOT AVAILABLE" ERROR
WEEKEND_PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC"]
WEEKDAY_PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC"]

def get_pairs():
    return WEEKEND_PAIRS # Always OTC

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

def send_channel_big_signal(pair, direction, reason):
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
        if al==0: return 50
        return 100-(100/(1+ag/al))
    except: return 50

def get_ema(candles, period):
    try:
        closes=[c['close'] for c in candles]
        ema=closes[0]; k=2/(period+1)
        for p in closes[1:]: ema=p*k+ema*(1-k)
        return ema
    except: return 0

def iq_connect():
    global Iq
    try:
        from iqoptionapi.stable_api import IQ_Option
        Iq = IQ_Option(EMAIL, PASS)
        check, reason = Iq.connect()
        if check:
            Iq.change_balance("PRACTICE")
            return True
    except Exception as e:
        print(f"IQ connect failed {e}", flush=True)
    return False

def get_safe_balance():
    global Iq
    try:
        if not Iq:
            iq_connect()
        return round(Iq.get_balance(), 2)
    except:
        try:
            iq_connect()
            time.sleep(1)
            return round(Iq.get_balance(), 2)
        except:
            return "RECONNECTING"

def analyze(pair):
    try:
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles)<25: return None, "No candles"
        ema7=get_ema(candles[-15:],7); ema21=get_ema(candles,21); rsi=get_rsi(candles,14); close=candles[-1]['close']
        if close>ema7>ema21 and 30<rsi<70:
            return "call", f"UP EMA7 {round(ema7,5)} > EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        elif close<ema7<ema21 and 30<rsi<70:
            return "put", f"DOWN EMA7 {round(ema7,5)} < EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        else:
            return None, f"SKIP RSI {round(rsi,1)}"
    except: return None, f"Err"

iq_connect()

@app.route('/')
def home():
    cd,_ = get_countdown()
    bal = get_safe_balance()
    return f"V17.4.2 LIVE {len(get_pairs())} pairs BAL {bal} NEXT {cd}"

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
    global OWNER_ID, LAST_SIGNAL, NEXT_SCAN_AT
    OWNER_ID=m.chat.id; LAST_SIGNAL=0; NEXT_SCAN_AT=time.time()+60
    load_state()
    bal = get_safe_balance()
    cd,_ = get_countdown()
    bot.send_message(m.chat.id, f"🤖 V17.4.2 RSI 30-70 ✅\nPairs: {len(get_pairs())}\nBal ${bal}\nNext ${current_amount} Lvl {martingale_level}\n⏳ Next in {cd}")

@bot.message_handler(commands=['balance'])
def balance_cmd(m):
    global OWNER_ID
    OWNER_ID=m.chat.id
    bal = get_safe_balance()
    status = "✅ Connected" if "RECONNECTING" not in str(bal) else "❌ Reconnecting..."
    bot.send_message(m.chat.id, f"💰 Balance: ${bal}\n{status}\nNext: ${current_amount} Lvl {martingale_level}")

@bot.message_handler(commands=['resume'])
def resume(m):
    global OWNER_ID, LAST_SIGNAL, SCANNING, NEXT_SCAN_AT
    OWNER_ID=m.chat.id; SCANNING=True; LAST_SIGNAL=0; NEXT_SCAN_AT=time.time()+60
    load_state()
    iq_connect()
    time.sleep(1)
    bal = get_safe_balance()
    cd,_ = get_countdown()
    send_private(f"▶️ RESUMED {len(get_pairs())} pairs\nBal ${bal}\nSaved ${current_amount} Lvl {martingale_level}\n⏳ Next in {cd}")

@bot.message_handler(commands=['pause'])
def pause(m):
    global SCANNING; SCANNING=False; send_private("⏸️ Paused")

@bot.message_handler(commands=['scan'])
def scan(m):
    global OWNER_ID; OWNER_ID=m.chat.id; do_trade()

def do_trade():
    global LAST_SIGNAL, current_amount, martingale_level, NEXT_SCAN_AT, ALERT_SENT
    if not Iq and not iq_connect():
        send_private("❌ IQ login failed - retrying next cycle")
        LAST_SIGNAL=time.time(); NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False; return
    if not OWNER_ID: return
    PAIRS=get_pairs(); random.shuffle(PAIRS)
    found_signal = False
    for pair in PAIRS:
        direction, reason = analyze(pair)
        if direction:
            found_signal = True
            try:
                # TRADE FIRST
                status, trade_id = Iq.buy(current_amount, pair, direction, EXPIRY)
                if not status:
                    err = str(trade_id)[:80] if trade_id else "Asset closed"
                    send_private(f"⚠️ {pair} {direction.upper()} found but IQ rejected: {err}")
                    continue

                private_msg = f"✅ TRADE PLACED {pair} {direction.upper()}\n💯 {pair} {direction.upper()} | ${current_amount} Lvl {martingale_level} Exp {EXPIRY}min\n{reason}"
                send_private(private_msg)
                send_channel_big_signal(pair, direction, reason)

                send_private(f"⏳ Wait 125s for result...")
                time.sleep(125)
                profit=Iq.check_win_v3(trade_id); bal=get_safe_balance(); LAST_SIGNAL=time.time(); NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False
                cd,_ = get_countdown()
                if profit and profit>0:
                    result = f"💰 WIN +${round(profit,2)} ✅\nBal ${bal}\n🔄 Reset to $10\n⏳ Next in {cd}"
                    send_private(result); send_private("🤑")
                    send_channel(result); send_channel("🤑")
                    martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]; save_state()
                else:
                    result = f"📉 LOSS -${current_amount} ❌\nBal ${bal}\n⏳ Next in {cd}"
                    send_private(result); send_private("😮‍💨")
                    send_channel(result); send_channel("😮‍💨")
                    martingale_level+=1
                    if martingale_level >= MAX_MARTINGALE:
                        send_private(f"🔄 Max martingale reached. Resetting to ${MARTINGALE_AMOUNTS[0]}")
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
            except Exception as e:
                send_private(f"Error {e}")
                continue

    LAST_SIGNAL=time.time(); NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False
    cd,_ = get_countdown()
    bal = get_safe_balance()
    if found_signal:
        send_private(f"⚠️ Signal found but all buys failed | Bal ${bal}\n⏳ Next in {cd}")
    else:
        send_private(f"⏭️ No RSI 30-70 signal scanned {len(PAIRS)} pairs | Next ${current_amount} Lvl {martingale_level} | Bal ${bal}\n⏳ Next in {cd}")

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
            if rem in [90,60,30] and time.time() - last_notified > 25:
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
