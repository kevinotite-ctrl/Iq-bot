import os, time, threading, random
from flask import Flask

print("=== BOT V6.1 GUARANTEED SIGNAL ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

OWNER_ID = None
Iq = None
SCANNING = True

# --- IQ CONNECTION ---
try:
    try:
        from iqoptionapi.stable_api import IQ_Option
    except:
        from iqoptionapi.api import IQ_Option

    print("Connecting IQ...", flush=True)
    Iq = IQ_Option(EMAIL, PASS)
    check, reason = Iq.connect()
    print(f"IQ CONNECT: {check} | {reason}", flush=True)

    if check:
        Iq.change_balance("PRACTICE")
        time.sleep(1)
        print(f"IQ BALANCE PRACTICE: ${Iq.get_balance()}", flush=True)
    else:
        Iq = None
except Exception as e:
    print(f"IQ EXCEPTION: {e}", flush=True)
    Iq = None

@app.route('/')
def home():
    bal = Iq.get_balance() if Iq else "NOT CONNECTED"
    return f"V6.1 AUTO SIGNAL LIVE - BAL: ${bal}"

# --- INDICATORS ---
def get_rsi(prices, period=14):
    if len(prices) < period+1:
        return 50
    gains=[]; losses=[]
    for i in range(1, len(prices)):
        d = prices[i]-prices[i-1]
        gains.append(max(d,0))
        losses.append(max(-d,0))
    ag = sum(gains[-period:])/period
    al = sum(losses[-period:])/period
    if al == 0:
        return 70
    rs = ag/al
    return 100-(100/(1+rs))

def get_ema(prices, period):
    if len(prices) < period:
        return prices[-1]
    k = 2/(period+1)
    ema = sum(prices[:period])/period
    for p in prices[period:]:
        ema = p*k + ema*(1-k)
    return ema

# --- TELEGRAM BOT ---
def run_telegram():
    import telebot
    from telebot import types
    global OWNER_ID, SCANNING

    bot = telebot.TeleBot(TOKEN)
    PAIRS = ["EURUSD-OTC","GBPUSD-OTC","USDJPY-OTC","AUDUSD-OTC","GBPJPY-OTC","EURGBP-OTC","EURJPY-OTC","USDCHF-OTC"]

    @bot.message_handler(commands=['start'])
    def start_cmd(m):
        global OWNER_ID
        OWNER_ID = m.chat.id
        bal = Iq.get_balance() if Iq else "?"
        print(f"OWNER SAVED: {OWNER_ID}", flush=True)
        bot.reply_to(m, f"✅ V6.1 AUTO SIGNAL ACTIVE\nID: {OWNER_ID}\nBalance: ${bal}\n\n🤖 I will
