import os, time, threading, random, datetime, json
from flask import Flask, request
import telebot

print("=== V19.1 BURST FIXED NO ERROR ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")
CHANNEL_ID = -1003709183793

BASE_AMOUNT = 100
MARTINGALE_AMOUNTS = [100, 200, 400]
MAX_MARTINGALE = 3
STATE_FILE = "bot_state.json"
EXPIRY = 2
SCAN_INTERVAL = 75

OWNER_ID = None
Iq = None
SCANNING = True
NEXT_SCAN_AT = time.time() + 45
ALERT_SENT = False
current_amount = BASE_AMOUNT
martingale_level = 0

WEEKEND_PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURJPY-OTC"]
WEEKDAY_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "EURJPY"]

bot = telebot.TeleBot(TOKEN)

def get_min_conf(): return 70
def get_pairs(): return WEEKEND_PAIRS if datetime.datetime.now().weekday()>=5 else WEEKDAY_PAIRS
def get_countdown():
    rem = int(NEXT_SCAN_AT - time.time())
    if rem < 0: rem = 0
    return f"{rem//60:02d}:{rem%60:02d}", rem

def load_state():
    global current_amount, martingale_level
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                martingale_level = data.get('level', 0)
                current_amount = MARTINGALE_AMOUNTS[martingale_level] if martingale_level < len(MARTINGALE_AMOUNTS) else MARTINGALE_AMOUNTS[0]
    except: pass

def save_state():
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({'level': martingale_level, 'amount': current_amount}, f)
    except: pass

def send_private(text):
    try:
        if OWNER_ID: bot.send_message(OWNER_ID, text)
    except: pass

def send_channel(text):
    try: bot.send_message(CHANNEL_ID, text)
    except: pass

# ALL INDICATORS DEFINED AT TOP - NO ERROR
def get_rsi(candles, period=14):
    try:
        closes=[c['close'] for c in candles]; gains=[]; losses=[]
        for i in range(1,len(closes)):
            d=closes[i]-closes[i-1]; gains.append(max(d,0)); losses.append(max(-d,0))
        if len(gains)<period: return 50
        ag=sum(gains[-period:])/period; al=sum(losses[-period:])/period
        if al==0: return 78
        return 100-(100/(1+ag/al))
    except: return 50

def get_ema(candles, period):
    try:
        closes=[c['close'] for c in candles]; ema=closes[0]; k=2/(period+1)
        for p in closes[1:]: ema=p*k+ema*(1-k)
        return ema
    except: return 0

def get_stochastic(candles, k_period=14, d_period=3):
    try:
        if len(candles) < k_period: return 50,50,50
        k_values=[]
        for i in range(k_period, len(candles)+1):
            window=candles[i-k_period:i]
            lows=[c.get('low', c['close']*0.9995) for c in window]
            highs=[c.get('high', c['close']*1.0005) for c in window]
            ll=min(lows); hh=max(highs); close=candles[i-1]['close']
            k=(close-ll)/(hh-ll)*100 if hh!=ll else 50
            k_values.append(k)
        k_cur=k_values[-1]; d_cur=sum(k_values[-d_period:])/d_period if len(k_values)>=d_period else sum(k_values)/len(k_values)
        k_prev=k_values[-2] if len(k_values)>=2 else k_cur
        return k_cur, d_cur, k_prev
    except: return 50,50,50

def iq_connect():
    global Iq
    try:
        from iqoptionapi.stable_api import IQ_Option
        Iq=IQ_Option(EMAIL,PASS)
        chk,_=Iq.connect()
        if chk:
            Iq.change_balance("PRACTICE")
            print(f"IQ CONNECTED BAL {Iq.get_balance()}", flush=True)
            return True
    except Exception as e:
        print(f"IQ FAIL {e}", flush=True)
    return False

def calculate_confidence_burst(ema_gap, k, d, rsi):
    conf=70
    if ema_gap>1.0: conf+=15
    elif ema_gap>0.5: conf+=10
    elif ema_gap>0.2: conf+=5
    if 20<=k<=40 or 60<=k<=80: conf+=12
    if abs(k-d)>3: conf+=8
    if 45<=rsi<=65: conf+=10
    return min(100, max(70, int(conf)))

def analyze_burst(pair):
    try:
        if Iq is None: return None, "IQ not connected", 0, 0
        candles=Iq.get_candles(pair,60,50,time.time())
        if not candles or len(candles)<20: return None,f"No candles {pair}",0,0
        ema7=get_ema(candles[-15:],7); ema14=get_ema(candles[-20:],14)
        rsi=get_rsi(candles,14); k,d,k_prev=get_stochastic(candles,14,3)
        close=candles[-1]['close']; open_p=candles[-1].get('open', close)
        is_green=close>open_p; is_red=close<open_p
        ema_gap=abs(ema7-ema14)/ema14*1000 if ema14!=0 else 0

        if ema7>ema14 and k_prev<d and k>d and k<45 and 40<rsi<72 and is_green and ema_gap>0.15:
            conf=calculate_confidence_burst(ema_gap,k,d,rsi)
            return "call", f"BURST UP EMA7 {round(ema7,5)} > EMA14 Stoch {round(k,1)} UP {round(d,1)} RSI {round(rsi,1)}", conf, rsi
        if ema7<ema14 and k_prev>d and k<d and k>55 and 28<rsi<60 and is_red and ema_gap>0.15:
            conf=calculate_confidence_burst(ema_gap,k,d,rsi)
            return "put", f"BURST DOWN EMA7 {round(ema7,5)} < EMA14 Stoch {round(k,1)} DOWN {round(d,1)} RSI {round(rsi,1)}", conf, rsi
        if ema7>ema14 and k>d and 20<k<50 and 42<rsi<70 and is_green:
            conf=calculate_confidence_burst(ema_gap,k,d,rsi)-5
            if conf>=70: return "call", f"MOMENTUM UP Stoch {round(k,1)}>{round(d,1)} RSI {round(rsi,1)}", conf, rsi
        if ema7<ema14 and k<d and 50<k<80 and 30<rsi<58 and is_red:
            conf=calculate_confidence_burst(ema_gap,k,d,rsi)-5
            if conf>=70: return "put", f"MOMENTUM DOWN Stoch {round(k,1)}<{round(d,1)} RSI {round(rsi,1)}", conf, rsi
        return None,f"WAIT Gap {round(ema_gap,2)} K {round(k,1)} D {round(d,1)} RSI {round(rsi,1)}",0,rsi
    except Exception as e:
        return None,f"Err {e}",0,0

load_state()

@app.route('/')
def home():
    cd,_=get_countdown()
    bal = Iq.get_balance() if Iq else 0
    return f"V19.1 BURST FIXED 70-100% BAL {bal} NEXT {cd}"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str=request.get_data().decode('UTF-8')
        update=telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except: pass
    return "OK",200

@app.route('/setwebhook')
def set_webhook():
    try:
        bot.remove_webhook(); time.sleep(1)
        url=f"{os.getenv('RENDER_EXTERNAL_URL')}/{TOKEN}"
        bot.set_webhook(url=url); return f"Webhook set {url}"
    except Exception as e: return f"Error {e}"

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, NEXT_SCAN_AT, ALERT_SENT
    OWNER_ID=m.chat.id; NEXT_SCAN_AT=time.time()+45; ALERT_SENT=False
    load_state()
    if Iq is None: iq_connect()
    try: bal=round(Iq.get_balance(),2)
    except: bal="?"
    cd,_=get_countdown()
    bot.send_message(m.chat.id, f"🤖 V19.1 BURST FIXED ✅\n70-100% | 4 PAIRS | $100-200-400\nEMA7/14 + Stoch Cross\nPairs: {', '.join(get_pairs())}\nBal ${bal}\nNext ${current_amount} Lvl {martingale_level+1}\nNext in {cd}")

@bot.message_handler(commands=['balance','resume','pause','scan'])
def cmds(m):
    global OWNER_ID, SCANNING, NEXT_SCAN_AT, ALERT_SENT
    if m.text.startswith('/pause'):
        SCANNING=False; send_private("⏸️ Paused"); return
    OWNER_ID=m.chat.id
    if m.text.startswith('/resume'):
        SCANNING=True; NEXT_SCAN_AT=time.time()+45; ALERT_SENT=False; bot.send_message(m.chat.id, "▶️ RESUMED BURST")
    elif m.text.startswith('/balance'):
        try: bal=round(Iq.get_balance(),2); bot.send_message(m.chat.id, f"💰 Bal ${bal} Next ${current_amount} Lvl {martingale_level+1}")
        except: bot.send_message(m.chat.id, "❌ IQ not connected - /start")
    elif m.text.startswith('/scan'):
        do_trade(is_manual=True)

def do_trade(is_manual=False):
    global NEXT_SCAN_AT, ALERT_SENT, current_amount, martingale_level
    if Iq is None and not iq_connect():
        send_private("❌ IQ login failed"); NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False; return
    if not OWNER_ID: return
    PAIRS=get_pairs(); random.shuffle(PAIRS); last_reason=""
    for pair in PAIRS:
        direction, reason, conf, rsi = analyze_burst(pair)
        last_reason = f"{pair}: {reason}"
        if direction and conf>=70:
            try:
                status, trade_id = Iq.buy(current_amount, pair, direction, EXPIRY)
                if not status:
                    send_private(f"❌ Buy FAILED {pair} ${current_amount} - skip channel"); continue
                send_private(f"💥 BURST {conf}% 💯\n💯 {pair} {direction.upper()} {conf}% | ${current_amount} Lvl {martingale_level+1} Exp {EXPIRY}min\n{reason}\n✅ TRADE PLACED!")
                big_dir = "🟢 CALL BURST 🟢\n⬆️ GO UP ⬆️" if direction=="call" else "🔴 PUT BURST 🔴\n⬇️ GO DOWN ⬇️"
                send_channel(f"🔥 BURST SIGNAL - AUTO TRADED ${current_amount} 🔥\n💰 {pair}\n{big_dir}\n⏰ {EXPIRY} MIN\n🎯 {conf}% [70-100%]\n💵 ${current_amount} (L{ martingale_level+1 })\n📊 {reason}\n⚡️ BOT ENTERED ⚡️")
                time.sleep(125)
                profit=Iq.check_win_v3(trade_id); bal=Iq.get_balance(); NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False
                if profit and profit>0:
                    send_private(f"💰 WIN +${round(profit,2)} {conf}% CORRECT Bal ${round(bal,2)}")
                    send_channel(f"💰 WIN +${round(profit,2)} {pair} BURST {conf}% ✅")
                    martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]; save_state()
                else:
                    send_private(f"📉 LOSS -${current_amount} Bal ${round(bal,2)}")
                    send_channel(f"📉 LOSS -${current_amount} {pair} BURST {conf}%")
                    martingale_level+=1
                    if martingale_level>=MAX_MARTINGALE: martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]
                    else: current_amount=MARTINGALE_AMOUNTS[martingale_level]
                    save_state()
                return
            except Exception as e:
                send_private(f"Trade err {e}"); continue
    NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; ALERT_SENT=False
    cd,_=get_countdown()
    if is_manual:
        send_private(f"⏭️ No 70%+ BURST in 4 pairs\nLast: {last_reason}\nRetry {cd}")

def scanner():
    while True:
        try:
            time.sleep(2)
            if not OWNER_ID or not SCANNING: continue
            if time.time() < NEXT_SCAN_AT: continue
            do_trade(is_manual=False)
        except: time.sleep(5)

def countdown_notifier():
    global ALERT_SENT
    while True:
        try:
            time.sleep(1)
            if not OWNER_ID or not SCANNING: continue
            _, rem = get_countdown()
            if rem <= 5 and rem > 0 and not ALERT_SENT:
                send_private(f"‼️ BURST in 5 secs\nNext ${current_amount} Lvl {martingale_level+1} Min 70%")
                ALERT_SENT=True
        except: time.sleep(2)

# START THREADS AND CONNECT ONLY ONCE
threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=countdown_notifier, daemon=True).start()

# Connect safely after definition
try:
    iq_connect()
except: pass

if __name__=="__main__":
    try:
        bot.remove_webhook(); time.sleep(1)
        ext_url=os.getenv("RENDER_EXTERNAL_URL")
        if ext_url: bot.set_webhook(url=f"{ext_url}/{TOKEN}")
    except: pass
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
