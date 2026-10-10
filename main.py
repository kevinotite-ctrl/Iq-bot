import os
import re
import time
import threading
from flask import Flask

print("=== BOT V5 FINAL - $10 TRADE - CONFIRM & RESULT ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")

OWNER_ID = None

Iq = None
try:
    # Try both import paths
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
    return f"BOT V5 LIVE - $10/TRADA - BAL: ${bal}"

def run_telegram():
    import telebot
    from telebot import types
    global OWNER_ID
    bot = telebot.TeleBot(TOKEN)

    PAIRS = ["EURUSD","GBPUSD","USDJPY","AUDUSD","EURGBP","GBPJPY","USDCHF","EURJPY",
             "EURUSD-OTC","GBPUSD-OTC","USDJPY-OTC","AUDUSD-OTC","EURGBP-OTC","GBPJPY-OTC"]

    @bot.message_handler(commands=['start'])
    def start_cmd(msg):
        global OWNER_ID
        OWNER_ID = msg.chat.id
        bal = Iq.get_balance() if Iq else "Not connected"
        print(f"OWNER ID SAVED: {OWNER_ID}", flush=True)
        bot.reply_to(msg, f"✅ Bot Active - $10 per trade\nYour ID: {OWNER_ID}\nBalance: ${bal}")

    @bot.message_handler(commands=['balance'])
    def bal_cmd(msg):
        b = Iq.get_balance() if Iq else "Not connected"
        bot.reply_to(msg, f"Balance: ${b}")

    def check_win_after(trade_id, pair, direction, chat_id, amount=10):
        print(f"Waiting 65s for {trade_id}...", flush=True)
        time.sleep(65)
        try:
            result = Iq.check_win_v3(trade_id)
            print(f"CHECK WIN {trade_id}: {result}", flush=True)
            bal = Iq.get_balance()
            if isinstance(result, (int, float)):
                if result > 0:
                    bot.send_message(chat_id, f"✅ WIN!\nPair: {pair} {direction.upper()}\nProfit: +${round(result,2)}\nBalance: ${bal}")
                else:
                    bot.send_message(chat_id, f"❌ LOSS!\nPair: {pair} {direction.upper()}\nLost: -${amount}\nBalance: ${bal}")
            elif result == True:
                bot.send_message(chat_id, f"✅ WIN! {pair} {direction.upper()} Balance: ${bal}")
            else:
                bot.send_message(chat_id, f"❌ LOSS! {pair} {direction.upper()} Balance: ${bal}")
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ Finished {pair}. Check IQ. {e}")

    @bot.callback_query_handler(func=lambda c: True)
    def on_confirm(call):
        data = call.data
        if data.startswith("skip_"):
            bot.answer_callback_query(call.id, "Skipped")
            bot.edit_message_text("⏭️ Skipped", call.message.chat.id, call.message.message_id)
            return
        if data.startswith("trade_"):
            _, pair, direction = data.split("_")
            print(f"USER CONFIRMED: {pair} {direction}", flush=True)
            bot.answer_callback_query(call.id, f"Trading {pair}...")
            bot.edit_message_text(f"⏳ Executing {pair} {direction.upper()} $10...", call.message.chat.id, call.message.message_id)
            if not Iq:
                bot.send_message(call.message.chat.id, "❌ IQ not connected!")
                return
            trade_ok = False
            trade_id = None
            last_error = ""
            tried = []
            for p_try in [pair, pair+"-OTC", "EURUSD-OTC", "GBPUSD-OTC"]:
                if p_try in tried: continue
                tried.append(p_try)
                ok, _id = Iq.buy(10, p_try, direction, 1)
                print(f"TRADE EXECUTED: {p_try} {direction} -> {ok} {_id}", flush=True)
                last_error = _id
                if ok:
                    trade_ok = True
                    trade_id = _id
                    pair = p_try
                    break
                if "not available" not in str(_id).lower() and "not open" not in str(_id).lower():
                    break
            if trade_ok:
                bot.send_message(call.message.chat.id, f"🚀 TRADE EXECUTED\nPair: {pair}\nDir: {direction.upper()}\nAmount: $10\nID: {trade_id}\n⏰ Alert in 60s")
                threading.Thread(target=check_win_after, args=(trade_id, pair, direction, call.message.chat.id, 10), daemon=True).start()
            else:
                bot.send_message(call.message.chat.id, f"❌ FAILED: {last_error}")

    @bot.channel_post_handler(func=lambda m: True)
    @bot.message_handler(func=lambda m: True)
    def on_signal(msg):
        global OWNER_ID
        if msg.chat.type == "private":
            OWNER_ID = msg.chat.id
        text = msg.text or msg.caption or ""
        if not text or text.startswith("/"): return
        if "TRADE EXECUTED" in text or "NEW SIGNAL" in text: return
        print(f"CHANNEL MSG: {text}", flush=True)
        upper = text.upper()
        pair = None
        for p in PAIRS:
            if p in upper:
                pair = p
                break
        if not pair:
            mm = re.search(r'([A-Z]{3})[/\s]?([A-Z]{3})', upper)
            if mm: pair = mm.group(1)+mm.group(2)
        if not pair: return
        direction = None
        if any(x in upper for x in ["CALL","BUY","UP","⬆️","GREEN"]): direction = "call"
        elif any(x in upper for x in ["PUT","SELL","DOWN","⬇️","RED"]): direction = "put"
        if not direction: return
        print(f"SIGNAL FOUND: {pair} {direction}", flush=True)
        if not OWNER_ID: return
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(f"✅ TRADE $10 {pair} {direction.upper()}", callback_data=f"trade_{pair}_{direction}"),
            types.InlineKeyboardButton("❌ SKIP", callback_data=f"skip_{pair}")
        )
        bal = Iq.get_balance() if Iq else "?"
        bot.send_message(OWNER_ID, f"📡 NEW SIGNAL\nPair: {pair}\nAction: {direction.upper()}\nAmount: $10\nRaw: {text[:120]}\nBal: ${bal}\nPlace trade?", reply_markup=markup)

    bot.infinity_polling(skip_pending=True)

threading.Thread(target=run_telegram, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))
