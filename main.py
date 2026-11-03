import os, time, threading, datetime, json, requests, random
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import logging, warnings
warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.CRITICAL)
logging.disable(logging.ERROR)

try:
    import pandas as pd
    HAS_PD = True
except:
    HAS_PD = False
    pd = None

print("=== V32 FINAL IQ+OTC+MOMENTUM+ENTRY+EXPIRY ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
IQ_EMAIL = os.getenv("IQ_EMAIL")
IQ_PASS = os.getenv("IQ_PASS")
CHANNEL_ID = "@trailblazeebot"

OWNER_ID = None
SCANNING = True
LAST_SIGNAL_TIME = time.time()
PAIRS = ["EURUSD","GBPUSD","USDJPY","EURJPY","AUDUSD","EURGBP","USDCHF","GBPJPY"]
OTC_MAP = {p:f"{p}-OTC" for p in PAIRS}
PAID_FILE = "paid_users.json"
FREE_FILE = "free_users.json"
HISTORY_FILE = "price_history.json"
PRICE_CACHE = {}

def load_json(f):
    try:
        if os.path.exists(f):
            with open(f,'r') as fp: return json.load(fp)
    except: pass
    return {}
def save_json(f,data):
    try:
        with open(f,'w') as fp: json.dump(data, fp)
    except: pass

PAID_USERS = load_json(PAID_FILE)
FREE_USERS = load_json(FREE_FILE)
PRICE_HISTORY = load_json(HISTORY_FILE)

iq = None
IQ_CONNECTED = False
IQ_LOCK = threading.Lock()
BALANCE = 0

def init_iq():
    global iq, IQ_CONNECTED, BALANCE
    if not IQ_EMAIL or not IQ_PASS: return
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL)
        iq = IQ_Option(IQ_EMAIL, IQ_PASS)
        iq.connect()
        IQ_CONNECTED = iq.check_connect()
        if IQ_CONNECTED:
            try: BALANCE = iq.get_balance()
            except: pass
        logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
        print(f"IQ Connected {IQ_CONNECTED} Bal {BALANCE}", flush=True)
    except Exception as e: print(f"IQ Fail {e}", flush=True)

threading.Thread(target=init_iq, daemon=True).start()

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL)
        iq = IQ_Option(IQ_EMAIL, IQ_PASS)
        iq.connect()
        IQ_CONNECTED = iq.check_connect()
        logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
        return IQ_CONNECTED
    except: return False

def is_otc_time():
    now = datetime.datetime.now() + datetime.timedelta(hours=1)
    return now.weekday() >= 5 or now.hour >= 21 or now.hour < 7

def get_active_symbol(base):
    return OTC_MAP.get(base, base) if is_otc_time() else base

def get_iq_candles(base, count=100):
    if not IQ_CONNECTED and not iq_reconnect(): return None, base
    active = get_active_symbol(base)
    try_list = list(dict.fromkeys([active, base, OTC_MAP.get(base,"")]))
    try_list = [x for x in try_list if x]
    for sym in try_list:
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                candles = iq.get_candles(sym, 60, count, time.time())
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if candles and len(candles)>20:
                candles=sorted(candles,key=lambda x:x['from'])
                PRICE_CACHE[f"{base}_SYMBOL"]=sym
                return candles, sym
        except: continue
    return None, base

def get_price(base):
    candles, sym = get_iq_candles(base, 100)
    if candles:
        closes=[c['close'] for c in candles]
        PRICE_HISTORY[base]=closes[-100:]
        PRICE_HISTORY[f"{base}_FULL"]=candles[-100:]
        save_json(HISTORY_FILE, PRICE_HISTORY)
        return closes[-1], sym
    if base in PRICE_HISTORY and PRICE_HISTORY[base]:
        return PRICE_HISTORY[base][-1], PRICE_CACHE.get(f"{base}_SYMBOL",base)
    return 1.08, base

# ===== MOMENTUM HELPERS =====
def get_candles_df(pair):
    base = pair.replace("-OTC","")
    full_key = f"{base}_FULL"
    if full_key in PRICE_HISTORY and PRICE_HISTORY[full_key]:
        candles = PRICE_HISTORY[full_key]
        if HAS_PD:
            df = pd.DataFrame(candles)
            if 'close' in df.columns:
                return df
    if base in PRICE_HISTORY and len(PRICE_HISTORY[base])>=50:
        closes = PRICE_HISTORY[base]
        if HAS_PD:
            df = pd.DataFrame({
                'close': closes,
                'open': [closes[0]]+closes[:-1],
                'max': [c*1.0003 for c in closes],
                'min': [c*0.9997 for c in closes]
            })
            return df
    return None

def calc_rsi_pandas(close_series, period=14):
    delta = close_series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calc_rsi(close_list, period=14):
    if HAS_PD and hasattr(close_list, 'ewm'):
        return calc_rsi_pandas(close_list, period)
    return 50

def calc_atr(df, period=14):
    try:
        if not HAS_PD: return 0.0004
        high = df['max'] if 'max' in df.columns else df['high']
        low = df['min'] if 'min' in df.columns else df['low']
        close = df['close']
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/period, adjust=False).mean().iloc[-1]
        return float(atr)
    except: return 0.0004

def get_payout(pair):
    try:
        with IQ_LOCK:
            logging.disable(logging.CRITICAL)
            p = iq.get_all_profit()
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if pair in p: return 80
    except: pass
    return 80

def analyze_momentum(pair, sniper_mode=False):
    df=get_candles_df(pair)
    if df is None or len(df)<50: return None
    try:
        if not HAS_PD: return None
        close=df['close']; open_=df['open']; high=df['max'] if 'max' in df.columns else df['high']; low=df['min'] if 'min' in df.columns else df['low']
        ema9=close.ewm(span=9, adjust=False).mean(); ema21=close.ewm(span=21, adjust=False).mean(); ema50=close.ewm(span=50, adjust=False).mean()
        rsi_fast=calc_rsi(close,7); rsi_slow=calc_rsi(close,14)
        atr=calc_atr(df,14)
        c_now=float(close.iloc[-1]); o_now=float(open_.iloc[-1])
        c_prev=float(close.iloc[-2]); o_prev=float(open_.iloc[-2])
        h_now=float(high.iloc[-1]); l_now=float(low.iloc[-1])
        e9=float(ema9.iloc[-1]); e21=float(ema21.iloc[-1]); e50=float(ema50.iloc[-1])
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
        min_atr = 0.00025 if pair.replace("-OTC","") in ["EURUSD","GBPUSD","USDJPY"] else 0.00035
        if atr < min_atr:
            return {"pair":pair,"dir":sig,"conf":45,"price":c_now,"rsi":rsi7,"reason":"Low ATR - Choppy","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if body < atr*0.35:
            return {"pair":pair,"dir":sig,"conf":50,"price":c_now,"rsi":rsi7,"reason":"Doji - No body","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if upper_wick > body*2.5 and lower_wick > body*2.5:
            return {"pair":pair,"dir":sig,"conf":48,"price":c_now,"rsi":rsi7,"reason":"High indecision","payout":payout,"expiry":120,"atr":atr,"rejected":False}
        if is_green:
            if e9 > e21 and e21 > e50: score+=20; reason_list.append("EMA Bull Align")
            elif e9 > e21: score+=12
        else:
            if e9 < e21 and e21 < e50: score+=20; reason_list.append("EMA Bear Align")
            elif e9 < e21: score+=12
        if is_green:
            if 55 <= rsi7 <= 68 and 50 <= rsi14 <= 65: score+=25; reason_list.append(f"RSI Safe {rsi7:.0f}")
            elif 50 <= rsi7 <= 72: score+=15
            elif rsi7 > 75: score-=15
        else:
            if 32 <= rsi7 <= 45 and 35 <= rsi14 <= 50: score+=25; reason_list.append(f"RSI Safe {rsi7:.0f}")
            elif 28 <= rsi7 <= 50: score+=15
            elif rsi7 < 25: score-=15
        if is_green:
            if mom1 > 0.025 and mom3 > 0.05: score+=20; reason_list.append(f"Mom {mom1:.3f}%")
            elif mom1 > 0.01: score+=10
            elif mom1 < 0: score-=10
        else:
            if mom1 < -0.025 and mom3 < -0.05: score+=20; reason_list.append(f"Mom {mom1:.3f}%")
            elif mom1 < -0.01: score+=10
            elif mom1 > 0: score-=10
        bullish_engulf = c_now > o_prev and o_now < c_prev and is_green and not (c_prev > o_prev)
        bearish_engulf = c_now < o_prev and o_now > c_prev and not is_green and (c_prev > o_prev)
        pin_bull = lower_wick > body*1.5 and lower_wick > upper_wick*1.5 and is_green
        pin_bear = upper_wick > body*1.5 and upper_wick > lower_wick*1.5 and not is_green
        if is_green:
            if bullish_engulf: score+=15; reason_list.append("Bull Engulf")
            if pin_bull: score+=15; reason_list.append("Pin Bar Bull")
            elif lower_wick > upper_wick: score+=8
        else:
            if bearish_engulf: score+=15; reason_list.append("Bear Engulf")
            if pin_bear: score+=15; reason_list.append("Pin Bar Bear")
            elif upper_wick > lower_wick: score+=8
        score = max(45, min(94, score + 30))
        reason = " + ".join(reason_list) if reason_list else "Weak PA"
        expiry = 180 if abs(mom1) > 0.06 else 120
        if "-OTC" in pair: expiry = 60 if abs(mom1) > 0.05 else 120
        if sniper_mode and score < 85:
            return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":rsi7,"reason":reason,"payout":payout,"expiry":expiry,"atr":atr,"rejected":True}
        return {"pair":pair,"dir":sig,"conf":score,"price":c_now,"rsi":rsi7,"reason":reason,"payout":payout,"expiry":expiry,"atr":atr,"rejected":False}
    except Exception as e:
        print(f"Momentum err {e}", flush=True)
        return None

def calc_bollinger(prices, period=20, std=2):
    if len(prices) < period: return None, None, None
    sma = sum(prices[-period:]) / period
    var = sum((x - sma) ** 2 for x in prices[-period:]) / period
    return sma + std*(var**0.5), sma, sma - std*(var**0.5)

def calc_rsi_simple(prices, period=14):
    if len(prices) < period+1: return 50
    gains=[]; losses=[]
    for i in range(1,len(prices)):
        d=prices[i]-prices[i-1]
        gains.append(max(d,0)); losses.append(abs(min(d,0)))
    if len(gains)<period: return 50
    ag=sum(gains[-period:])/period; al=sum(losses[-period:])/period
    if al==0: return 88
    if ag==0: return 12
    return 100-(100/(1+ag/al))

def calc_ema_simple(prices, period=21):
    if len(prices)<period: return prices[-1] if prices else 0
    k=2/(period+1); ema=prices[0]
    for p in prices[1:]: ema=p*k+ema*(1-k)
    return ema

def find_sr_levels(prices, lookback=40):
    if len(prices) < lookback: return None, None
    return min(prices[-lookback:]), max(prices[-lookback:])

def analyze_real(pair):
    price, used_sym = get_price(pair)
    prices = PRICE_HISTORY.get(pair, [])
    if len(prices)<40: return None
    rsi=calc_rsi_simple(prices); ema9=calc_ema_simple(prices,9); ema21=calc_ema_simple(prices,21)
    upper,middle,lower=calc_bollinger(prices,20,2)
    support,resistance=find_sr_levels(prices,40)
    if not upper or not support: return None
    d_res=abs(price-resistance)/price*100; d_sup=abs(price-support)/price*100
    near_res=d_res<0.18; near_sup=d_sup<0.18
    tag = "OTC" if "OTC" in used_sym else "REAL"
    expiry = 180
    if near_sup and price<=lower*1.001 and rsi<=28 and prices[-1]>ema9:
        return {"pair":pair,"dir":"CALL","conf":90,"rsi":round(rsi,1),"reason":f"SUPPORT+BB {tag}","price":round(price,5),"used":used_sym,"type":"SR","expiry":expiry,"payout":85,"atr":0.0004}
    if near_res and price>=upper*0.999 and rsi>=72 and prices[-1]<ema9:
        return {"pair":pair,"dir":"PUT","conf":90,"rsi":round(rsi,1),"reason":f"RESISTANCE+BB {tag}","price":round(price,5),"used":used_sym,"type":"SR","expiry":expiry,"payout":85,"atr":0.0004}
    if near_sup and rsi<32 and price<lower*1.002:
        return {"pair":pair,"dir":"CALL","conf":85,"rsi":round(rsi,1),"reason":f"NEAR SUP {tag}","price":round(price,5),"used":used_sym,"type":"SR","expiry":expiry,"payout":80,"atr":0.0004}
    if near_res and rsi>68 and price>upper*0.998:
        return {"pair":pair,"dir":"PUT","conf":85,"rsi":round(rsi,1),"reason":f"NEAR RES {tag}","price":round(price,5),"used":used_sym,"type":"SR","expiry":expiry,"payout":80,"atr":0.0004}
    return None

def generate_chart(pair):
    full_key = f"{pair}_FULL"
    if full_key in PRICE_HISTORY and PRICE_HISTORY[full_key]:
        candles = PRICE_HISTORY[full_key]
        prices = [c['close'] for c in candles]
        open_list = [c['open'] for c in candles]
        high_list = [c['max'] for c in candles]
        low_list = [c['min'] for c in candles]
    else:
        prices = PRICE_HISTORY.get(pair, [])
        if len(prices) < 20: return None
        open_list = [prices[0]] + prices[:-1]
        high_list=[]; low_list=[]
        for i in range(len(prices)):
            o=open_list[i]; c=prices[i]; wiggle=abs(c-o)*0.3+c*0.0004
            high_list.append(max(o,c)+wiggle); low_list.append(min(o,c)-wiggle)
    try:
        support, resistance = find_sr_levels(prices, 40)
        def ema_series(p,per):
            k=2/(per+1); e=p[0]; lst=[]
            for price in p:
                e=price if lst==[] else price*k+e*(1-k); lst.append(e)
            return lst
        ema9=ema_series(prices,9); ema21=ema_series(prices,21)
        fig,ax1=plt.subplots(1,1,figsize=(10,4),facecolor='#131722')
        ax1.set_facecolor('#131722')
        x=list(range(len(prices)))
        for i in range(len(x)):
            o=open_list[i]; h=high_list[i]; l=low_list[i]; c=prices[i]
            col='#26a69a' if c>=o else '#ef5350'
            ax1.plot([x[i],x[i]],[l,h],color=col,linewidth=0.8,alpha=0.9,zorder=2)
            bh=abs(c-o); 
            if bh<(h-l)*0.08: bh=(h-l)*0.08
            ax1.add_patch(Rectangle((x[i]-0.35,min(o,c)),0.7,bh,facecolor=col,edgecolor=col,linewidth=0.8,zorder=3))
        ax1.plot(x,ema9,color='#FFD700',linewidth=1.2,label='EMA9'); ax1.plot(x,ema21,color='orange',linewidth=1.2,label='EMA21')
        if support: ax1.axhline(y=support,color='#26a69a',linestyle='--',linewidth=1.2,label=f'SUP {round(support,5)}')
        if resistance: ax1.axhline(y=resistance,color='#ef5350',linestyle='--',linewidth=1.2,label=f'RES {round(resistance,5)}')
        last=prices[-1]
        used_sym=PRICE_CACHE.get(f"{pair}_SYMBOL",pair)
        ax1.set_title(f'{pair} • {used_sym} • {"🌙 OTC" if "OTC" in used_sym else "☀️ REAL"} • {round(last,5)} IQ:{"✅" if IQ_CONNECTED else "❌"}',color='white',fontsize=11)
        ax1.legend(facecolor='#131722',edgecolor='gray',labelcolor='white',fontsize=7,loc='upper left'); ax1.tick_params(colors='gray'); ax1.grid(color='#2a2e39',linewidth=0.3)
        plt.tight_layout(); path=f"/tmp/{pair}_chart.png"; plt.savefig(path,facecolor='#131722',dpi=150,bbox_inches='tight'); plt.close(); return path
    except Exception as e:
        print(f"Chart err {e}",flush=True); plt.close(); return None

def is_paid(uid):
    if OWNER_ID and str(uid)==str(OWNER_ID): return True
    if str(uid) in PAID_USERS and time.time()<PAID_USERS[str(uid)]: return True
    return False
def can_send_free(uid): return True if is_paid(uid) else FREE_USERS.get(str(uid),0)<2
def use_free(uid):
    if is_paid(uid): return
    FREE_USERS[str(uid)]=FREE_USERS.get(str(uid),0)+1; save_json(FREE_FILE,FREE_USERS)
def get_expiry_date(uid): return datetime.datetime.fromtimestamp(PAID_USERS[str(uid)]).strftime('%d %b %Y') if str(uid) in PAID_USERS else "Not paid"

def build_full_text(pair,d,c,rsi,reason,price,used_sym, expiry=180, payout=80, atr=0):
    now=datetime.datetime.now()+datetime.timedelta(hours=1)
    exp=now+datetime.timedelta(seconds=expiry)
    icon="🔺" if d=="CALL" else "🔻"
    otc_tag="🌙 OTC NIGHT/WEEKEND" if "OTC" in used_sym else "☀️ REAL MARKET"
    strat_tag = "⚡ MOMENTUM" if "EMA" in reason or "Mom" in reason or "Engulf" in reason or "Pin" in reason else "🏔️ SR+BB"
    if expiry <= 60:
        exp_reason = "1 MIN - Fast momentum OTC"
    elif expiry <= 120:
        exp_reason = "2 MIN - Standard momentum"
    else:
        exp_reason = "3 MIN - SR bounce needs time" if "SUP" in reason or "RES" in reason or "BB" in reason else "3 MIN - Strong trend continuation"
    mins = expiry // 60
    secs = expiry
    return f"""🚨 V31 {otc_tag} {strat_tag} 🚨

💱 {pair} → {used_sym}
{'📈' if d=='CALL' else '📉'} {d} - {mins} MIN {icon}
🔥 {c}% 💎 | {reason}
💲 {price} | RSI {round(float(rsi),1)} | ATR {round(float(atr),5)} | Pay {payout}%
📡 IQ: {"✅ REAL" if IQ_CONNECTED else "❌"}

🎯 ENTRY: {now.strftime('%H:%M:%S')} WAT
⏰ EXPIRY: {exp.strftime('%H:%M:%S')} WAT ({secs}s)
⏳ SUGGESTED: {exp_reason}

👉 Trade {d} NOW on {used_sym}!"""

bot = telebot.TeleBot(TOKEN, threaded=False) if ':' in TOKEN else None

if bot:
    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        if OWNER_ID is None: OWNER_ID=m.chat.id
        mode="🌙 OTC" if is_otc_time() else "☀️ REAL"
        if OWNER_ID and m.chat.id==OWNER_ID:
            bot.send_message(m.chat.id,f"👑 V31 OWNER {mode} IQ:{'✅' if IQ_CONNECTED else '❌'}\nDual Engine: SR+BB + MOMENTUM\n/resume /pause /test /status /levels /balance\n/chart EURUSD")
            return
        left=2-FREE_USERS.get(str(m.chat.id),0)
        bot.send_message(m.chat.id,f"🚀 V31 IQ+OTC+Momentum\n{mode}\n{left} free left")

    @bot.message_handler(commands=['chart'])
    def chart_cmd(m):
        try:
            parts=m.text.split(); pair=parts[1].upper() if len(parts)>1 else "EURUSD"
            base=pair.replace("-OTC","")
            if base not in PAIRS: base="EURUSD"
            if "-OTC" in pair: PRICE_CACHE[f"{base}_SYMBOL"]=pair
            get_price(base)
            prices=PRICE_HISTORY.get(base,[])
            if len(prices)<25: bot.send_message(m.chat.id,f"⏳ Fetching IQ {PRICE_CACHE.get(f'{base}_SYMBOL',base)}... {len(prices)}/25"); return
            bot.send_message(m.chat.id,f"📈 Generating {PRICE_CACHE.get(f'{base}_SYMBOL',base)} chart...")
            chart_path=generate_chart(base)
            if chart_path and os.path.exists(chart_path):
                with open(chart_path,'rb') as f: bot.send_photo(m.chat.id,f,caption=f"📊 {PRICE_CACHE.get(f'{base}_SYMBOL',base)} IQ {'✅' if IQ_CONNECTED else '❌'}")
            else: bot.send_message(m.chat.id,"❌ Chart failed")
        except Exception as e: bot.send_message(m.chat.id,f"Error {e}")

    @bot.message_handler(commands=['levels','balance','status','id','pause','resume','test','scan'])
    def other(m):
        global SCANNING,OWNER_ID,LAST_SIGNAL_TIME,BALANCE
        if m.text.startswith("/id"):
            bot.send_message(m.chat.id,f"ID {m.from_user.id} Owner {OWNER_ID} OTC {is_otc_time()} IQ {IQ_CONNECTED} Sym {PRICE_CACHE.get('EURUSD_SYMBOL','?')}"); return
        if m.text.startswith("/balance"):
            if OWNER_ID and m.chat.id!=OWNER_ID: return
            try:
                with IQ_LOCK:
                    logging.disable(logging.CRITICAL)
                    bal = iq.get_balance()
                    mode = iq.get_balance_mode()
                    logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                BALANCE = bal
                bot.send_message(m.chat.id, f"💰 IQ Balance\nMode: {mode}\nBal: ${bal}\nIQ: {'✅' if IQ_CONNECTED else '❌'}")
            except Exception as e:
                bot.send_message(m.chat.id, f"❌ {e} IQ:{IQ_CONNECTED}")
            return
        if OWNER_ID and m.chat.id!=OWNER_ID: return
        if m.text.startswith("/status"):
            txt=f"OTC: {is_otc_time()} {'🌙' if is_otc_time() else '☀️'} IQ {IQ_CONNECTED} SCAN {SCANNING}\n"
            for p in PAIRS: txt+=f"{p}: {len(PRICE_HISTORY.get(p,[]))} Sym {PRICE_CACHE.get(f'{p}_SYMBOL','?')}\n"
            bot.send_message(m.chat.id, txt)
        elif m.text.startswith("/levels"):
            mode="🌙 OTC" if is_otc_time() else "☀️ REAL"
            txt=f"📊 V31 LEVELS {mode} IQ:{'✅' if IQ_CONNECTED else '❌'}\n━━━━━━━━━━━━━━━\n"
            for pair in PAIRS:
                prices=PRICE_HISTORY.get(pair,[])
                if len(prices)<40: txt+=f"⏳ {pair}: {len(prices)}/40\n"; continue
                sup,res=find_sr_levels(prices,40)
                upper,mid,lower=calc_bollinger(prices,20,2); rsi=calc_rsi_simple(prices); price=prices[-1]
                if not upper: continue
                used=PRICE_CACHE.get(f"{pair}_SYMBOL",pair)
                txt+=f"{'🌙' if 'OTC' in used else '☀️'} {pair}→{used} {round(price,5)} RSI {round(rsi,1)}\n"
                mom = analyze_momentum(used)
                if mom and mom['conf']>=70:
                    txt+=f"  ⚡ MOM {mom['dir']} {mom['conf']}% {mom['reason']} Exp {mom['expiry']}s\n"
            txt+=f"━━━━━━━━━━━━━━━\n/chart EURUSD or /chart EURUSD-OTC"
            bot.send_message(m.chat.id,txt)
        elif m.text.startswith("/resume"): SCANNING=True; bot.send_message(m.chat.id,"▶️ ON")
        elif m.text.startswith("/pause"): SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused")
        elif m.text.startswith("/test") or m.text.startswith("/scan"):
            pair=random.choice(PAIRS); sym=get_active_symbol(pair)
            sr = analyze_real(pair)
            mom = analyze_momentum(sym)
            best = None
            if mom and mom['conf']>=70: best = mom
            elif sr: best = sr
            if best:
                d=best['dir']; c=best['conf']; rsi=best['rsi']; reason=best['reason']; price=best['price']; payout=best.get('payout',80); expiry=best.get('expiry',120); atr=best.get('atr',0.0004)
            else:
                d=random.choice(["CALL","PUT"]); c=90; rsi=23.5; reason="TEST SR+BB"; price=1.08; payout=80; expiry=180; atr=0.0004
            mk=InlineKeyboardMarkup(row_width=1)
            mk.add(InlineKeyboardButton(f"👥 Users {sym} {d} {c}% Exp {expiry}s",callback_data=f"users_{pair}_{d}_{c}_{rsi}_{reason}_{price}_{expiry}_{payout}_{atr}"),
                   InlineKeyboardButton(f"📢 Channel {sym}",callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{reason}_{price}_{expiry}_{payout}_{atr}"),
                   InlineKeyboardButton(f"🚀 BOTH {sym} {expiry}s",callback_data=f"both_{pair}_{d}_{c}_{rsi}_{reason}_{price}_{expiry}_{payout}_{atr}"),
                   InlineKeyboardButton("❌ Skip",callback_data="skip"))
            bot.send_message(m.chat.id,f"TEST {pair}→{sym} {d} {c}%\n{reason}\n🎯 Entry now + {expiry}s expiry\nPay {payout}% ATR {round(atr,5)}\nWhere?",reply_markup=mk)

    @bot.callback_query_handler(func=lambda c: True)
    def cb(call):
        global LAST_SIGNAL_TIME
        if OWNER_ID and call.message.chat.id!=OWNER_ID: return
        if call.data=="skip": bot.edit_message_text("❌ Skipped",call.message.chat.id,call.message.message_id); return
        try:
            parts=call.data.split("_"); typ=parts[0]; pair=parts[1]; d=parts[2]; c=parts[3]; rsi=parts[4]; reason=parts[5]; price=parts[6]
            expiry=int(parts[7]) if len(parts)>7 else 180
            payout=int(parts[8]) if len(parts)>8 else 80
            atr=float(parts[9]) if len(parts)>9 else 0.0004
            used_sym=PRICE_CACHE.get(f"{pair}_SYMBOL",get_active_symbol(pair))
            full=build_full_text(pair,d,c,rsi,reason,price,used_sym,expiry,payout,atr)
            chart_path=generate_chart(pair)
            if typ in ["users","both"]:
                all_ids=set(list(PAID_USERS.keys())+list(FREE_USERS.keys())+[str(OWNER_ID)])
                for uid_str in all_ids:
                    try:
                        uid=int(uid_str)
                        if not is_paid(uid) and not can_send_free(uid): continue
                        if chart_path and os.path.exists(chart_path):
                            with open(chart_path,'rb') as f: bot.send_photo(uid,f,caption=full)
                        else: bot.send_message(uid,full)
                        use_free(uid); time.sleep(0.4)
                    except: pass
            if typ in ["chan","both"]:
                try:
                    if chart_path and os.path.exists(chart_path):
                        with open(chart_path,'rb') as f: bot.send_photo(CHANNEL_ID,f,caption=full)
                    else: bot.send_message(CHANNEL_ID,full)
                except: pass
            LAST_SIGNAL_TIME=time.time()
            bot.edit_message_text(f"✅ SENT {used_sym} {typ} {d} {c}% Exp {expiry}s",call.message.chat.id,call.message.message_id)
        except Exception as e: bot.send_message(call.message.chat.id,f"Error {e}")

    @app.route(f'/{TOKEN}',methods=['POST'])
    def webhook():
        if request.headers.get('content-type')=='application/json':
            js=request.get_data().decode('utf-8'); upd=telebot.types.Update.de_json(js); bot.process_new_updates([upd]); return ''
        return 'ok',200
    @app.route('/')
    def home(): return f"V32 FINAL IQ:{IQ_CONNECTED} OTC:{is_otc_time()} Sym:{PRICE_CACHE.get('EURUSD_SYMBOL','?')}",200

    def set_wh():
        time.sleep(5)
        if RENDER_URL:
            try: requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True",timeout=10); time.sleep(2); url=f"{RENDER_URL}/{TOKEN}"; r=requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}",timeout=10); print(r.text,flush=True)
            except: pass
    threading.Thread(target=set_wh,daemon=True).start()

def scanner():
    global LAST_SIGNAL_TIME
    while True:
        try:
            time.sleep(60)
            if not OWNER_ID or not SCANNING or not bot: continue
            for pair in PAIRS:
                sr = analyze_real(pair)
                sym = get_active_symbol(pair)
                mom = analyze_momentum(sym, sniper_mode=False)
                candidates = []
                if sr: candidates.append(sr)
                if mom and not mom.get('rejected', False) and mom['conf']>=70:
                    candidates.append({
                        "pair": pair,
                        "dir": mom['dir'],
                        "conf": mom['conf'],
                        "rsi": mom['rsi'],
                        "reason": mom['reason'],
                        "price": mom['price'],
                        "used": sym,
                        "type": "MOM",
                        "expiry": mom['expiry'],
                        "payout": mom['payout'],
                        "atr": mom['atr']
                    })
                if not candidates: continue
                best = max(candidates, key=lambda x: x['conf'])
                d=best['dir']; c=best['conf']; rsi=best['rsi']; reason=best['reason']; price=best['price']; used_sym=best['used']
                expiry=best.get('expiry',180); payout=best.get('payout',80); atr=best.get('atr',0.0004)
                strat_icon = "⚡ MOM" if best.get('type')=="MOM" else "🏔️ SR"
                mk=InlineKeyboardMarkup(row_width=1)
                mk.add(InlineKeyboardButton(f"👥 Users {used_sym} {d} {c}% {strat_icon} {expiry}s",callback_data=f"users_{pair}_{d}_{c}_{rsi}_{reason}_{price}_{expiry}_{payout}_{atr}"),
                       InlineKeyboardButton(f"📢 Channel {used_sym}",callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{reason}_{price}_{expiry}_{payout}_{atr}"),
                       InlineKeyboardButton(f"🚀 BOTH {used_sym} {strat_icon} Exp {expiry}s",callback_data=f"both_{pair}_{d}_{c}_{rsi}_{reason}_{price}_{expiry}_{payout}_{atr}"),
                       InlineKeyboardButton("❌ Skip",callback_data="skip"))
                now=datetime.datetime.now()+datetime.timedelta(hours=1)
                exp=now+datetime.timedelta(seconds=expiry)
                txt=f"🔔 V32 {strat_icon} READY!\n{pair}→{used_sym} {d} {c}% Price {price} RSI {round(float(rsi),1)}\n{reason}\nPay {payout}% ATR {round(float(atr),5)}\n🎯 ENTRY {now.strftime('%H:%M:%S')} → ⏰ EXPIRY {exp.strftime('%H:%M:%S')} ({expiry}s)\n{'🌙 OTC' if 'OTC' in used_sym else '☀️ REAL'}"
                bot.send_message(OWNER_ID,txt,reply_markup=mk)
                LAST_SIGNAL_TIME=time.time()
                time.sleep(120)
                break
        except Exception as e: print(f"SCAN {e}",flush=True); time.sleep(10)

threading.Thread(target=scanner,daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
