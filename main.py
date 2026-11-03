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

print("=== V33 HYBRID MOMENTUM + 40s BUFFER ===", flush=True)
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
CACHE_TIME = {}
BUFFER_SEC = 40

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
BALANCE = 0

def init_iq():
    global iq, IQ_CONNECTED, BALANCE
    if not IQ_EMAIL or not IQ_PASS:
        print("IQ credentials missing - fallback mode", flush=True)
        return
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL)
        iq_obj = IQ_Option(IQ_EMAIL, IQ_PASS)
        iq_obj.connect()
        connected = iq_obj.check_connect()
        iq = iq_obj if connected else None
        IQ_CONNECTED = bool(connected)
        if IQ_CONNECTED:
            try: BALANCE = iq.get_balance()
            except: pass
        logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
        print(f"IQ Connected {IQ_CONNECTED} Bal {BALANCE}", flush=True)
    except Exception as e:
        iq=None; IQ_CONNECTED=False
        print(f"IQ Fail {e} fallback", flush=True)

threading.Thread(target=init_iq, daemon=True).start()

def is_otc_time():
    now = datetime.datetime.now() + datetime.timedelta(hours=1)
    return now.weekday()>=5 or now.hour>=21 or now.hour<7

def get_active_symbol(base):
    return OTC_MAP.get(base, base) if is_otc_time() else base

def get_price_hybrid(pair):
    global iq, IQ_CONNECTED
    if iq and IQ_CONNECTED:
        try:
            active=get_active_symbol(pair)
            logging.disable(logging.CRITICAL)
            candles=iq.get_candles(active,60,2,time.time())
            logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
            if candles:
                PRICE_CACHE[f"{pair}_SYMBOL"]=active
                return candles[-1]['close'], active, True
        except: pass
    now=time.time()
    if pair in PRICE_CACHE and now-CACHE_TIME.get(pair,0)<120:
        price=PRICE_CACHE[pair]+random.uniform(-0.0003,0.0003)
        sym=PRICE_CACHE.get(f"{pair}_SYMBOL",get_active_symbol(pair))
        return price, sym, False
    try:
        r=requests.get(f"https://api.exchangerate.host/convert?from={pair[:3]}&to={pair[3:6]}&amount=1",timeout=8).json()
        if r.get("result"):
            price=float(r["result"])
            PRICE_CACHE[pair]=price; CACHE_TIME[pair]=now
            sym=PRICE_CACHE.get(f"{pair}_SYMBOL",get_active_symbol(pair))
            return price, sym, False
    except: pass
    base_prices={"EURUSD":1.08,"GBPUSD":1.27,"USDJPY":150,"EURJPY":162,"AUDUSD":0.66,"EURGBP":0.85,"USDCHF":0.88,"GBPJPY":190}
    price=base_prices.get(pair,1.08)+random.uniform(-0.002,0.002)
    sym=PRICE_CACHE.get(f"{pair}_SYMBOL",get_active_symbol(pair))
    return price, sym, False

# ===== INDICATORS =====
def calc_bollinger(prices, period=20, std=2):
    if len(prices)<period: return None,None,None
    sma=sum(prices[-period:])/period
    var=sum((x-sma)**2 for x in prices[-period:])/period
    return sma+std*(var**0.5), sma, sma-std*(var**0.5)

def calc_rsi(prices, period=14):
    if len(prices)<period+1: return 50
    gains=[]; losses=[]
    for i in range(1,len(prices)):
        d=prices[i]-prices[i-1]
        gains.append(max(d,0)); losses.append(abs(min(d,0)))
    if len(gains)<period: return 50
    ag=sum(gains[-period:])/period; al=sum(losses[-period:])/period
    if al==0: return 88
    if ag==0: return 12
    return 100-(100/(1+ag/al))

def calc_ema(prices, period=21):
    if len(prices)<period: return prices[-1] if prices else 0
    k=2/(period+1); ema=prices[0]
    for p in prices[1:]: ema=p*k+ema*(1-k)
    return ema

def calc_ema_series(prices, period):
    k=2/(period+1); ema=prices[0] if prices else 0; lst=[]
    for p in prices:
        ema=p if not lst else p*k+ema*(1-k); lst.append(ema)
    return lst

def find_sr_levels(prices, lookback=40):
    if len(prices)<lookback: return None,None
    return min(prices[-lookback:]), max(prices[-lookback:])

# ===== SR ENGINE (OLD WORKING) =====
def analyze_sr(pair):
    price, used_sym, is_iq = get_price_hybrid(pair)
    if pair not in PRICE_HISTORY: PRICE_HISTORY[pair]=[]
    PRICE_HISTORY[pair].append(price)
    if len(PRICE_HISTORY[pair])>100: PRICE_HISTORY[pair].pop(0)
    prices=PRICE_HISTORY[pair]
    if len(prices)<40: return None
    rsi=calc_rsi(prices); ema9=calc_ema(prices,9)
    upper,middle,lower=calc_bollinger(prices,20,2)
    support,resistance=find_sr_levels(prices,40)
    if not upper or not support: return None
    d_sup=abs(price-support)/price*100; d_res=abs(price-resistance)/price*100
    near_sup=d_sup<0.18; near_res=d_res<0.18
    tag=f"{'IQ' if is_iq else 'FB'}-{'OTC' if 'OTC' in used_sym else 'REAL'}"
    expiry=180
    if near_sup and price<=lower*1.001 and rsi<=28 and prices[-1]>ema9:
        return {"pair":pair,"dir":"CALL","conf":90,"rsi":rsi,"reason":f"SUPPORT+BB {tag}","price":price,"used":used_sym,"expiry":expiry,"payout":85,"is_iq":is_iq,"type":"SR"}
    if near_res and price>=upper*0.999 and rsi>=72 and prices[-1]<ema9:
        return {"pair":pair,"dir":"PUT","conf":90,"rsi":rsi,"reason":f"RESISTANCE+BB {tag}","price":price,"used":used_sym,"expiry":expiry,"payout":85,"is_iq":is_iq,"type":"SR"}
    if near_sup and rsi<32 and price<lower*1.002:
        return {"pair":pair,"dir":"CALL","conf":85,"rsi":rsi,"reason":f"NEAR SUP {tag}","price":price,"used":used_sym,"expiry":expiry,"payout":80,"is_iq":is_iq,"type":"SR"}
    if near_res and rsi>68 and price>upper*0.998:
        return {"pair":pair,"dir":"PUT","conf":85,"rsi":rsi,"reason":f"NEAR RES {tag}","price":price,"used":used_sym,"expiry":expiry,"payout":80,"is_iq":is_iq,"type":"SR"}
    return None

# ===== MOMENTUM ENGINE (ADDED BACK) =====
def analyze_momentum(pair):
    base=pair.replace("-OTC","")
    prices=PRICE_HISTORY.get(base, [])
    if len(prices)<50: return None
    try:
        ema9_s=calc_ema_series(prices,9); ema21_s=calc_ema_series(prices,21); ema50_s=calc_ema_series(prices,50)
        c_now=prices[-1]; o_now=prices[-2] if len(prices)>1 else c_now
        c_prev=prices[-2]; o_prev=prices[-3] if len(prices)>2 else c_prev
        e9=ema9_s[-1]; e21=ema21_s[-1]; e50=ema50_s[-1]
        rsi=calc_rsi(prices,14)
        rsi_fast=calc_rsi(prices,7)
        mom1=(prices[-1]-prices[-2])/prices[-2]*100 if prices[-2]!=0 else 0
        mom3=(prices[-1]-prices[-4])/prices[-4]*100 if len(prices)>=4 and prices[-4]!=0 else 0
        # ATR approx
        tr_list=[abs(prices[i]-prices[i-1]) for i in range(1,len(prices[-15:]))]
        atr=sum(tr_list)/len(tr_list) if tr_list else 0.0004
        body=abs(c_now-o_now)
        # wicks fake
        upper_wick=max(0, c_now*0.0003); lower_wick=max(0, c_now*0.0003)
        is_green=c_now>o_now
        # filters
        if atr<0.00015: return {"pair":base,"dir":"CALL" if is_green else "PUT","conf":45,"rsi":rsi_fast,"reason":"Low ATR","price":c_now,"used":pair,"expiry":120,"payout":80,"is_iq":False,"type":"MOM","rejected":True}
        if body < atr*0.3: return {"pair":base,"dir":"CALL" if is_green else "PUT","conf":50,"rsi":rsi_fast,"reason":"Doji","price":c_now,"used":pair,"expiry":120,"payout":80,"is_iq":False,"type":"MOM","rejected":True}
        score=0; reasons=[]
        if is_green:
            if e9>e21 and e21>e50: score+=20; reasons.append("EMA Bull")
            elif e9>e21: score+=12
        else:
            if e9<e21 and e21<e50: score+=20; reasons.append("EMA Bear")
            elif e9<e21: score+=12
        if is_green:
            if 55<=rsi_fast<=68: score+=25; reasons.append(f"RSI {rsi_fast:.0f}")
            elif 50<=rsi_fast<=72: score+=15
        else:
            if 32<=rsi_fast<=45: score+=25; reasons.append(f"RSI {rsi_fast:.0f}")
            elif 28<=rsi_fast<=50: score+=15
        if is_green:
            if mom1>0.025 and mom3>0.05: score+=20; reasons.append(f"Mom {mom1:.3f}%")
            elif mom1>0.01: score+=10
        else:
            if mom1<-0.025 and mom3<-0.05: score+=20; reasons.append(f"Mom {mom1:.3f}%")
            elif mom1<-0.01: score+=10
        # engulfing
        bullish_engulf=c_now>o_prev and o_now<c_prev and is_green and not (c_prev>o_prev)
        bearish_engulf=c_now<o_prev and o_now>c_prev and not is_green and (c_prev>o_prev)
        if bullish_engulf and is_green: score+=15; reasons.append("Bull Engulf")
        if bearish_engulf and not is_green: score+=15; reasons.append("Bear Engulf")
        score=max(45,min(94,score+30))
        expiry=60 if "-OTC" in pair else (120 if abs(mom1)>0.05 else 180)
        sig="CALL" if is_green else "PUT"
        reason=" + ".join(reasons) if reasons else "Weak PA"
        return {"pair":base,"dir":sig,"conf":score,"rsi":rsi_fast,"reason":f"{reason} {'OTC' if 'OTC' in pair else 'REAL'}","price":c_now,"used":pair,"expiry":expiry,"payout":80,"is_iq":False,"type":"MOM","rejected":False}
    except Exception as e:
        print(f"Mom err {e}",flush=True)
        return None

def generate_chart(pair):
    prices=PRICE_HISTORY.get(pair,[])
    if len(prices)<20: return None
    try:
        support,resistance=find_sr_levels(prices,40)
        def ema_series(p,per):
            k=2/(per+1); e=p[0]; lst=[]
            for price in p:
                e=price if not lst else price*k+e*(1-k); lst.append(e)
            return lst
        ema9=ema_series(prices,9); ema21=ema_series(prices,21)
        fig,ax1=plt.subplots(1,1,figsize=(10,4),facecolor='#131722')
        ax1.set_facecolor('#131722')
        x=list(range(len(prices)))
        open_list=[prices[0]]+prices[:-1]
        high_list=[]; low_list=[]
        for i in range(len(prices)):
            o=open_list[i]; c=prices[i]; wiggle=abs(c-o)*0.3+c*0.0004
            high_list.append(max(o,c)+wiggle); low_list.append(min(o,c)-wiggle)
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
        last=prices[-1]; used=PRICE_CACHE.get(f"{pair}_SYMBOL",get_active_symbol(pair))
        ax1.set_title(f'{pair} • {used} • {round(last,5)} IQ:{"✅" if IQ_CONNECTED else "❌ FB"}',color='white',fontsize=11)
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

def build_full_text(pair,d,c,rsi,reason,price,used_sym, expiry=180, payout=80, typ="SR"):
    now=datetime.datetime.now()+datetime.timedelta(hours=1)
    entry=now+datetime.timedelta(seconds=BUFFER_SEC)
    exp=entry+datetime.timedelta(seconds=expiry)
    icon="🔺" if d=="CALL" else "🔻"
    strat="⚡ MOMENTUM" if typ=="MOM" else "🏔️ SR+BB"
    return f"""🚨 V33 {strat} {used_sym} 🚨

💱 {pair} → {used_sym}
{'📈' if d=='CALL' else '📉'} {d} - {expiry//60} MIN {icon}
🔥 {c}% 💎 | {reason}
💲 {round(float(price),5)} | RSI {round(float(rsi),1)} | Pay {payout}%
📡 IQ: {"✅ REAL" if IQ_CONNECTED else "❌ Fallback"}

🎯 ENTRY: {entry.strftime('%H:%M:%S')} WAT (in {BUFFER_SEC}s)
⏰ EXPIRY: {exp.strftime('%H:%M:%S')} WAT

👉 You have {BUFFER_SEC}s to place {d} on {used_sym}!"""

bot = telebot.TeleBot(TOKEN, threaded=False) if ':' in TOKEN else None

if bot:
    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        if OWNER_ID is None: OWNER_ID=m.chat.id
        mode="🌙 OTC" if is_otc_time() else "☀️ REAL"
        if OWNER_ID and m.chat.id==OWNER_ID:
            bot.send_message(m.chat.id,f"👑 V33 HYBRID OWNER {mode} IQ:{'✅' if IQ_CONNECTED else '❌ FB'}\nDual Engine SR+BB + MOMENTUM + {BUFFER_SEC}s\n/resume /pause /test /status /levels /balance\n/chart EURUSD")
            return
        left=2-FREE_USERS.get(str(m.chat.id),0)
        bot.send_message(m.chat.id,f"🚀 V33 HYBRID {mode}\n{left} free left")

    @bot.message_handler(commands=['chart','levels','balance','status','id','pause','resume','test','scan'])
    def all_cmd(m):
        global SCANNING,OWNER_ID
        txt=m.text
        if txt.startswith("/id"):
            bot.send_message(m.chat.id,f"ID {m.from_user.id} Owner {OWNER_ID} OTC {is_otc_time()} IQ {IQ_CONNECTED} iq_obj {iq is not None} Sym {PRICE_CACHE.get('EURUSD_SYMBOL','?')} Hist {len(PRICE_HISTORY.get('EURUSD',[]))}"); return
        if txt.startswith("/balance"):
            if OWNER_ID and m.chat.id!=OWNER_ID: return
            if not iq or not IQ_CONNECTED:
                bot.send_message(m.chat.id,f"⚠️ IQ not connected, using fallback\nAdd IQ_EMAIL/IQ_PASS in Render to get REAL balance"); return
            try:
                logging.disable(logging.CRITICAL)
                bal=iq.get_balance(); mode=iq.get_balance_mode()
                logging.disable(logging.NOTSET); logging.disable(logging.ERROR)
                bot.send_message(m.chat.id,f"💰 IQ Balance {mode} ${bal}")
            except Exception as e: bot.send_message(m.chat.id,f"Bal err {e}")
            return
        if txt.startswith("/chart"):
            try:
                parts=txt.split(); pair=parts[1].upper() if len(parts)>1 else "EURUSD"
                base=pair.replace("-OTC","")
                if base not in PAIRS: base="EURUSD"
                if "-OTC" in pair: PRICE_CACHE[f"{base}_SYMBOL"]=pair
                get_price_hybrid(base)
                prices=PRICE_HISTORY.get(base,[])
                if len(prices)<25: bot.send_message(m.chat.id,f"⏳ Collecting {base} {len(prices)}/25..."); return
                bot.send_message(m.chat.id,f"📈 Generating {PRICE_CACHE.get(f'{base}_SYMBOL',base)}...")
                chart_path=generate_chart(base)
                if chart_path and os.path.exists(chart_path):
                    with open(chart_path,'rb') as f: bot.send_photo(m.chat.id,f,caption=f"📊 {PRICE_CACHE.get(f'{base}_SYMBOL',base)} IQ {'✅' if IQ_CONNECTED else '❌ FB'}")
                else: bot.send_message(m.chat.id,"❌ Chart failed")
            except Exception as e: bot.send_message(m.chat.id,f"Error {e}")
            return
        if OWNER_ID and m.chat.id!=OWNER_ID: return
        if txt.startswith("/status"):
            t=f"OTC: {is_otc_time()} IQ {IQ_CONNECTED} SCAN {SCANNING}\n"
            for p in PAIRS: t+=f"{p}: {len(PRICE_HISTORY.get(p,[]))} Sym {PRICE_CACHE.get(f'{p}_SYMBOL','?')}\n"
            bot.send_message(m.chat.id,t)
        elif txt.startswith("/levels"):
            mode="🌙 OTC" if is_otc_time() else "☀️ REAL"
            t=f"📊 V33 LEVELS {mode} IQ:{'✅ REAL' if IQ_CONNECTED else '❌ Fallback'}\n━━━━━━━━━━━━━━━\n"
            for pair in PAIRS:
                prices=PRICE_HISTORY.get(pair,[])
                if len(prices)<40: t+=f"⏳ {pair}: {len(prices)}/40\n"; continue
                sup,res=find_sr_levels(prices,40)
                upper,mid,lower=calc_bollinger(prices,20,2); rsi=calc_rsi(prices); price=prices[-1]
                if not upper: continue
                used=PRICE_CACHE.get(f"{pair}_SYMBOL",get_active_symbol(pair))
                mom=analyze_momentum(used)
                t+=f"{'🌙' if 'OTC' in used else '☀️'} {pair}→{used} {round(price,5)} RSI {round(rsi,1)}\n"
                if mom and not mom.get('rejected') and mom['conf']>=70:
                    t+=f"  ⚡ MOM {mom['dir']} {mom['conf']}% {mom['reason']} Exp {mom['expiry']}s\n"
            t+=f"━━━━━━━━━━━━━━━\nBuffer {BUFFER_SEC}s"
            bot.send_message(m.chat.id,t)
        elif txt.startswith("/resume"): SCANNING=True; bot.send_message(m.chat.id,"▶️ ON")
        elif txt.startswith("/pause"): SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused")
        elif txt.startswith("/test") or txt.startswith("/scan"):
            pair=random.choice(PAIRS); sym=get_active_symbol(pair)
            sr=analyze_sr(pair); mom=analyze_momentum(sym)
            candidates=[]
            if sr: candidates.append(sr)
            if mom and not mom.get('rejected') and mom['conf']>=60: candidates.append(mom)
            if candidates:
                best=max(candidates,key=lambda x:x['conf'])
                d=best['dir']; c=best['conf']; rsi=best['rsi']; reason=best['reason']; price=best['price']; sym=best['used']; expiry=best['expiry']; payout=best['payout']; typ=best['type']
            else:
                d=random.choice(["CALL","PUT"]); c=90; rsi=23.5; reason="TEST"; price=1.08; expiry=180; payout=80; typ="SR"
            mk=InlineKeyboardMarkup(row_width=1)
            mk.add(InlineKeyboardButton(f"👥 Users {sym} {d} {c}% {typ} {expiry}s",callback_data=f"users_{pair}_{d}_{c}_{rsi}_{reason}_{price}_{expiry}_{payout}_{typ}"),
                   InlineKeyboardButton(f"📢 Channel {sym}",callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{reason}_{price}_{expiry}_{payout}_{typ}"),
                   InlineKeyboardButton(f"🚀 BOTH {sym}",callback_data=f"both_{pair}_{d}_{c}_{rsi}_{reason}_{price}_{expiry}_{payout}_{typ}"),
                   InlineKeyboardButton("❌ Skip",callback_data="skip"))
            bot.send_message(m.chat.id,f"TEST {pair}→{sym} {d} {c}% {typ}\n{reason}\n🎯 Entry in {BUFFER_SEC}s + {expiry}s\nWhere?",reply_markup=mk)

    @bot.callback_query_handler(func=lambda c: True)
    def cb(call):
        global LAST_SIGNAL_TIME
        if OWNER_ID and call.message.chat.id!=OWNER_ID: return
        if call.data=="skip": bot.edit_message_text("❌ Skipped",call.message.chat.id,call.message.message_id); return
        try:
            parts=call.data.split("_"); typ_send=parts[0]; pair=parts[1]; d=parts[2]; c=parts[3]; rsi=parts[4]; reason=parts[5]; price=parts[6]
            expiry=int(parts[7]) if len(parts)>7 else 180; payout=int(parts[8]) if len(parts)>8 else 80; strat_typ=parts[9] if len(parts)>9 else "SR"
            used_sym=PRICE_CACHE.get(f"{pair}_SYMBOL",get_active_symbol(pair))
            full=build_full_text(pair,d,c,rsi,reason,float(price),used_sym,expiry,payout,strat_typ)
            chart_path=generate_chart(pair)
            if typ_send in ["users","both"]:
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
            if typ_send in ["chan","both"]:
                try:
                    if chart_path and os.path.exists(chart_path):
                        with open(chart_path,'rb') as f: bot.send_photo(CHANNEL_ID,f,caption=full)
                    else: bot.send_message(CHANNEL_ID,full)
                except: pass
            LAST_SIGNAL_TIME=time.time()
            bot.edit_message_text(f"✅ SENT {used_sym} {typ_send} {d} {c}% {strat_typ} Exp {expiry}s +{BUFFER_SEC}s",call.message.chat.id,call.message.message_id)
        except Exception as e: bot.send_message(call.message.chat.id,f"Error {e}")

    @app.route(f'/{TOKEN}',methods=['POST'])
    def webhook():
        if request.headers.get('content-type')=='application/json':
            js=request.get_data().decode('utf-8'); upd=telebot.types.Update.de_json(js); bot.process_new_updates([upd]); return ''
        return 'ok',200
    @app.route('/')
    def home(): return f"V33 HYBRID MOM IQ:{IQ_CONNECTED} Buffer:{BUFFER_SEC}s",200

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
                sr=analyze_sr(pair)
                sym=get_active_symbol(pair)
                mom=analyze_momentum(sym)
                candidates=[]
                if sr: candidates.append(sr)
                if mom and not mom.get('rejected') and mom['conf']>=70: candidates.append(mom)
                if not candidates: continue
                best=max(candidates,key=lambda x:x['conf'])
                d=best['dir']; c=best['conf']; rsi=best['rsi']; reason=best['reason']; price=best['price']; used_sym=best['used']; expiry=best['expiry']; payout=best['payout']; typ=best['type']
                mk=InlineKeyboardMarkup(row_width=1)
                mk.add(InlineKeyboardButton(f"👥 Users {used_sym} {d} {c}% {typ} {expiry}s",callback_data=f"users_{pair}_{d}_{c}_{rsi}_{reason}_{price}_{expiry}_{payout}_{typ}"),
                       InlineKeyboardButton(f"📢 Channel {used_sym}",callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{reason}_{price}_{expiry}_{payout}_{typ}"),
                       InlineKeyboardButton(f"🚀 BOTH {used_sym} {typ}",callback_data=f"both_{pair}_{d}_{c}_{rsi}_{reason}_{price}_{expiry}_{payout}_{typ}"),
                       InlineKeyboardButton("❌ Skip",callback_data="skip"))
                txt=f"🔔 V33 READY! {pair}→{used_sym} {d} {c}% {typ} Price {round(float(price),5)} RSI {round(float(rsi),1)} {reason} Entry {BUFFER_SEC}s Exp {expiry}s"
                bot.send_message(OWNER_ID,txt,reply_markup=mk)
                LAST_SIGNAL_TIME=time.time()
                time.sleep(120)
                break
        except Exception as e: print(f"SCAN {e}",flush=True); time.sleep(10)

threading.Thread(target=scanner,daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
