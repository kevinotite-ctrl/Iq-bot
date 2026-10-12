import os, time, threading, random, datetime, json
from flask import Flask, request
import telebot

print("=== V20.1 SIMPLE + DAILY SUMMARY ===", flush=True)
app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EMAIL = os.getenv("IQ_EMAIL")
PASS = os.getenv("IQ_PASSWORD")
CHANNEL_ID = -1003709183793

BASE_AMOUNT = 100
MARTINGALE_AMOUNTS = [100, 200, 400]
MAX_MARTINGALE = 3
STATE_FILE = "bot_state.json"
DAILY_FILE = "daily_trades.json"
EXPIRY = 2
SCAN_INTERVAL = 30

OWNER_ID = None
Iq = None
SCANNING = True
NEXT_SCAN_AT = time.time() + 60
current_amount = BASE_AMOUNT
martingale_level = 0
DAILY_LOSS = 0
MAX_DAILY_LOSS = 600

WEEKEND_PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURJPY-OTC"]
WEEKDAY_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "EURJPY"]

bot = telebot.TeleBot(TOKEN)

def get_pairs(): return WEEKEND_PAIRS if datetime.datetime.now().weekday()>=5 else WEEKDAY_PAIRS
def get_countdown():
    rem = int(NEXT_SCAN_AT - time.time())
    return f"{rem//60:02d}:{rem%60:02d}", rem

def load_state():
    global current_amount, martingale_level
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE,'r') as f:
                d=json.load(f)
                martingale_level=d.get('level',0)
                current_amount=MARTINGALE_AMOUNTS[martingale_level] if martingale_level <3 else 100
    except: pass

def save_state():
    try:
        with open(STATE_FILE,'w') as f: json.dump({'level':martingale_level}, f)
    except: pass

# DAILY SUMMARY LOGIC
def get_today_key(): return datetime.datetime.now().strftime("%Y-%m-%d")

def load_daily():
    try:
        if os.path.exists(DAILY_FILE):
            with open(DAILY_FILE,'r') as f: return json.load(f)
    except: pass
    return {}

def save_daily(data):
    try:
        with open(DAILY_FILE,'w') as f: json.dump(data,f)
    except: pass

def log_trade(pair, direction, amount, conf, result, profit):
    try:
        data=load_daily()
        key=get_today_key()
        if key not in data:
            data[key]={'trades':[], 'wins':0, 'losses':0, 'profit':0, 'total':0}
        data[key]['trades'].append({
            'time': datetime.datetime.now().strftime("%H:%M"),
            'pair': pair,
            'dir': direction,
            'amount': amount,
            'conf': conf,
            'result': result,
            'profit': profit
        })
        data[key]['total']+=1
        if result=='WIN': data[key]['wins']+=1
        else: data[key]['losses']+=1
        data[key]['profit']+=profit if profit else -amount if result=='LOSS' else 0
        save_daily(data)
    except: pass

def get_daily_summary(date_key=None):
    data=load_daily()
    key=date_key or get_today_key()
    if key not in data or data[key]['total']==0:
        return f"📊 No trades on {key}"
    d=data[key]
    winrate = round(d['wins']/d['total']*100,1) if d['total']>0 else 0
    # Build trade list
    trade_lines=""
    for t in d['trades'][-10:]: # last 10
        emoji="✅" if t['result']=='WIN' else "❌"
        trade_lines+=f"{emoji} {t['time']} {t['pair']} {t['dir']} ${t['amount']} {t['conf']}% {t['result']} {t['profit']:+}\n"

    summary = f"""📊 DAILY SUMMARY - {key}
━━━━━━━━━━━━━━━━━━
💼 Total Trades: {d['total']}
✅ Wins: {d['wins']}
❌ Losses: {d['losses']}
📈 Win Rate: {winrate}%
💰 Profit: ${round(d['profit'],2)}

📝 Last Trades:
{trade_lines}
━━━━━━━━━━━━━━━━━━
Next: ${current_amount} Lvl {martingale_level+1}"""
    return summary

def send_private(t):
    try:
        if OWNER_ID: bot.send_message(OWNER_ID, t)
    except: pass
def send_channel(t):
    try: bot.send_message(CHANNEL_ID, t)
    except: pass

def get_ema(closes, period):
    try:
        ema=closes[0]; k=2/(period+1)
        for c in closes[1:]: ema=c*k+ema*(1-k)
        return ema
    except: return 0
def get_rsi(closes, period=14):
    try:
        gains=[]; losses=[]
        for i in range(1,len(closes)):
            d=closes[i]-closes[i-1]
            gains.append(max(d,0)); losses.append(max(-d,0))
        if len(gains)<period: return 50
        ag=sum(gains[-period:])/period; al=sum(losses[-period:])/period
        if al==0: return 70
        return 100-(100/(1+ag/al))
    except: return 50

def iq_connect():
    global Iq
    try:
        from iqoptionapi.stable_api import IQ_Option
        Iq=IQ_Option(EMAIL,PASS)
        ok,_=Iq.connect()
        if ok:
            Iq.change_balance("PRACTICE")
            print(f"IQ OK {Iq.get_balance()}", flush=True)
            return True
    except Exception as e:
        print(f"IQ FAIL {e}", flush=True)
    return False

def analyze_simple(pair):
    try:
        if Iq is None: return None, "No IQ", 0
        candles=Iq.get_candles(pair,60,60,time.time())
        if not candles or len(candles)<50: return None, f"No candles {pair}",0
        closes=[c['close'] for c in candles]
        ema20=get_ema(closes[-30:],20)
        ema50=get_ema(closes,50)
        rsi=get_rsi(closes,14)
        close=closes[-1]; open_p=candles[-1].get('open',close)
        high=max(closes[-10:]); low=min(closes[-10:])
        volatility = (high-low)/close*1000
        if volatility < 0.4: return None, f"FLAT vol {round(volatility,2)} SKIP", 0
        ema_gap = abs(ema20-ema50)/ema50*1000
        if ema_gap < 0.2: return None, f"Weak gap {round(ema_gap,2)} SKIP",0
        if close>ema20 and ema20>ema50:
            dist = abs(close-ema20)/close*1000
            if dist < 0.6 and 45<=rsi<=68 and close>open_p:
                conf=78
                if ema_gap>0.8: conf+=10
                elif ema_gap>0.5: conf+=7
                if 50<=rsi<=62: conf+=8
                if dist<0.3: conf+=6
                conf=min(95,conf)
                if conf>=75: return "call", f"SIMPLE UP EMA20 {round(ema20,5)} > EMA50 Pullback {round(dist,2)} RSI {round(rsi,1)}", conf
        if close<ema20 and ema20<ema50:
            dist = abs(close-ema20)/close*1000
            if dist < 0.6 and 32<=rsi<=55 and close<open_p:
                conf=78
                if ema_gap>0.8: conf+=10
                elif ema_gap>0.5: conf+=7
                if 38<=rsi<=50: conf+=8
                if dist<0.3: conf+=6
                conf=min(95,conf)
                if conf>=75: return "put", f"SIMPLE DOWN EMA20 {round(ema20,5)} < EMA50 Pullback {round(dist,2)} RSI {round(rsi,1)}", conf
        return None, f"WAIT EMA20 {round(ema20,5)} EMA50 {round(ema50,5)} RSI {round(rsi,1)}", 0
    except Exception as e:
        return None, f"Err {e}",0

load_state()
iq_connect()

@app.route('/')
def home():
    cd,_=get_countdown(); bal=Iq.get_balance() if Iq else 0
    return f"V20.1 SIMPLE+SUMMARY {bal} NEXT {cd}"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try: bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode('UTF-8'))])
    except: pass
    return "OK",200

@app.route('/setwebhook')
def set_webhook():
    try:
        bot.remove_webhook(); time.sleep(1)
        url=f"{os.getenv('RENDER_EXTERNAL_URL')}/{TOKEN}"
        bot.set_webhook(url=url); return f"Set {url}"
    except Exception as e: return f"Err {e}"

@bot.message_handler(commands=['start'])
def start(m):
    global OWNER_ID, NEXT_SCAN_AT
    OWNER_ID=m.chat.id; NEXT_SCAN_AT=time.time()+60; load_state()
    if Iq is None: iq_connect()
    bal=round(Iq.get_balance(),2) if Iq else "?"
    cd,_=get_countdown()
    bot.send_message(m.chat.id, f"🤖 V20.1 SIMPLE + SUMMARY ✅\nEMA20+EMA50+RSI Vol Filter\nPairs: {', '.join(get_pairs())}\nBal ${bal}\nNext ${current_amount} Lvl {martingale_level+1}\nNext in {cd}\n\nCommands:\n/summary - Today report\n/yesterday - Yesterday\n/balance - Balance\n/reset - Reset Lvl")

@bot.message_handler(commands=['balance','resume','pause','scan','reset','summary','today','yesterday','report','daily'])
def cmds(m):
    global OWNER_ID, SCANNING, NEXT_SCAN_AT, DAILY_LOSS, martingale_level, current_amount
    OWNER_ID=m.chat.id
    txt=m.text.lower()
    if '/pause' in txt: SCANNING=False; send_private("⏸️ Paused"); return
    if '/resume' in txt: SCANNING=True; NEXT_SCAN_AT=time.time()+60; bot.send_message(m.chat.id, "▶️ RESUMED")
    elif '/balance' in txt:
        try: bal=round(Iq.get_balance(),2); bot.send_message(m.chat.id, f"💰 Bal ${bal} Next ${current_amount} Daily Loss ${DAILY_LOSS}/{MAX_DAILY_LOSS}\n\n{get_daily_summary()}")
        except: bot.send_message(m.chat.id, "❌ IQ not connected")
    elif '/reset' in txt:
        martingale_level=0; current_amount=100; DAILY_LOSS=0; save_state(); bot.send_message(m.chat.id, "🔄 Reset $100")
    elif '/scan' in txt: do_trade(is_manual=True)
    elif 'summary' in txt or 'today' in txt or 'daily' in txt or 'report' in txt:
        bot.send_message(m.chat.id, get_daily_summary())
        try:
            bal=round(Iq.get_balance(),2)
            bot.send_message(CHANNEL_ID, f"📊 DAILY UPDATE {get_today_key()}\n{get_daily_summary()}\nBal ${bal}")
        except: pass
    elif 'yesterday' in txt:
        y=(datetime.datetime.now()-datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        bot.send_message(m.chat.id, get_daily_summary(y))

def do_trade(is_manual=False):
    global NEXT_SCAN_AT, current_amount, martingale_level, DAILY_LOSS
    if Iq is None and not iq_connect():
        send_private("❌ IQ login failed"); NEXT_SCAN_AT=time.time()+SCAN_INTERVAL; return
    if not OWNER_ID: return
    if DAILY_LOSS >= MAX_DAILY_LOSS:
        send_private(f"🛑 DAILY STOP ${DAILY_LOSS} reached - /reset to continue"); NEXT_SCAN_AT=time.time()+3600; return
    PAIRS=get_pairs(); random.shuffle(PAIRS); last_reason=""
    for pair in PAIRS:
        direction, reason, conf = analyze_simple(pair)
        last_reason=f"{pair}: {reason}"
        if direction and conf>=75:
            try:
                status, trade_id = Iq.buy(current_amount, pair, direction, EXPIRY)
                if not status:
                    send_private(f"❌ Buy FAILED {pair} ${current_amount}"); continue
                send_private(f"✅ SIMPLE {conf}% 💯\n💯 {pair} {direction.upper()} {conf}% | ${current_amount} Lvl {martingale_level+1}\n{reason}")
                big_dir = "🟢 CALL UP 🟢" if direction=="call" else "🔴 PUT DOWN 🔴"
                send_channel(f"🔥 SIMPLE ${current_amount} 🔥\n💰 {pair}\n{big_dir}\n⏰ {EXPIRY} MIN\n🎯 {conf}%\n💵 ${current_amount}\n📊 {reason}")
                time.sleep(125)
                profit=Iq.check_win_v3(trade_id); bal=Iq.get_balance(); NEXT_SCAN_AT=time.time()+SCAN_INTERVAL
                if profit and profit>0:
                    send_private(f"💰 WIN +${round(profit,2)} {conf}% Bal ${round(bal,2)}")
                    send_channel(f"💰 WIN +${round(profit,2)} {pair} {conf}% ✅")
                    log_trade(pair, direction.upper(), current_amount, conf, 'WIN', round(profit,2))
                    martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]; save_state()
                else:
                    DAILY_LOSS+=current_amount
                    send_private(f"📉 LOSS -${current_amount} Bal ${round(bal,2)} Daily -${DAILY_LOSS}")
                    send_channel(f"📉 LOSS -${current_amount} {pair} {conf}%")
                    log_trade(pair, direction.upper(), current_amount, conf, 'LOSS', -current_amount)
                    martingale_level+=1
                    if martingale_level>=MAX_MARTINGALE: martingale_level=0; current_amount=MARTINGALE_AMOUNTS[0]
                    else: current_amount=MARTINGALE_AMOUNTS[martingale_level]
                    save_state()
                return
            except Exception as e:
                send_private(f"Trade err {e}"); continue
    NEXT_SCAN_AT=time.time()+SCAN_INTERVAL
    if is_manual: send_private(if is_manual: send_private(f"⏭️ No SIMPLE signal\nLast: {last_reason}\nNext 00:30 - Good, avoiding bad trades"))

def scanner():
    while True:
        try:
            time.sleep(2)
            if not OWNER_ID or not SCANNING: continue
            if time.time() < NEXT_SCAN_AT: continue
            do_trade(False)
        except: time.sleep(5)

def daily_auto_reporter():
    sent_today=""
    while True:
        try:
            time.sleep(60)
            now=datetime.datetime.now()
            # Auto send at 23:59 Lagos time
            if now.hour==23 and now.minute==59 and get_today_key()!=sent_today:
                if OWNER_ID:
                    summary=get_daily_summary()
                    send_private(f"🌙 END OF DAY AUTO SUMMARY\n{summary}")
                    send_channel(f"🌙 END OF DAY - {get_today_key()}\n{summary}")
                    sent_today=get_today_key()
            # Reset DAILY_LOSS at midnight
            if now.hour==0 and now.minute==0:
                global DAILY_LOSS
                DAILY_LOSS=0
        except: time.sleep(60)

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=daily_auto_reporter, daemon=True).start()
try: iq_connect()
except: pass

if __name__=="__main__":
    try:
        bot.remove_webhook(); time.sleep(1)
        ext=os.getenv("RENDER_EXTERNAL_URL")
        if ext: bot.set_webhook(url=f"{ext}/{TOKEN}")
    except: pass
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
