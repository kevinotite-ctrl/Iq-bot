import os, time, threading, json, logging
from flask import Flask
import telegram
from telegram.ext import Updater, CommandHandler
from iqoptionapi.stable_api import IQ_Option
import ta

# --- ENV ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
IQ_EMAIL = os.getenv("IQ_EMAIL")
IQ_PASSWORD = os.getenv("IQ_PASSWORD")
ACCOUNT_TYPE = os.getenv("ACCOUNT_TYPE", "PRACTICE") # PRACTICE or REAL

app = Flask(__name__)
bot = telegram.Bot(token=BOT_TOKEN)
iq = None
is_scanning = True
memory_file = "memory.json"

logging.basicConfig(level=logging.INFO)

# --- MEMORY ---
def load_memory():
    try:
        with open(memory_file, "r") as f:
            return json.load(f)
    except:
        return {"amount": 10, "level": 0, "last": "None"}

def save_memory(data):
    with open(memory_file, "w") as f:
        json.dump(data, f)

def get_mem_text():
    m = load_memory()
    return f"${m['amount']} Lvl {m['level']}", f"{m['last']} -> {m['level']}"

# --- IQ CONNECT FIXED ---
def connect_iq():
    global iq
    print("Connecting to IQ...", flush=True)
    try:
        iq = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
        check, reason = iq.connect()
        print(f"IQ Connect: {check} | {reason}", flush=True)
        attempt = 0
        while not check and attempt < 3:
            print(f"Retry connect {attempt+1}...", flush=True)
            time.sleep(3)
            check, reason = iq.connect()
            attempt += 1
        if check:
            iq.change_balance(ACCOUNT_TYPE)
            bal = iq.get_balance()
            print(f"IQ Balance: {bal}", flush=True)
            return True
        else:
            print(f"IQ FAILED: {reason}", flush=True)
            return False
    except Exception as e:
        print(f"IQ Exception: {e}", flush=True)
        return False

# --- TELEGRAM COMMANDS ---
def send_msg(text):
    try:
        bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        print(f"Telegram send error: {e}", flush=True)

def cmd_start(update, context):
    amt_text, last_text = get_mem_text()
    bal = "Checking..."
    if iq and iq.check_connect():
        try:
            bal = iq.get_balance()
        except:
            bal = "Error"
    msg = f"✨ 🤖 KEVIN V25 ONLINE + WAKE ROUTE ✨\n\n💾🧠 Memory: {amt_text}\n📊 Last: {last_text}\n\n🔗 Wake link: https://{os.getenv('RENDER_EXTERNAL_HOSTNAME','iq-bot-ba30.onrender.com')}/wake\n📱 Save this link! Open in phone browser to wake bot without Render login! 🚀\n\n🎮 /scan /testbuy /balance /memory /pause"
    send_msg(msg)
    send_msg(f"💰 Balance: ${bal} 💎")
    start_scanning_thread()

def cmd_scan(update, context):
    send_msg("🔍 Scanning now... 👀")
    start_scanning_thread()

def cmd_balance(update, context):
    if not iq or not iq.check_connect():
        connect_iq()
    try:
        bal = iq.get_balance()
        send_msg(f"💰 Balance: ${bal} 💎\nAccount: {ACCOUNT_TYPE}")
    except Exception as e:
        send_msg(f"Balance error: {e}\nTrying reconnect...")
        connect_iq()

def cmd_memory(update, context):
    amt, last = get_mem_text()
    send_msg(f"Memory: {amt}\nLast: {last}")

def cmd_pause(update, context):
    global is_scanning
    is_scanning = False
    send_msg("⏸️ Paused")

def cmd_testbuy(update, context):
    send_msg("🧪 TEST BUY... 🚀")
    if not iq or not iq.check_connect():
        send_msg("IQ not connected, reconnecting...")
        if not connect_iq():
            send_msg("❌ IQ Connect failed. Check email/pass")
            return
    try:
        mem = load_memory()
        amount = mem["amount"]
        # FORCE BUY EURUSD 1min CALL for test
        _, id = iq.buy(amount, "EURUSD", "call", 1)
        if id:
            send_msg(f"✅ TEST BUY PLACED! ID: {id}\nEURUSD CALL ${amount} 1m")
        else:
            send_msg(f"❌ Buy failed. ID none. Balance? {iq.get_balance()}")
    except Exception as e:
        send_msg(f"❌ TEST BUY Error: {e}")
        print(f"Testbuy error: {e}", flush=True)

# --- SCANNING LOGIC ---
PAIRS = ["EURUSD", "GBPUSD", "EURGBP", "USDJPY", "AUDUSD", "USDCAD", "EURJPY", "GBPJPY"]

def get_rsi(pair):
    try:
        candles = iq.get_candles(pair, 60, 100, time.time())
        close = [c['close'] for c in candles]
        if len(close) < 30:
            return 50
        import pandas as pd
        df = pd.DataFrame(close, columns=['close'])
        rsi = ta.momentum.RSIIndicator(df['close'], window=14).rsi().iloc[-1]
        return rsi
    except:
        return 50

def scanning_loop():
    global is_scanning
    count = 0
    while is_scanning:
        if not iq or not iq.check_connect():
            print("IQ disconnected in loop, reconnecting...", flush=True)
            connect_iq()
            time.sleep(5)
            continue
        
        count += 1
        mem = load_memory()
        amt = mem["amount"]
        send_msg(f"🔍 Scanning {count}... 💵 ${amt}")
        
        for pair in PAIRS:
            if not is_scanning:
                break
            try:
                rsi = get_rsi(pair)
                print(f"{pair} RSI {rsi}", flush=True)
                action = None
                if rsi < 30:
                    action = "call"
                elif rsi > 70:
                    action = "put"
                
                if action:
                    send_msg(f"📡 SIGNAL {pair} {action.upper()} ${amt} RSI {round(rsi,1)}")
                    _, buy_id = iq.buy(amt, pair, action, 1)
                    if buy_id:
                        send_msg(f"✅ TRADE PLACED {pair} {action} ID {buy_id}")
                        # wait result
                        time.sleep(65)
                        result = iq.check_win_v4(buy_id)
                        print(f"Result {result}", flush=True)
                        # update memory martingale
                        if result > 0:
                            save_memory({"amount": 10, "level": 0, "last": "WIN"})
                        else:
                            new_amt = amt * 2.2
                            if new_amt > 100: new_amt = 10
                            save_memory({"amount": round(new_amt,2), "level": mem["level"]+1, "last": "LOSS"})
                    else:
                        send_msg(f"❌ Buy failed for {pair}")
            except Exception as e:
                print(f"Scan error {pair}: {e}", flush=True)
            time.sleep(2)
        
        time.sleep(10)

def start_scanning_thread():
    global is_scanning
    is_scanning = True
    t = threading.Thread(target=scanning_loop, daemon=True)
    t.start()

# --- FLASK ROUTES ---
@app.route('/')
def home():
    return "KEVIN V25 LIVE"

@app.route('/wake')
def wake():
    amt, last = get_mem_text()
    msg = f"📱 🌅 WAKE SIGNAL from browser! 🚀\n💵 Amt {amt} Lvl {last.split('->')[-1] if '->' in last else '0'}\n📊 Last {last}\n🔍 Scanning now... 👀"
    send_msg(msg)
    start_scanning_thread()
    return "Woke! Check Telegram"

# --- MAIN ---
if __name__ == "__main__":
    connect_iq()
    # Telegram bot
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", cmd_start))
    dp.add_handler(CommandHandler("scan", cmd_scan))
    dp.add_handler(CommandHandler("testbuy", cmd_testbuy))
    dp.add_handler(CommandHandler("balance", cmd_balance))
    dp.add_handler(CommandHandler("memory", cmd_memory))
    dp.add_handler(CommandHandler("pause", cmd_pause))
    
    updater.start_polling()
    print("Telegram polling started", flush=True)
    
    # initial message
    time.sleep(2)
    try:
        mem_amt, mem_last = get_mem_text()
        send_msg(f"✨ 🤖 KEVIN V25 ONLINE + WAKE ROUTE ✨\n\n💾🧠 Memory: {mem_amt}\n📊 Last: {mem_last}\n\n🔗 Wake link: https://iq-bot-ba30.onrender.com/wake\n📱 Save this link! Open in phone browser to wake bot without Render login! 🚀\n\n🎮 /scan /testbuy /balance /memory /pause")
    except:
        pass
    
    start_scanning_thread()
    app.run(host="0.0.0.0", port=10000)
