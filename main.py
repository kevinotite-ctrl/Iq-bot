import os, time, threading, random, datetime
from flask import Flask
import telebot

print("=== V13.3 FULL FIX ===", flush=True)
app = Flask(__name__)

# Accept BOTH names so you never get len=0
TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
EMAIL = (os.getenv("IQ_EMAIL") or "").strip()
PASS = (os.getenv("IQ_PASS") or os.getenv("IQ_PASSWORD") or "").strip()

print(f"ENV TOKEN len={len(TOKEN)} colon={':' in TOKEN}", flush=True)
print(f"ENV EMAIL={EMAIL} len={len(EMAIL)} PASS len={len(PASS)}", flush=True)

BASE_AMOUNT = 10
MAX_MARTINGALE = 3
current_amount = BASE_AMOUNT
martingale_level = 0
OWNER_ID = None
Iq = None
SCANNING = True
LAST_SIGNAL = 0
RESUME_AT = time.time()

WEEKEND_PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "GBPUSD-OTC", "AUDUSD-OTC", "EURUSD-OTC"]
WEEKDAY_PAIRS = ["EURUSD", "GBPUSD", "EURJPY", "USDJPY", "EURUSD-OTC", "GBPUSD-OTC"]

def get_pairs():
    wd = datetime.datetime.now().weekday()
    return WEEKEND_PAIRS if wd >= 5 else WEEKDAY_PAIRS

def get_rsi(candles, period=14):
    try:
        closes=[c['close'] for c in candles]
        gains=[]; losses=[]
        for i in range(1,len(closes)):
            d=closes[i]-closes[i-1]
            gains.append(max(d,0)); losses.append(max(-d,0))
        if len(gains)<period: return 50
        ag=sum(gains[-period:])/period; al=sum(losses[-period:])/period
        if al==0: return 70
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
        print(f"IQ Trying login {EMAIL}", flush=True)
        Iq = IQ_Option(EMAIL, PASS)
        check, reason = Iq.connect()
        print(f"IQ CONNECT {check} {reason}", flush=True)
        if check:
            Iq.change_balance("PRACTICE")
            bal = Iq.get_balance()
            print(f"IQ BAL ${bal} CONNECTED", flush=True)
            return True
        else:
            print(f"IQ FAILED Reason: {reason}", flush=True)
            return False
    except Exception as e:
        print(f"IQ ERR {e}", flush=True)
        return False

def analyze(pair):
    try:
        candles = Iq.get_candles(pair, 60, 50, time.time())
        if not candles or len(candles)<25: return None, "No candles"
        ema7=get_ema(candles[-15:],7); ema21=get_ema(candles,21); rsi=get_rsi(candles,14); close=candles[-1]['close']
        if close>ema7>ema21 and 55<rsi<75: return "call", f"UP EMA7 {round(ema7,5)} > EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        elif close<ema7<ema21 and 25<rsi<45: return "put", f"DOWN EMA7 {round(ema7,5)} < EMA21 {round(ema21,5)} RSI {round(rsi,1)}"
        else: return None, f"SKIP RSI {round(rsi,1)}"
    except Exception as e: return None, f"Err {e}"

@app.route('/')
def home(): return "V13.3 LIVE - Kevin Bot", 200

bot = None
if ':' in TOKEN:
    bot = telebot.TeleBot(TOKEN)
    print("BOT CREATED V13.3", flush=True)

    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID, RESUME_AT, LAST_SIGNAL, current_amount, martingale_level
        OWNER_ID=m.chat.id; RESUME_AT=time.time(); LAST_SIGNAL=0; current_amount=BASE_AMOUNT; martingale_level=0
        
        if not Iq or not Iq.check_connect():
            bot.send_message(m.chat.id, "⏳ Connecting IQ... wait 8s")
            iq_connect()
            time.sleep(3)

        try:
            if Iq and Iq.check_connect():
                bal = Iq.get_balance()
                mode = Iq.get_balance_mode()
                bot.send_message(m.chat.id, f"🤖 V13.3 MARTINGALE FIXED\n💰 Bal ${round(bal,2)} {mode}\n$10 -> $20 -> $40 reset\n🤑 Win | 😮‍💨 Loss\n/resume /pause /balance")
            else:
                bot.send_message(m.chat.id, f"❌ IQ Login Failed\nBal $?\nEmail: {EMAIL}\nPass len: {len(PASS)}\n\nFix:\n1. Check IQ_EMAIL/IQ_PASS in Render (no spaces)\n2. Login on iqoption.com with same pass\n3. Disable 2FA / Google Auth in IQ Settings\nThen send /start again")
        except Exception as e:
            bot.send_message(m.chat.id, f"Bal error: {e}")
            print(f"BAL ERR {e}", flush=True)

    @bot.message_handler(commands=['resume'])
    def resume(m):
        global OWNER_ID, RESUME_AT, LAST_SIGNAL, SCANNING
        OWNER_ID=m.chat.id; SCANNING=True; RESUME_AT=time.time(); LAST_SIGNAL=0
        if not Iq or not Iq.check_connect(): iq_connect()
        bot.send_message(m.chat.id, f"▶️ RESUMED Lvl {martingale_level} Amt ${current_amount}")

    @bot.message_handler(commands=['pause'])
    def pause(m):
        global SCANNING; SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused")

    @bot.message_handler(commands=['balance','status'])
    def status(m):
        global OWNER_ID; OWNER_ID=m.chat.id
        try:
            b = round(Iq.get_balance(),2) if Iq and Iq.check_connect() else "?"
            mode = Iq.get_balance_mode() if Iq and Iq.check_connect() else ""
            bot.send_message(m.chat.id, f"BAL ${b} {mode}\nAmt ${current_amount} Lvl {martingale_level}/{MAX_MARTINGALE}")
        except Exception as e:
            bot.send_message(m.chat.id, f"BAL error {e}")

    def run_bot():
        while True:
            try:
                bot.remove_webhook()
                time.sleep(1)
                print("V13.3 Polling started...", flush=True)
                bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=30)
            except Exception as e:
                msg = str(e)
                if "409" in msg:
                    print(f"409 Conflict - waiting 30s for old instance to die", flush=True)
                    time.sleep(30)
                else:
                    print(f"Poll ERR {e}", flush=True)
                    time.sleep(5)

    threading.Thread(target=run_bot, daemon=True).start()
else:
    print("TOKEN invalid", flush=True)

def do_trade():
    global LAST_SIGNAL, current_amount, martingale_level
    if (not Iq or not Iq.check_connect()) and not iq_connect():
        if OWNER_ID and bot: bot.send_message(OWNER_ID,"❌ IQ login failed")
        LAST_SIGNAL=time.time(); return
    if not OWNER_ID: return
    PAIRS=get_pairs(); random.shuffle(PAIRS)
    for pair in PAIRS:
        direction, reason = analyze(pair)
        print(f"{pair} {direction} {reason} AMT {current_amount}", flush=True)
        if direction:
            try:
                if bot: bot.send_message(OWNER_ID,f"📊 SIGNAL {pair} {direction.upper()}\nAmt ${current_amount} Lvl {martingale_level}\n{reason}")
                status, trade_id = Iq.buy(current_amount, pair, direction, 1)
                if not status: continue
                if bot: bot.send_message(OWNER_ID,f"✅ BOUGHT {pair} ${current_amount} Lvl {martingale_level}\nWait 65s...")
                time.sleep(65)
                profit=Iq.check_win_v3(trade_id); bal=Iq.get_balance(); LAST_SIGNAL=time.time()
                if profit and profit>0:
                    if bot: bot.send_message(OWNER_ID,f"💰 WIN +${round(profit,2)}\nBal ${round(bal,2)}\n🔄 Reset ${BASE_AMOUNT}\n🤑")
                    current_amount=BASE_AMOUNT; martingale_level=0
                else:
                    martingale_level+=1
                    if martingale_level >= MAX_MARTINGALE:
                        if bot: bot.send_message(OWNER_ID,f"📉 LOSS -${current_amount} RESET to ${BASE_AMOUNT} Bal ${round(bal,2)}\n😮‍💨")
                        current_amount=BASE_AMOUNT; martingale_level=0
                    else:
                        old=current_amount; current_amount=BASE_AMOUNT*(2**martingale_level)
                        if bot: bot.send_message(OWNER_ID,f"📉 LOSS -${old} Next ${current_amount} Lvl {martingale_level} Bal ${round(bal,2)}\n😮‍💨")
                return
            except Exception as e: print(f"BUY ERR {e}", flush=True); continue
    LAST_SIGNAL=time.time()
    if OWNER_ID and bot:
        try: b=round(Iq.get_balance(),2)
        except: b="?"
        bot.send_message(OWNER_ID,f"⏭️ No trend Skip | Amt ${current_amount} Lvl {martingale_level} | Bal ${b}")

def scanner():
    while True:
        try:
            time.sleep(10)
            if not OWNER_ID or not SCANNING: continue
            if time.time() - (RESUME_AT if LAST_SIGNAL==0 else LAST_SIGNAL) < 120: continue
            do_trade()
        except Exception as e: print(f"SCAN ERR {e}", flush=True); time.sleep(5)

threading.Thread(target=scanner, daemon=True).start()

def iq_bg():
    time.sleep(3)
    iq_connect()
threading.Thread(target=iq_bg, daemon=True).start()

print(f"FLASK STARTING ON {os.getenv('PORT',10000)}", flush=True)
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
