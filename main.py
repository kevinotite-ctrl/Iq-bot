import os, time, threading, datetime, json, requests, random
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import logging
import warnings

warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.CRITICAL)
logging.disable(logging.ERROR)

print("=== V31 IQ REAL + OTC NIGHT/WEEKEND ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
IQ_EMAIL = os.getenv("IQ_EMAIL")
IQ_PASS = os.getenv("IQ_PASS")
CHANNEL_ID = "@trailblazeebot"
PRICE = "$10/month"

OWNER_ID = None
SCANNING = True
LAST_SIGNAL_TIME = time.time()

# Regular pairs
PAIRS = ["EURUSD","GBPUSD","USDJPY","EURJPY","AUDUSD","EURGBP","USDCHF","GBPJPY"]
# OTC mapping
OTC_MAP = {
    "EURUSD":"EURUSD-OTC",
    "GBPUSD":"GBPUSD-OTC",
    "USDJPY":"USDJPY-OTC",
    "EURJPY":"EURJPY-OTC",
    "AUDUSD":"AUDUSD-OTC",
    "EURGBP":"EURGBP-OTC",
    "USDCHF":"USDCHF-OTC",
    "GBPJPY":"GBPJPY-OTC"
}
OTC_PAIRS = list(OTC_MAP.values())

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

# ===== IQ + OTC LOGIC =====
iq = None
IQ_CONNECTED = False
IQ_LOCK = threading.Lock()

def init_iq():
    global iq, IQ_CONNECTED
    if not IQ_EMAIL or not IQ_PASS:
        print("IQ_EMAIL/PASS not set - fallback", flush=True)
        return
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL)
        iq = IQ_Option(IQ_EMAIL, IQ_PASS)
        iq.connect()
        IQ_CONNECTED = iq.check_connect()
        logging.disable(logging.NOTSET)
        logging.disable(logging.ERROR)
        print(f"IQ Connected: {IQ_CONNECTED}", flush=True)
    except Exception as e:
        print(f"IQ Failed: {e}", flush=True)

threading.Thread(target=init_iq, daemon=True).start()

def iq_reconnect():
    global iq, IQ_CONNECTED
    try:
        from iqoptionapi.stable_api import IQ_Option
        logging.disable(logging.CRITICAL)
        iq = IQ_Option(IQ_EMAIL, IQ_PASS)
        iq.connect()
        IQ_CONNECTED = iq.check_connect()
        logging.disable(logging.NOTSET)
        logging.disable(logging.ERROR)
        print(f"IQ Reconnected: {IQ_CONNECTED}", flush=True)
        return IQ_CONNECTED
    except:
        IQ_CONNECTED = False
        return False

def is_otc_time():
    now = datetime.datetime.now() + datetime.timedelta(hours=1)  # WAT
    is_weekend = now.weekday() >= 5  # Sat=5 Sun=6
    is_night = now.hour >= 21 or now.hour < 7  # 9pm-7am WAT low liquidity
    return is_weekend or is_night

def get_active_symbol(base_pair):
    """Auto pick OTC at night/weekend"""
    if is_otc_time():
        return OTC_MAP.get(base_pair, base_pair)
    return base_pair

def get_iq_candles(base_pair, count=100):
    if not IQ_CONNECTED and not iq_reconnect():
        return None, base_pair
    active_sym = get_active_symbol(base_pair)
    # Try order: active (OTC if night) -> regular -> other OTC
    try_list = [active_sym, base_pair, OTC_MAP.get(base_pair, "")]
    try_list = [x for x in try_list if x]
    try_list = list(dict.fromkeys(try_list))  # dedup
    
    for sym in try_list:
        try:
            with IQ_LOCK:
                logging.disable(logging.CRITICAL)
                candles = iq.get_candles(sym, 60, count, time.time())
                logging.disable(logging.NOTSET)
                logging.disable(logging.ERROR)
            if candles and len(candles) > 20:
                candles = sorted(candles, key=lambda x: x['from'])
                PRICE_CACHE[f"{base_pair}_SYMBOL"] = sym
                PRICE_CACHE[f"{base_pair}_OTC_MODE"] = "OTC" in sym
                return candles, sym
        except:
            continue
    return None, base_pair

def get_price(base_pair):
    candles, used_sym = get_iq_candles(base_pair, 100)
    if candles:
        closes = [c['close'] for c in candles]
        PRICE_HISTORY[base_pair] = closes[-100:]
        PRICE_HISTORY[f"{base_pair}_FULL"] = candles[-100:]
        save_json(HISTORY_FILE, PRICE_HISTORY)
        return closes[-1], used_sym
    # fallback cached
    if base_pair in PRICE_HISTORY and PRICE_HISTORY[base_pair]:
        sym = PRICE_CACHE.get(f"{base_pair}_SYMBOL", base_pair)
        return PRICE_HISTORY[base_pair][-1], sym
    return 1.08, base_pair

# ===== STRATEGY SAME =====
def calc_bollinger(prices, period=20, std=2):
    if len(prices) < period: return None, None, None
    sma = sum(prices[-period:]) / period
    var = sum((x - sma) ** 2 for x in prices[-period:]) / period
    return sma + std*(var**0.5), sma, sma - std*(var**0.5)

def calc_rsi(prices, period=14):
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

def calc_rsi_series(prices, period=14):
    return [50 if i<period else calc_rsi(prices[:i+1], period) for i in range(len(prices))]

def calc_ema(prices, period=21):
    if len(prices)<period: return prices[-1] if prices else 0
    k=2/(period+1); ema=prices[0]
    for p in prices[1:]: ema=p*k+ema*(1-k)
    return ema

def calc_ema_series(prices, period=9):
    ema_list=[]; k=2/(period+1); ema=prices[0] if prices else 0
    for i,p in enumerate(prices):
        ema=p if i==0 else p*k+ema*(1-k)
        ema_list.append(ema)
    return ema_list

def find_sr_levels(prices, lookback=40):
    if len(prices) < lookback: return None, None
    return min(prices[-lookback:]), max(prices[-lookback:])

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
        upper_list=[]; mid_list=[]; lower_list=[]
        for i in range(len(prices)):
            if i<20: upper_list.append(None); mid_list.append(None); lower_list.append(None)
            else: u,m,l=calc_bollinger(prices[:i+1],20,2); upper_list.append(u); mid_list.append(m); lower_list.append(l)
        ema9=calc_ema_series(prices,9); ema21=calc_ema_series(prices,21); rsi_s=calc_rsi_series(prices,14)
        fig,(ax1,ax2)=plt.subplots(2,1,figsize=(10,6),gridspec_kw={'height_ratios':[3,1]},facecolor='#131722')
        ax1.set_facecolor('#131722'); ax2.set_facecolor('#131722')
        x=list(range(len(prices)))
        for i in range(len(x)):
            o=open_list[i]; h=high_list[i]; l=low_list[i]; c=prices[i]
            col='#26a69a' if c>=o else '#ef5350'
            ax1.plot([x[i],x[i]],[l,h],color=col,linewidth=0.8,alpha=0.9,zorder=2)
            bh=abs(c-o); 
            if bh<(h-l)*0.08: bh=(h-l)*0.08
            ax1.add_patch(Rectangle((x[i]-0.35,min(o,c)),0.7,bh,facecolor=col,edgecolor=col,linewidth=0.8,zorder=3))
        vid=[i for i,u in enumerate(upper_list) if u is not None]
        if vid:
            vu=[upper_list[i] for i in vid]; vl=[lower_list[i] for i in vid]; vx=[x[i] for i in vid]
            ax1.fill_between(vx,vl,vu,color='#5d9cf5',alpha=0.12,label='BB'); ax1.plot(vx,vu,color='#5d9cf5',linewidth=0.8,alpha=0.5); ax1.plot(vx,vl,color='#5d9cf5',linewidth=0.8,alpha=0.5)
        ax1.plot(x,ema9,color='#FFD700',linewidth=1.2,label='EMA9'); ax1.plot(x,ema21,color='orange',linewidth=1.2,label='EMA21')
        if support: ax1.axhline(y=support,color='#26a69a',linestyle='--',linewidth=1.2,label=f'SUP {round(support,5)}')
        if resistance: ax1.axhline(y=resistance,color='#ef5350',linestyle='--',linewidth=1.2,label=f'RES {round(resistance,5)}')
        last=prices[-1]; lr=rsi_s[-1]
        used_sym=PRICE_CACHE.get(f"{pair}_SYMBOL",pair)
        is_otc="OTC" in used_sym
        ax1.set_title(f'{pair} • {used_sym} • {"🌙 OTC NIGHT/WEEKEND" if is_otc else "☀️ REAL"} • Price:{round(last,5)} RSI:{round(lr,1)} IQ:{"✅" if IQ_CONNECTED else "❌"}',color='white',fontsize=11)
        ax1.legend(facecolor='#131722',edgecolor='gray',labelcolor='white',fontsize=7,loc='upper left'); ax1.tick_params(colors='gray'); ax1.grid(color='#2a2e39',linewidth=0.3)
        ax2.plot(x,rsi_s,color='#b388ff',linewidth=1.2); ax2.axhline(y=70,color='red',linestyle='--',alpha=0.6); ax2.axhline(y=30,color='green',linestyle='--',alpha=0.6)
        ax2.set_ylim(0,100); ax2.set_ylabel('RSI',color='white'); ax2.tick_params(colors='gray'); ax2.grid(color='#2a2e39',linewidth=0.3)
        plt.tight_layout(); path=f"/tmp/{pair}_chart.png"; plt.savefig(path,facecolor='#131722',dpi=150,bbox_inches='tight'); plt.close(); return path
    except Exception as e:
        print(f"Chart err {e}",flush=True); plt.close(); return None

def analyze_real(pair):
    price, used_sym = get_price(pair)
    prices = PRICE_HISTORY.get(pair, [])
    if len(prices)<40: return None
    rsi=calc_rsi(prices); ema9=calc_ema(prices,9); ema21=calc_ema(prices,21); ema50=calc_ema(prices,50)
    upper,middle,lower=calc_bollinger(prices,20,2)
    support,resistance=find_sr_levels(prices,40)
    if not upper or not support: return None
    d_res=abs(price-resistance)/price*100; d_sup=abs(price-support)/price*100
    near_res=d_res<0.18; near_sup=d_sup<0.18
    tag = "OTC" if "OTC" in used_sym else "REAL"
    if near_sup and price<=lower*1.001 and rsi<=28 and prices[-1]>ema9:
        return "CALL",90,round(rsi,1),f"SUPPORT+BB {tag}",f"IQ {used_sym} SUPPORT {round(support,5)} + BB {round(lower,5)} + RSI {round(rsi,1)} {tag}",round(price,5),used_sym
    if near_res and price>=upper*0.999 and rsi>=72 and prices[-1]<ema9:
        return "PUT",90,round(rsi,1),f"RESISTANCE+BB {tag}",f"IQ {used_sym} RESISTANCE {round(resistance,5)} + BB {round(upper,5)} + RSI {round(rsi,1)} {tag}",round(price,5),used_sym
    if near_sup and rsi<32 and price<lower*1.002:
        return "CALL",85,round(rsi,1),f"NEAR SUP {tag}",f"IQ {used_sym} Near Sup {round(support,5)} BB + RSI {round(rsi,1)}",round(price,5),used_sym
    if near_res and rsi>68 and price>upper*0.998:
        return "PUT",85,round(rsi,1),f"NEAR RES {tag}",f"IQ {used_sym} Near Res {round(resistance,5)} BB + RSI {round(rsi,1)}",round(price,5),used_sym
    return None

def is_paid(uid):
    if OWNER_ID and str(uid)==str(OWNER_ID): return True
    if str(uid) in PAID_USERS and time.time()<PAID_USERS[str(uid)]: return True
    return False
def can_send_free(uid): return True if is_paid(uid) else FREE_USERS.get(str(uid),0)<2
def use_free(uid):
    if is_paid(uid): return
    FREE_USERS[str(uid)]=FREE_USERS.get(str(uid),0)+1; save_json(FREE_FILE,FREE_USERS)
def get_expiry(uid): return datetime.datetime.fromtimestamp(PAID_USERS[str(uid)]).strftime('%d %b %Y') if str(uid) in PAID_USERS else "Not paid"

bot = telebot.TeleBot(TOKEN, threaded=False) if ':' in TOKEN else None

def build_full_text(pair,d,c,rsi,ema,price,reason,used_sym):
    now=datetime.datetime.now()+datetime.timedelta(hours=1); exp=now+datetime.timedelta(minutes=3)
    icon="🔺" if d=="CALL" else "🔻"
    otc_tag="🌙 OTC NIGHT/WEEKEND" if "OTC" in used_sym else "☀️ REAL MARKET"
    return f"""🚨 V31 IQ {otc_tag} 🚨

💱 {pair} → {used_sym}
{'📈' if d=='CALL' else '📉'} {d} - 3 MIN {icon}
🔥 {c}% 💎 | {ema}
💲 {price} | RSI {rsi}
📡 IQ: {"✅ REAL" if IQ_CONNECTED else "❌"}

📊 {reason}
⏰ {now.strftime('%H:%M')} → {exp.strftime('%H:%M')} WAT

👉 Trade {d} NOW on {used_sym}!"""

if bot:
    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        if OWNER_ID is None: OWNER_ID=m.chat.id
        mode="🌙 OTC MODE (Night/Weekend)" if is_otc_time() else "☀️ REAL MODE"
        if OWNER_ID and m.chat.id==OWNER_ID:
            bot.send_message(m.chat.id,f"👑 V31 IQ+OTC OWNER\n{mode}\nIQ:{'✅' if IQ_CONNECTED else '❌'} Active:{PRICE_CACHE.get(f'{PAIRS[0]}_SYMBOL','?')}\n/resume /pause /test /status /levels\n/chart EURUSD\n/chart EURUSD-OTC")
            return
        left=2-FREE_USERS.get(str(m.chat.id),0)
        bot.send_message(m.chat.id,f"🚀 V31 IQ+OTC\n{mode}\n{left} free left\n/chart EURUSD")

    @bot.message_handler(commands=['chart'])
    def chart_cmd(m):
        try:
            parts=m.text.split(); pair=parts[1].upper() if len(parts)>1 else "EURUSD"
            base=pair.replace("-OTC","")
            if base not in PAIRS and pair not in OTC_PAIRS: bot.send_message(m.chat.id,f"Use: {', '.join(PAIRS)} or {', '.join(OTC_PAIRS)}"); return
            # if user typed OTC directly
            if "-OTC" in pair: base=pair.replace("-OTC",""); PRICE_CACHE[f"{base}_SYMBOL"]=pair
            else: base=pair
            # force fetch
            get_price(base)
            prices=PRICE_HISTORY.get(base,[])
            if len(prices)<25: bot.send_message(m.chat.id,f"⏳ Fetching IQ {PRICE_CACHE.get(f'{base}_SYMBOL',base)}... {len(prices)}/25"); return
            bot.send_message(m.chat.id,f"📈 Generating {PRICE_CACHE.get(f'{base}_SYMBOL',base)} chart...")
            chart_path=generate_chart(base)
            if chart_path and os.path.exists(chart_path):
                with open(chart_path,'rb') as f: bot.send_photo(m.chat.id,f,caption=f"📊 {PRICE_CACHE.get(f'{base}_SYMBOL',base)} IQ {'✅' if IQ_CONNECTED else '❌'} {'🌙 OTC' if 'OTC' in PRICE_CACHE.get(f'{base}_SYMBOL','') else '☀️ REAL'}")
            else: bot.send_message(m.chat.id,"❌ Chart failed")
        except Exception as e: bot.send_message(m.chat.id,f"Error {e}")

    @bot.message_handler(commands=['levels'])
    def levels_cmd(m):
        mode="🌙 OTC NIGHT/WEEKEND" if is_otc_time() else "☀️ REAL"
        txt=f"📊 V31 IQ+OTC LEVELS {mode} IQ:{'✅' if IQ_CONNECTED else '❌'}\n━━━━━━━━━━━━━━━\n\n"
        for pair in PAIRS:
            prices=PRICE_HISTORY.get(pair,[])
            if len(prices)<40: txt+=f"⏳ {pair}: {len(prices)}/40...\n\n"; continue
            support,resistance=find_sr_levels(prices,40)
            upper,middle,lower=calc_bollinger(prices,20,2); rsi=calc_rsi(prices); price=prices[-1]
            if not upper: continue
            used=PRICE_CACHE.get(f"{pair}_SYMBOL",pair); is_otc="OTC" in used
            txt+=f"{'🌙' if is_otc else '☀️'} {pair} → {used} {round(price,5)} RSI {round(rsi,1)}\n  Sup {round(support,5)} Res {round(resistance,5)}\n\n"
        txt+=f"━━━━━━━━━━━━━━━\nOTC Active: {'YES 🌙' if is_otc_time() else 'NO ☀️'}\n/chart EURUSD or /chart EURUSD-OTC"
        bot.send_message(m.chat.id,txt)

    @bot.message_handler(commands=['approve','paidlist','resume','pause','test','status','scan','id'])
    def other(m):
        global SCANNING,OWNER_ID,LAST_SIGNAL_TIME
        if m.text.startswith("/id"): bot.send_message(m.chat.id,f"ID {m.from_user.id} Owner {OWNER_ID} OTC-Time {is_otc_time()} IQ {IQ_CONNECTED} Sym {PRICE_CACHE.get('EURUSD_SYMBOL','?')}"); return
        if OWNER_ID and m.chat.id!=OWNER_ID: return
        if m.text.startswith("/approve"):
            try: p=m.text.split(); uid=p[1]; d=int(p[2]) if len(p)>2 else 30; PAID_USERS[str(uid)]=time.time()+d*24*3600; save_json(PAID_FILE,PAID_USERS); bot.send_message(m.chat.id,f"✅ {uid} till {get_expiry(uid)}")
            except: bot.send_message(m.chat.id,"Use: /approve ID 30")
        elif m.text.startswith("/paidlist"): bot.send_message(m.chat.id,"💰 Paid:\n"+"\n".join([f"{k} - {get_expiry(k)}" for k in PAID_USERS]) if PAID_USERS else "No paid")
        elif m.text.startswith("/status"): bot.send_message(m.chat.id,f"OTC Time: {is_otc_time()} {'🌙' if is_otc_time() else '☀️'}\nIQ {IQ_CONNECTED} SCAN {SCANNING}\nEURUSD Sym {PRICE_CACHE.get('EURUSD_SYMBOL','?')}\n"+ "\n".join([f"{p}: {len(PRICE_HISTORY.get(p,[]))}" for p in PAIRS]))
        elif m.text.startswith("/resume"): SCANNING=True; bot.send_message(m.chat.id,"▶️ ON")
        elif m.text.startswith("/pause"): SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused")
        elif m.text.startswith("/test") or m.text.startswith("/scan"):
            pair=random.choice(PAIRS); d=random.choice(["CALL","PUT"]); c=90; rsi=23.5 if d=="CALL" else 76.2; ema="SUP+BB"; price=round(random.uniform(1.05,1.35),5); sym=get_active_symbol(pair)
            mk=InlineKeyboardMarkup(row_width=1); mk.add(InlineKeyboardButton(f"👥 Users {sym}",callback_data=f"users_{pair}_{d}_{c}_{rsi}_{ema}_{price}"), InlineKeyboardButton(f"📢 Channel {sym}",callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{ema}_{price}"), InlineKeyboardButton(f"🚀 BOTH {sym}",callback_data=f"both_{pair}_{d}_{c}_{rsi}_{ema}_{price}"), InlineKeyboardButton("❌ Skip",callback_data="skip"))
            bot.send_message(m.chat.id,f"TEST {pair}→{sym} {d} {c}% { '🌙 OTC' if 'OTC' in sym else '☀️ REAL'}\nWhere?",reply_markup=mk)

    @bot.callback_query_handler(func=lambda c: True)
    def cb(call):
        global LAST_SIGNAL_TIME
        if OWNER_ID and call.message.chat.id!=OWNER_ID: return
        if call.data=="skip": bot.edit_message_text("❌ Skipped",call.message.chat.id,call.message.message_id); return
        try:
            parts=call.data.split("_"); typ=parts[0]; pair=parts[1]; d=parts[2]; c=parts[3]; rsi=parts[4]; ema=parts[5]; price=parts[6]
            used_sym=PRICE_CACHE.get(f"{pair}_SYMBOL",get_active_symbol(pair))
            full=build_full_text(pair,d,c,rsi,ema,price,f"RSI {rsi}+{ema} {used_sym}",used_sym)
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
            bot.edit_message_text(f"✅ SENT {used_sym} {typ}",call.message.chat.id,call.message.message_id)
        except Exception as e: bot.send_message(call.message.chat.id,f"Error {e}")

    @app.route(f'/{TOKEN}',methods=['POST'])
    def webhook():
        if request.headers.get('content-type')=='application/json':
            js=request.get_data().decode('utf-8'); upd=telebot.types.Update.de_json(js); bot.process_new_updates([upd]); return ''
        return 'ok',200
    @app.route('/')
    def home(): return f"V31 IQ+OTC LIVE IQ:{IQ_CONNECTED} OTC-Time:{is_otc_time()} Sym:{PRICE_CACHE.get('EURUSD_SYMBOL','?')}",200

    def set_wh():
        time.sleep(5)
        if RENDER_URL:
            try: requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True",timeout=10); time.sleep(2); url=f"{RENDER_URL}/{TOKEN}"; r=requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}",timeout=10); print(r.text,flush=True)
            except Exception as e: print(e,flush=True)
    threading.Thread(target=set_wh,daemon=True).start()

def scanner():
    global LAST_SIGNAL_TIME
    while True:
        try:
            time.sleep(60)
            if not OWNER_ID or not SCANNING or not bot: continue
            for pair in PAIRS:
                res=analyze_real(pair)
                if not res: continue
                d,c,rsi,ema,reason,price,used_sym=res
                mk=InlineKeyboardMarkup(row_width=1)
                mk.add(InlineKeyboardButton(f"👥 Users {used_sym}",callback_data=f"users_{pair}_{d}_{c}_{rsi}_{ema}_{price}"), InlineKeyboardButton(f"📢 Channel {used_sym}",callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{ema}_{price}"), InlineKeyboardButton(f"🚀 BOTH {used_sym}",callback_data=f"both_{pair}_{d}_{c}_{rsi}_{ema}_{price}"), InlineKeyboardButton("❌ Skip",callback_data="skip"))
                txt=f"🔔 V31 IQ {used_sym} READY!\n{pair}→{used_sym} {d} {c}% Price {price} RSI {rsi}\n{reason}\n{'🌙 OTC NIGHT' if 'OTC' in used_sym else '☀️ REAL'}"
                bot.send_message(OWNER_ID,txt,reply_markup=mk)
                LAST_SIGNAL_TIME=time.time()
                time.sleep(120)
                break
        except Exception as e: print(f"SCAN {e}",flush=True); time.sleep(10)

threading.Thread(target=scanner,daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
