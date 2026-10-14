import os, time, threading, datetime
from flask import Flask
import numpy as np

# ===== ENV - NO CRASH IF MISSING =====
TOKEN = os.environ.get("BOT_TOKEN","").strip()
EMAIL = os.environ.get("IQ_EMAIL","").strip()
PASS = os.environ.get("IQ_PASS","").strip()
CHAT_ID = os.environ.get("CHAT_ID","")

print(f"ENV CHECK BOT_TOKEN len={len(TOKEN)} colon={':' in TOKEN}", flush=True)
print(f"ENV CHECK EMAIL len={len(EMAIL)} PASS len={len(PASS)}", flush=True)

app = Flask(__name__)
@app.route('/', methods=['GET','HEAD'])
def home():
    if ':' not in TOKEN:
        return f"ERROR BOT_TOKEN invalid len={len(TOKEN)} - Fix in Render Env", 200
    return "KEVIN V25 FULL PAY CODE LIVE ✅ TRADING", 200

if ':' not in TOKEN:
    print("BOT_TOKEN invalid - Flask only, won't crash", flush=True)
    bot = None
    Iq = None
    running = False
else:
    import telebot
    bot = telebot.TeleBot(TOKEN, threaded=False)
    Iq = None
    running = False
    current_level = 0
    BASE = [10,20,40]
    PAIRS = ["EURUSD-OTC","GBPUSD-OTC","EURGBP-OTC","USDJPY-OTC","AUDUSD-OTC","EURJPY-OTC"]

    # ===== IQ CONNECT =====
    def iq_connect():
        global Iq
        while True:
            try:
                from iqoptionapi.stable_api import IQ_Option
                print("IQ Connecting...", flush=True)
                Iq = IQ_Option(EMAIL, PASS)
                check, reason = Iq.connect()
                print(f"IQ Connected {check} {reason}", flush=True)
                if check:
                    Iq.change_balance("PRACTICE")
                    print(f"BAL ${Iq.get_balance()}", flush=True)
                    return
            except Exception as e:
                print(f"IQ ERR {e}", flush=True)
            time.sleep(15)

    # ===== INDICATORS - YOUR FULL STRATEGY =====
    def get_signal(pair):
        try:
            candles = Iq.get_candles(pair, 60, 50, time.time())
            closes = np.array([c['close'] for c in candles])
            if len(closes) < 25: return None
            ema7 = np.mean(closes[-7:])
            ema21 = np.mean(closes[-21:])
            # RSI
            deltas = np.diff(closes)
            gains = deltas.clip(min=0)
            losses = -deltas.clip(max=0)
            avg_gain = np.mean(gains[-14:])
            avg_loss = np.mean(losses[-14:])
            rsi = 100 if avg_loss==0 else 100 - (100/(1+avg_gain/avg_loss))
            
            print(f"SCAN {pair} EMA7 {ema7:.5f} EMA21 {ema21:.5f} RSI {rsi:.1f}", flush=True)
            if ema7 > ema21 and 55 < rsi < 70: return "call"
            if ema7 < ema21 and 30 < rsi < 45: return "put"
        except Exception as e:
            print(f"SIG ERR {pair} {e}", flush=True)
        return None

    def trade(pair, action):
        global current_level
        amt = BASE[current_level]
        try:
            Iq.buy(amt, pair, action, 1)
            msg = f"📈 Lvl{current_level} ${amt} {pair} {action.upper()}\nEMA7/21 RSI {datetime.datetime.now().strftime('%H:%M:%S')}"
            print(msg, flush=True)
            bot.send_message(CHAT_ID if CHAT_ID else list(bot.get_updates()[-1].message.chat.id) if bot.get_updates() else 0, msg)
            time.sleep(70)
            # check result
            # Simplified win check
            current_level = 0  # Reset after trade, you can add win/loss check later
            bot.send_message(CHAT_ID if CHAT_ID else 0, f"✅ Trade done Reset Lvl 0")
        except Exception as e:
            print(f"TRADE ERR {e}", flush=True)

    # ===== TELEGRAM COMMANDS =====
    @bot.message_handler(commands=['start'])
    def start_cmd(m):
        bal = 0
        try: bal = Iq.get_balance() if Iq else 0
        except: pass
            
      @bot.message_handler(commands=['start','balance'])
      def start_cmd(m):
        print(f"GOT /start from {m.chat.id}", flush=True)
        bal_text = "IQ not connected yet, wait 20s"
        try:
            if Iq and Iq.check_connect():
                b = Iq.get_balance()
                bal_text = f"💰 ${b} PRACTICE"
                print(f"BAL CHECK {b}", flush=True)
            else:
                bal_text = f"IQ status False - still connecting, check IQ_EMAIL/PASS in Render"
        except Exception as e:
            bal_text = f"Bal err {e}"
            print(bal_text, flush=True)
        bot.send_message(m.chat.id, f"🤖 KEVIN V25 FULL PAY CODE\n{bal_text}\n\n/resume - Start\n/pause - Stop\n/balance")
          
    @bot.message_handler(commands=['resume'])
    def resume_cmd(m):
        global running
        running = True
        bot.send_message(m.chat.id, "▶️ RESUMED Scanning every 2 mins...")

    @bot.message_handler(commands=['pause'])
    def pause_cmd(m):
        global running
        running = False
        bot.send_message(m.chat.id, "⏸️ PAUSED")

    @bot.message_handler(commands=['balance'])
    def bal_cmd(m):
        try: bot.send_message(m.chat.id, f"💰 ${Iq.get_balance()} PRACTICE")
        except: bot.send_message(m.chat.id, "IQ not connected yet")

    def trading_loop():
        print("TRADING LOOP FULL STARTED", flush=True)
        while True:
            try:
                if not running or not Iq or not Iq.check_connect():
                    time.sleep(10)
                    continue
                for pair in PAIRS:
                    if not running: break
                    sig = get_signal(pair)
                    if sig:
                        trade(pair, sig)
                        break
                time.sleep(120)
            except Exception as e:
                print(f"LOOP ERR {e}", flush=True)
                time.sleep(10)

    def run_bot():
        while True:
            try:
                print("Trying remove webhook...", flush=True)
                bot.remove_webhook()
                time.sleep(2)
                print("Starting infinity_polling FULL...", flush=True)
                bot.infinity_polling(skip_pending=True, timeout=30)
            except Exception as e:
                print(f"Polling ERR FULL {e}", flush=True)
                time.sleep(5)

    threading.Thread(target=iq_connect, daemon=True).start()
    threading.Thread(target=trading_loop, daemon=True).start()
    threading.Thread(target=run_bot, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
