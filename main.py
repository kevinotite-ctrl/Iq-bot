import os, time, threading, warnings, logging
from datetime import datetime, timedelta, timezone
from flask import Flask, request
import telebot
from telebot import types
import pandas as pd
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pytz

warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.CRITICAL)
logging.disable(logging.ERROR)

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 8659453018
BUFFER_SEC = 40  # <-- 40s BUFFER ADDED

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

REAL_PAIRS = ["EURUSD","GBPUSD","USDJPY","EURGBP","AUDUSD","USDCAD","EURJPY","GBPJPY","USDCHF","AUDJPY","EURAUD","GBPCHF","EURCHF","NZDUSD","GBPAUD","EURCAD","AUDCAD","GBPCAD","NZDJPY","AUDNZD","CHFJPY","CADJPY"]
OTC_PAIRS = ["EURUSD-OTC","GBPUSD-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","AUDJPY-OTC","EURAUD-OTC","GBPAUD-OTC","NZDUSD-OTC","GBPCHF-OTC","EURCHF-OTC","USDCHF-OTC","AUDCAD-OTC","EURCAD-OTC","CADJPY-OTC","NZDJPY-OTC"]

PAIR_EMOJI = {
    "EURUSD":"🇪🇺 EUR/USD REAL", "GBPUSD":"🇬🇧 GBP/USD REAL", "USDJPY":"🇺🇸 USD/JPY REAL", "EURGBP":"🇪🇺 EUR/GBP REAL",
    "AUDUSD":"🇦🇺 AUD/USD REAL", "USDCAD":"🇺🇸 USD/CAD REAL", "EURJPY":"🇪🇺 EUR/JPY REAL", "GBPJPY":"🇬🇧 GBP/JPY REAL",
    "USDCHF":"🇺🇸 USD/CHF REAL", "AUDJPY":"🇦🇺 AUD/JPY REAL", "EURAUD":"🇪🇺 EUR/AUD REAL", "GBPCHF":"🇬🇧 GBP/CHF REAL",
    "EURCHF":"🇪🇺 EUR/CHF REAL", "NZDUSD":"🇳🇿 NZD/USD REAL", "GBPAUD":"🇬🇧 GBP/AUD REAL", "EURCAD":"🇪🇺 EUR/CAD REAL",
    "AUDCAD":"🇦🇺 AUD/CAD REAL", "GBPCAD":"🇬🇧 GBP/CAD REAL", "NZDJPY":"🇳🇿 NZD/JPY REAL", "AUDNZD":"🇦🇺 AUD/NZD REAL",
    "CHFJPY":"🇨🇭 CHF/JPY REAL", "CADJPY":"🇨🇦 CAD/JPY REAL",
    "EURUSD-OTC":"🇪🇺 EUR/USD OTC", "GBPUSD-OTC":"🇬🇧 GBP/USD OTC", "EURGBP-OTC":"🇪🇺 EUR/GBP OTC",
    "USDJPY-OTC":"🇺🇸 USD/JPY OTC", "GBPJPY-OTC":"🇬🇧 GBP/JPY OTC", "AUDUSD-OTC":"🇦🇺 AUD/USD OTC",
    "USDCHF-OTC":"🇺🇸 USD/CHF OTC", "EURJPY-OTC":"🇪🇺 EUR/JPY OTC", "AUDJPY-OTC":"🇦🇺 AUD/JPY OTC",
    "EURAUD-OTC":"🇪🇺 EUR/AUD OTC", "GBPAUD-OTC":"🇬🇧 GBP/AUD OTC", "NZDUSD-OTC":"🇳🇿 NZD/USD OTC",
    "GBPCHF-OTC":"🇬🇧 GBP/CHF OTC", "EURCHF-OTC":"🇪🇺 EUR/CHF OTC", "USDCAD-OTC":"🇺🇸 USD/CAD OTC",
    "AUDCAD-OTC":"🇦🇺 AUD/CAD OTC", "EURCAD-OTC":"🇪🇺 EUR/CAD OTC", "CADJPY-OTC":"🇨🇦 CAD/JPY OTC",
    "NZDJPY-OTC":"🇳🇿 NZD/JPY OTC"
}

STATS = {"balance":0.0,"real_balance":0.0,"wins":0,"loss":0,"streak":0}
user_states = {}; AUTO_STATE = {}; IQ_LOCK = threading.Lock()
IQ_CONNECTED=False; iq=None; PAYOUT_CACHE={}; PAYOUT_TIME=0

def is_allowed(uid): return uid == OWNER_ID

def is_real_hours():
    try:
        tz = pytz.timezone("Africa/Lagos")
        now = datetime.now(tz)
        if now.weekday() >= 5: return False
        return 7 <= now.hour < 20
    except:
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        if now.weekday() >= 5: return False
        return 7 <= now.hour < 20

def get_mode_text(): return "REAL SIGNAL (7AM-8PM)" if is_real_hours() else "OTC TRADING (8PM-7AM+Weekend)"

try:
    from iqoptionapi.stable_api import IQ_Option
    EMAIL=os.getenv("IQ_EMAIL"); PWD=os.getenv("IQ_PASS")
    if EMAIL and PWD:
        logging.disable(logging.CRITICAL)
        iq=IQ_Option(EMAIL,PWD); iq.connect()
        IQ_CONNECTED=iq.check_connect()
        if IQ_CONNECTED:
            try: iq.change_balance("PRACTICE"); STATS["real_balance"]=iq.get_balance()
            except: pass
        logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
except: IQ_CONNECTED=False

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL)
        iq=IQ_Option(os.getenv("IQ_EMAIL"),os.getenv("IQ_PASS")); iq.connect()
        IQ_CONNECTED=iq.check_connect()
        if IQ_CONNECTED: 
            try: STATS["real_balance"]=iq.get_balance()
            except: pass
        logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
        return IQ_CONNECTED
    except: IQ_CONNECTED=False; return False

def get_real_balance(bal_type="PRACTICE"):
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); iq.change_balance(bal_type); bal=iq.get_balance()
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            return bal
    except: return 0.0

def get_payout(pair):
    global PAYOUT_CACHE, PAYOUT_TIME
    if time.time()-PAYOUT_TIME<60 and pair in PAYOUT_CACHE: return PAYOUT_CACHE[pair]
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); all_p=iq.get_all_profit()
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if pair in all_p:
                for k in ['blitz','turbo','binary']:
                    if k in all_p[pair]:
                        PAYOUT_CACHE[pair]=float(all_p[pair][k]); PAYOUT_TIME=time.time(); return float(all_p[pair][k])
        return 0.85
    except: return PAYOUT_CACHE.get(pair,0.85)

# INSTANT CANDLES - NO 40 MIN WAIT
def get_candles(pair):
    if not IQ_CONNECTED and not iq_reconnect(): return None
    if pair not in REAL_PAIRS and pair not in OTC_PAIRS: return None
    for _ in range(2):
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL); c=iq.get_candles(pair,60,50,time.time())
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if c and len(c)>25: return pd.DataFrame(sorted(c,key=lambda x:x['from']))
            time.sleep(0.4)
        except: time.sleep(0.4)
    return None

def calc_rsi(closes, period=7):
    delta=closes.diff()
    gain=delta.where(delta>0,0).rolling(period).mean()
    loss=-delta.where(delta<0,0).rolling(period).mean()
    rs=gain/loss
    return 100-(100/(1+rs))

def calc_atr(df, period=14):
    try:
        high=df['max']; low=df['min']; close=df['close']
        tr1=high-low; tr2=(high-close.shift()).abs(); tr3=(low-close.shift()).abs()
        tr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]
    except: return 0.0005

def analyze_momentum(pair, sniper_mode=False):
    df=get_candles(pair)
    if df is None: return None
    try:
        close=df['close']; open_=df['open']; high=df['max']; low=df['min']
        ema9=close.ewm(9).mean(); ema21=close.ewm(21).mean(); ema50=close.ewm(50).mean()
        rsi_fast=calc_rsi(close,7); rsi_slow=calc_rsi(close,14)
        atr=calc_atr(df,14)
        c_now=float(close.iloc[-1]); o_now=float(open_.iloc[-1])
        c_prev=float(close.iloc[-2]); o_prev=float(open_.iloc[-2])
        h_now=float(high.iloc[-1]); l_now=float(low.iloc[-1])
        e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1])
        e21_prev=float(ema21.iloc[-2])
        rsi7=float(rsi_fast.iloc[-1]); rsi14=float(rsi_slow.iloc[-1])
        mom1=(close.iloc[-1]-close.iloc[-2])/close.iloc[-2]*100
        mom3=(close.iloc[-1]-close.iloc[-4])/close.iloc[-4]*100
        body=abs(c_now-o_now)
        upper_wick=h_now-max(c_now,o_now)
        lower_wick=min(c_now,o_now)-l_now
        is_green=c_now>o_now
        payout=get_payout(pair)
        sig="CALL" if is_green else "PUT"
        score=0; reason_list=[]
        min_atr = 0.00025 if pair in ["EURUSD","GBPUSD","USDJPY"] else 0.00035
        if atr < min_atr:
            return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":rsi7,"reason":"Low ATR","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if body < atr*0.35:
            return {"pair":pair,"dir":sig,"conf":50,"price":c_now,"rsi":rsi7,"reason":"Doji","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if is_green:
            if e9 > e21 and e21 > e50: 
                score+=20; reason_list.append("EMA Bull")
                if e21 > e21_prev: score+=10
            elif e9 > e21: score+=12
        else:
            if e9 < e21 and e21 < e50: 
                score+=20; reason_list.append("EMA Bear")
                if e21 < e21_prev: score+=10
            elif e9 < e21: score+=12
        if is_green:
            if 55 <= rsi7 <= 68 and 50 <= rsi14 <= 65:
                score+=25; reason_list.append(f"RSI {rsi7:.0f}")
            elif 50 <= rsi7 <= 72: score+=15
            elif rsi7 > 75: score-=15
        else:
            if 32 <= rsi7 <= 45 and 35 <= rsi14 <= 50:
                score+=25; reason_list.append(f"RSI {rsi7:.0f}")
            elif 28 <= rsi7 <= 50: score+=15
            elif rsi7 < 25: score-=15
        if is_green:
            if mom1 > 0.025 and mom3 > 0.05: score+=20; reason_list.append(f"Mom {mom1:.3f}%")
            elif mom1 > 0.01: score+=10
        else:
            if mom1 < -0.025 and mom3 < -0.05: score+=20; reason_list.append(f"Mom {mom1:.3f}%")
            elif mom1 < -0.01: score+=10
        bullish_engulf = c_now > o_prev and o_now < c_prev and is_green and not (c_prev > o_prev)
        bearish_engulf = c_now < o_prev and o_now > c_prev and not is_green and (c_prev > o_prev)
        pin_bull = lower_wick > body*1.5 and lower_wick > upper_wick*1.5 and is_green
        pin_bear = upper_wick > body*1.5 and upper_wick > lower_wick*1.5 and not is_green
        if is_green:
            if bullish_engulf: score+=15; reason_list.append("Bull Engulf")
            if pin_bull: score+=15; reason_list.append("Pin Bull")
        else:
            if bearish_engulf: score+=15; reason_list.append("Bear Engulf")
            if pin_bear: score+=15; reason_list.append("Pin Bear")
        score = max(45, min(94, score + 30))
        reason = " + ".join(reason_list) if reason_list else "Weak PA"
        expiry = 180 if abs(mom1) > 0.06 else 120
        if "-OTC" in pair: expiry = 60 if abs(mom1) > 0.05 else 120
        if sniper_mode and score < 85:
            return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":rsi7,"reason":reason,"payout":payout,"expiry":expiry,"atr":atr,"rejected":True}
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":rsi7,"reason":reason,"payout":payout,"expiry":expiry,"atr":atr,"rejected":False}
    except: return None

def iq_trade(pair,direction,amount,bal,expiry_sec=30):
    if not IQ_CONNECTED and not iq_reconnect(): return False,None,0
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL); iq.change_balance(bal)
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            mins=max(1,int(expiry_sec/60))
            if expiry_sec<=60: mins=1
            try:
                logging.disable(logging.CRITICAL); check,oid=iq.buy(amount,pair,direction.lower(),mins)
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                if check: return True,oid,expiry_sec
            except: pass
            if expiry_sec<=90:
                try:
                    logging.disable(logging.CRITICAL); _,oid=iq.buy_blitz(pair,amount,direction.lower(),expiry_sec)
                    logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                    return True,oid,expiry_sec
                except: pass
            return False,None,0
    except: iq_reconnect(); return False,None,0

# 40s BUFFER SIGNAL SCANNER
def real_signal_scanner():
    last_signal={}; tz=pytz.timezone("Africa/Lagos")
    while True:
        try:
            if IQ_CONNECTED:
                pairs = REAL_PAIRS if is_real_hours() else OTC_PAIRS
                for pair in pairs:
                    if pair in last_signal and time.time()-last_signal[pair]<600: continue
                    d=analyze_momentum(pair,sniper_mode=True)
                    if d and not d.get('rejected') and d['conf']>=85:
                        now=datetime.now(tz); entry=now+timedelta(seconds=BUFFER_SEC)
                        exp=d['expiry']; exp_txt=f"{exp//60} min" if exp>=60 else f"{exp}s"
                        dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"
                        msg=f"""📡 **REAL AUTO {PAIR_EMOJI.get(pair,pair)} + {BUFFER_SEC}s BUFFER** 📡

💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_e} | 🎯 {d['conf']:.0f}% 
📈 {d['reason']} | RSI {d['rsi']:.1f}
💸 {int(d['payout']*100)}% | Exp {exp_txt}

⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in {BUFFER_SEC}s)
📅 {now.strftime('%A %d %b %H:%M WAT')}
"""
                        try: bot.send_message(OWNER_ID,msg,parse_mode="Markdown"); last_signal[pair]=time.time()
                        except: pass
                    time.sleep(2)
            time.sleep(20)
        except: time.sleep(30)

@bot.message_handler(commands=['start','mode','balance','levels'])
def start(m):
    if not is_allowed(m.from_user.id): bot.send_message(m.chat.id,"❌ Private"); return
    if m.text.startswith('/mode'):
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz)
        txt=f"📍 **MODE V34 INSTANT**\n⏰ {now.strftime('%A %H:%M:%S WAT')}\n📊 {get_mode_text()}\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'}\n⏳ Buffer: {BUFFER_SEC}s\n⚡ Instant candles - no 1/40 wait"
        bot.send_message(m.chat.id,txt,parse_mode="Markdown"); return
    if m.text.startswith('/balance'):
        try:
            demo=get_real_balance("PRACTICE"); real=get_real_balance("REAL")
            bot.send_message(m.chat.id,f"💰 DEMO: ${demo:.2f}\n🔴 REAL: ${real:.2f}")
        except Exception as e: bot.send_message(m.chat.id,f"Balance error {e}")
        return
    if m.text.startswith('/levels'):
        bot.send_message(m.chat.id,f"🔍 **SCANNING ALL PAIRS INSTANT - NO WAIT...**")
        results=[]
        pairs = (REAL_PAIRS if is_real_hours() else []) + OTC_PAIRS
        # scan real + otc together
        all_pairs = REAL_PAIRS + OTC_PAIRS if is_real_hours() else OTC_PAIRS
        for pair in all_pairs[:22]:
            d=analyze_momentum(pair,sniper_mode=False)
            if not d: results.append((pair,0,"-","No data","🔴"))
            else: 
                status="🟢 READY" if d['conf']>=85 else "🟡 WAIT" if d['conf']>=65 else "🔴"
                results.append((pair,d['conf'],d['dir'],d['reason'],status))
            time.sleep(0.3)
        results.sort(key=lambda x: x[1], reverse=True)
        txt=f"📊 **LEVELS INSTANT {get_mode_text()}** 📊\nBuffer {BUFFER_SEC}s | IQ {'✅' if IQ_CONNECTED else '❌'}\n\n"
        for pair,conf,dir_,reason,status in results:
            emoji=PAIR_EMOJI.get(pair,pair)
            txt+=f"{status} {emoji}: {conf:.0f}% {dir_} - {reason}\n"
        bot.send_message(m.chat.id,txt,parse_mode="Markdown")
        return
    bal_demo=get_real_balance("PRACTICE")
    mk=types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton(f"💹 MANUAL OTC (19)",callback_data="trade"))
    mk.add(types.InlineKeyboardButton(f"📈 TRADE REAL (22)",callback_data="trade_real"))
    mk.add(types.InlineKeyboardButton("📊 LEVELS INSTANT",callback_data="levels_instant"))
    txt=f"🤖 **V34 INSTANT + {BUFFER_SEC}s BUFFER**\n💎 IQ: {'✅' if IQ_CONNECTED else '❌'} | ${bal_demo:.2f}\n📍 {get_mode_text()}\n⚡ No 1/40 wait - IQ candles instant"
    bot.send_message(m.chat.id,txt,reply_markup=mk,parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_allowed(c.from_user.id): bot.answer_callback_query(c.id,"❌ Private"); return
    data=c.data; cid=c.message.chat.id
    if data=="levels_instant":
        bot.send_message(cid,f"Use /levels - instant scan")
        return
    if data=="trade_real":
        mk=types.InlineKeyboardMarkup(row_width=1)
        mk.add(types.InlineKeyboardButton("🔍 SCAN ALL REAL NOW",callback_data="scan_all_real"))
        for p in REAL_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"real_pair_{p}"))
        bot.send_message(cid,f"📈 **TRADE REAL AUTO EXPIRY + {BUFFER_SEC}s BUFFER**",reply_markup=mk,parse_mode="Markdown"); return
    if data=="scan_all_real":
        bot.answer_callback_query(c.id,"Scanning 22 REAL pairs...")
        results=[]
        for pair in REAL_PAIRS:
            d=analyze_momentum(pair,sniper_mode=False)
            if not d: results.append((pair,0,"-","No data","🔴",120))
            else:
                status="🟢 READY" if d['conf']>=85 else "🟡 WAIT" if d['conf']>=65 else "🔴"
                results.append((pair,d['conf'],d['dir'],d['reason'],status,d['expiry']))
        results.sort(key=lambda x: x[1], reverse=True)
        txt=f"📊 **REAL READINESS + {BUFFER_SEC}s BUFFER**\n\n"
        for pair,conf,dir_,reason,status,exp in results:
            txt+=f"{status} {PAIR_EMOJI.get(pair,pair)}: {conf:.0f}% {dir_} Exp {exp}s - {reason}\n"
        bot.send_message(cid,txt,parse_mode="Markdown")
        return
    if data.startswith("real_pair_"):
        pair=data.replace("real_pair_","")
        d=analyze_momentum(pair,sniper_mode=False)
        if not d or d['conf'] < 65:
            bot.send_message(cid,f"⚠️ No safe trade for {pair} - {d['conf'] if d else 0}%")
            return
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=BUFFER_SEC)
        exp=d['expiry']; exp_txt=f"{exp//60} min" if exp>=60 else f"{exp}s"
        dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"
        signal_txt=f"""📡 **REAL SIGNAL + {BUFFER_SEC}s BUFFER** 📡

💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_e} | 🎯 {d['conf']:.0f}%
📈 {d['reason']} | RSI {d['rsi']:.1f}
💸 {int(d['payout']*100)}%

⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in {BUFFER_SEC}s)
⏱️ EXPIRY: {exp_txt}
📅 {now.strftime('%A %d %b')}

👉 You have {BUFFER_SEC}s to place {d['dir']}!
"""
        bot.send_message(cid,signal_txt,parse_mode="Markdown")
        return
    if data=="trade":
        mk=types.InlineKeyboardMarkup(row_width=2)
        for p in OTC_PAIRS: mk.add(types.InlineKeyboardButton(f"{PAIR_EMOJI.get(p,p)}",callback_data=f"pair_{p}"))
        bot.send_message(cid,f"💹 **MANUAL OTC + {BUFFER_SEC}s BUFFER**",reply_markup=mk,parse_mode="Markdown"); return
    if data.startswith("pair_"):
        pair=data.replace("pair_","")
        d=analyze_momentum(pair,sniper_mode=False)
        if not d: bot.send_message(cid,f"❌ Failed {pair}"); return
        tz=pytz.timezone("Africa/Lagos"); now=datetime.now(tz); entry=now+timedelta(seconds=BUFFER_SEC)
        dir_e="🟢 CALL ⬆️" if d['dir']=="CALL" else "🔴 PUT ⬇️"
        txt=f"""📡 **OTC SIGNAL + {BUFFER_SEC}s BUFFER** 📡

💱 {PAIR_EMOJI.get(pair,pair)}
📊 {dir_e} | {d['conf']:.0f}%
📈 {d['reason']}

⏰ ENTRY: {entry.strftime('%H:%M:%S WAT')} (in {BUFFER_SEC}s)
⏱️ EXPIRY: {d['expiry']}s

👉 Place {d['dir']} on {pair} in {BUFFER_SEC}s!
"""
        bot.send_message(cid,txt,parse_mode="Markdown")
        return

@app.route(f"/{BOT_TOKEN}",methods=['POST'])
def wh(): bot.process_new_updates([telebot.types.Update.de_json(request.get_data().decode("utf-8"))]); return "ok"
@app.route("/")
def home():
    u=os.getenv("RENDER_EXTERNAL_URL")
    if u:
        try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={u}/{BOT_TOKEN}",timeout=5)
        except: pass
    return f"V34 INSTANT {BUFFER_SEC}s BUFFER IQ:{IQ_CONNECTED}"

threading.Thread(target=real_signal_scanner,daemon=True).start()
app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))
