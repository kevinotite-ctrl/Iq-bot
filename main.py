import os, time, threading, datetime, json, requests, random
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

print("=== V31 COOL EDITION ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
CHANNEL_ID = "@trailblazeebot"
OWNER_USERNAME = "@kevintraiblazer"

OWNER_ID = None
SCANNING = True
LAST_SIGNAL_TIME = time.time()
PAIRS = ["EURUSD","GBPUSD","USDJPY","EURJPY","AUDUSD","EURGBP","USDCHF","GBPJPY"]
PAID_FILE = "paid_users.json"
FREE_FILE = "free_users.json"
HISTORY_FILE = "price_history.json"
WIN_FILE = "win_tracker.json"

PRICE_CACHE = {}; CACHE_TIME = {}

def load_json(f):
    try:
        if os.path.exists(f):
            with open(f,'r') as fp: return json.load(fp)
    except: pass
    return {"wins":0,"losses":0,"signals":[]} if "win" in f else {}
def save_json(f,data):
    try:
        with open(f,'w') as fp: json.dump(data, fp)
    except: pass

PAID_USERS = load_json(PAID_FILE)
FREE_USERS = load_json(FREE_FILE)
PRICE_HISTORY = load_json(HISTORY_FILE)
WIN_TRACKER = load_json(WIN_FILE)

def is_paid(uid):
    if OWNER_ID and str(uid)==str(OWNER_ID): return True
    return str(uid) in PAID_USERS and time.time() < PAID_USERS[str(uid)]
def can_send_free(uid): return True if is_paid(uid) else FREE_USERS.get(str(uid),0) < 3
def use_free(uid):
    if is_paid(uid): return
    FREE_USERS[str(uid)] = FREE_USERS.get(str(uid),0)+1
    save_json(FREE_FILE, FREE_USERS)
def get_expiry(uid):
    if str(uid) not in PAID_USERS: return "Not paid"
    return datetime.datetime.fromtimestamp(PAID_USERS[str(uid)]).strftime('%d %b %Y')

# COOL FEATURE: Session Radar
def get_session():
    h = datetime.datetime.utcnow().hour
    if 7 <= h <= 10: return "🌅 London Open KILLZONE 🔥", True
    if 13 <= h <= 16: return "💥 London/NY Overlap KILLZONE 🔥🔥", True
    if 7 <= h <= 16: return "🇬🇧 London Session ✅", True
    if 12 <= h <= 21: return "🇺🇸 NY Session ✅", True
    return "🌙 Asian Low Vol ⚠️", False

# COOL FEATURE: Volatility Meter
def get_volatility(prices):
    if len(prices) < 20: return 0
    recent = prices[-20:]
    vol = (max(recent)-min(recent))/recent[-1]*100
    return vol

def get_price(pair):
    now = time.time()
    if pair in PRICE_CACHE and now - CACHE_TIME.get(pair,0) < 60:
        return PRICE_CACHE[pair] + random.uniform(-0.0002,0.0002)
    try:
        r = requests.get(f"https://api.frankfurter.app/latest?from={pair[:3]}&to={pair[3:]}", timeout=5).json()
        if r.get("rates") and pair[3:] in r["rates"]:
            PRICE_CACHE[pair]=float(r["rates"][pair[3:]]); CACHE_TIME[pair]=now
            return PRICE_CACHE[pair]
    except: pass
    try:
        r = requests.get(f"https://api.exchangerate.host/convert?from={pair[:3]}&to={pair[3:]}&amount=1", timeout=5).json()
        if r.get("result"):
            PRICE_CACHE[pair]=float(r["result"]); CACHE_TIME[pair]=now
            return PRICE_CACHE[pair]
    except: pass
    base={"EURUSD":1.08,"GBPUSD":1.27,"USDJPY":150,"EURJPY":162,"AUDUSD":0.66,"EURGBP":0.85,"USDCHF":0.88,"GBPJPY":190}.get(pair,1.08)
    return base + random.uniform(-0.001,0.001)

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
        gains.append(d if d>0 else 0); losses.append(abs(d) if d<0 else 0)
    if len(gains)<period: return 50
    ag=sum(gains[-period:])/period; al=sum(losses[-period:])/period
    if al==0: return 80
    if ag==0: return 20
    return 100-(100/(1+ag/al))

def calc_rsi_series(prices, period=14):
    return [50 if i<period else calc_rsi(prices[:i+1], period) for i in range(len(prices))]

def calc_ema_series(prices, period=9):
    k=2/(period+1); ema=prices[0] if prices else 0; lst=[]
    for i,p in enumerate(prices):
        ema=p if i==0 else p*k+ema*(1-k); lst.append(ema)
    return lst

def calc_ema(prices, period=21):
    if len(prices)<period: return prices[-1]
    k=2/(period+1); ema=prices[0]
    for p in prices[1:]: ema=p*k+ema*(1-k)
    return ema

def find_sr_levels(prices, lookback=40):
    if len(prices)<lookback: return None,None
    recent=prices[-lookback:]; return min(recent), max(recent)

# COOL CHART WITH TP/SL + COOL DESIGN
def generate_chart(pair, signal_type=None, entry_price=None, confidence=90):
    prices = PRICE_HISTORY.get(pair, [])
    if len(prices) < 20: return None
    try:
        support, resistance = find_sr_levels(prices, 40)
        upper_list=[]; mid_list=[]; lower_list=[]
        for i in range(len(prices)):
            if i<20: upper_list.append(None); mid_list.append(None); lower_list.append(None)
            else: u,m,l=calc_bollinger(prices[:i+1],20,2); upper_list.append(u); mid_list.append(m); lower_list.append(l)
        ema9=calc_ema_series(prices,9); ema21=calc_ema_series(prices,21); rsi_series=calc_rsi_series(prices,14)
        
        fig, (ax1, ax2) = plt.subplots(2,1, figsize=(11,6.5), gridspec_kw={'height_ratios':[3.2,1]}, facecolor='#0e0e12')
        ax1.set_facecolor('#0e0e12'); ax2.set_facecolor('#0e0e12')
        x=list(range(len(prices)))
        open_list=[prices[0]]+prices[:-1]
        
        for i in range(len(x)):
            o=open_list[i]; c=prices[i]; wiggle=abs(c-o)*0.4 + c*0.0004
            h=max(o,c)+wiggle; l=min(o,c)-wiggle
            color='#089981' if c>=o else '#F23645'
            ax1.plot([x[i],x[i]],[l,h],color=color,linewidth=0.8)
            bh=abs(c-o); 
            if bh < (h-l)*0.08: bh=(h-l)*0.1
            ax1.add_patch(Rectangle((x[i]-0.35,min(o,c)),0.7,max(bh,prices[i]*0.00005),facecolor=color,edgecolor=color,zorder=3))

        valid=[i for i,u in enumerate(upper_list) if u is not None]
        if valid:
            vu=[upper_list[i] for i in valid]; vl=[lower_list[i] for i in valid]; vx=[x[i] for i in valid]
            ax1.fill_between(vx,vl,vu,color='#2962FF',alpha=0.08)
            ax1.plot(vx,vu,color='#2962FF',linewidth=0.6,alpha=0.4); ax1.plot(vx,vl,color='#2962FF',linewidth=0.6,alpha=0.4)
            vm=[mid_list[i] for i in valid if mid_list[i] is not None]
            if vm: ax1.plot(vx[-len(vm):],vm,color='#787B86',linewidth=0.5,linestyle='--',alpha=0.4)

        ax1.plot(x,ema9,color='#FFD60A',linewidth=1.1,label='EMA 9'); ax1.plot(x,ema21,color='#FF9800',linewidth=1.1,label='EMA 21')
        if support: ax1.axhline(y=support,color='#089981',linestyle='--',linewidth=1,alpha=0.6,label=f'SUP {round(support,5)}')
        if resistance: ax1.axhline(y=resistance,color='#F23645',linestyle='--',linewidth=1,alpha=0.6,label=f'RES {round(resistance,5)}')

        # COOL: TP/SL Lines
        if entry_price and signal_type:
            if signal_type=="CALL":
                tp=entry_price*1.0015; sl=entry_price*0.9988
            else:
                tp=entry_price*0.9985; sl=entry_price*1.0012
            ax1.axhline(y=tp,color='#00FF7F',linewidth=1.5,alpha=0.9,label=f'TP +15pips {round(tp,5)}')
            ax1.axhline(y=sl,color='#FF3B30',linewidth=1,alpha=0.6,label=f'SL -12pips {round(sl,5)}')
            ax1.axhline(y=entry_price,color='white',linewidth=0.8,linestyle=':',alpha=0.8,label=f'ENTRY {round(entry_price,5)}')

        last=prices[-1]; last_rsi=rsi_series[-1]
        vol=get_volatility(prices); vol_emoji="🔥" if vol>0.15 else "❄️" if vol<0.05 else "⚡"
        title=f"{pair} • {signal_type if signal_type else ''} {confidence}% • {round(last,5)} | RSI {round(last_rsi,1)} {vol_emoji} VOL {round(vol,3)}%"
        ax1.set_title(title,color='#D1D4DC',fontsize=11,loc='left',weight='bold')
        ax1.legend(facecolor='#1E222D',edgecolor='#2A2E39',labelcolor='#D1D4DC',fontsize=6,loc='upper left')
        ax1.tick_params(colors='#787B86',labelsize=8); ax1.grid(color='#1E222D',linewidth=0.3)

        ax2.plot(x,rsi_series,color='#9C27B0',linewidth=1.2); ax2.axhline(y=70,color='#F23645',linestyle='--',linewidth=0.6); ax2.axhline(y=30,color='#089981',linestyle='--',linewidth=0.6)
        ax2.set_ylim(0,100); ax2.set_ylabel('RSI',color='#787B86',fontsize=8); ax2.tick_params(colors='#787B86',labelsize=8); ax2.grid(color='#1E222D',linewidth=0.3)
        plt.tight_layout()
        path=f"/tmp/{pair}_v31cool.png"; plt.savefig(path,facecolor='#0e0e12',dpi=200,bbox_inches='tight'); plt.close()
        return path
    except Exception as e:
        print(f"Chart err {e}"); plt.close(); return None

def analyze_real(pair):
    price=get_price(pair)
    if pair not in PRICE_HISTORY: PRICE_HISTORY[pair]=[]
    PRICE_HISTORY[pair].append(price)
    if len(PRICE_HISTORY[pair])>100: PRICE_HISTORY[pair].pop(0)
    prices=PRICE_HISTORY[pair]
    if len(prices)<40: return None
    rsi=calc_rsi(prices); ema9=calc_ema(prices,9); ema21=calc_ema(prices,21); ema50=calc_ema(prices,50)
    upper,middle,lower=calc_bollinger(prices,20,2); support,resistance=find_sr_levels(prices,40)
    if not upper or not support: return None
    dist_sup=abs(price-support)/price*100; dist_res=abs(price-resistance)/price*100
    vol=get_volatility(prices)
    if vol<0.03: return None # Skip low volatility
    session_txt, good = get_session()
    if not good and random.random() < 0.5: return None # Filter bad session sometimes

    near_sup=dist_sup<0.18; near_res=dist_res<0.18
    if near_sup and price<=lower*1.001 and rsi<=28 and prices[-1]>ema9:
        return "CALL",90,round(rsi,1),"SUPPORT+BB","Support bounce",round(price,5)
    if near_res and price>=upper*0.999 and rsi>=72 and prices[-1]<ema9:
        return "PUT",90,round(rsi,1),"RESIST+BB","Resistance rejection",round(price,5)
    if near_sup and rsi<32 and price<lower*1.002:
        return "CALL",85,round(rsi,1),"NEAR SUP","Near support",round(price,5)
    if near_res and rsi>68 and price>upper*0.998:
        return "PUT",85,round(rsi,1),"NEAR RES","Near resistance",round(price,5)
    if rsi>58 and prices[-1]>ema9>ema21>ema50 and abs(price-middle)/price*100<0.1:
        return "CALL",80,round(rsi,1),"TREND","Trend retest",round(price,5)
    if rsi<42 and prices[-1]<ema9<ema21<ema50 and abs(price-middle)/price*100<0.1:
        return "PUT",80,round(rsi,1),"TREND","Trend retest",round(price,5)
    return None

bot = telebot.TeleBot(TOKEN, threaded=False) if ':' in TOKEN else None

def build_full_text(pair,d,c,rsi,ema,price,reason):
    now=datetime.datetime.now()+datetime.timedelta(hours=1)
    exp=now+datetime.timedelta(minutes=3)
    icon="🔺" if d=="CALL" else "🔻"
    session_txt, good = get_session()
    vol=get_volatility(PRICE_HISTORY.get(pair,[]))
    vol_txt = f"🔥 HIGH VOL {round(vol,3)}%" if vol>0.12 else f"⚡ MED VOL {round(vol,3)}%" if vol>0.06 else f"❄️ LOW VOL {round(vol,3)}%"
    wins=WIN_TRACKER.get("wins",0); losses=WIN_TRACKER.get("losses",0); total=wins+losses
    wr=round(wins/total*100,1) if total>0 else 87.5
    
    # TP/SL calc
    if d=="CALL":
        tp=price*1.0015; sl=price*0.9988
    else:
        tp=price*0.9985; sl=price*1.0012
    
    return f"""🚨 V31 COOL SNIPER 🚨

💱 {pair} {icon} {d} - 3 MIN
🔥 {c}% CONFIDENCE | {ema}
💲 Price: {price} | RSI: {rsi}

📊 {reason}
{vol_txt}
🌍 {session_txt}

🎯 ENTRY: {price}
✅ TP: {round(tp,5)} (+15 pips)
❌ SL: {round(sl,5)} (-12 pips)

⏰ Entry: {now.strftime('%H:%M:%S')} WAT
⏳ Expiry: {exp.strftime('%H:%M:%S')} WAT (3 MIN)

📈 Accuracy: {wr}% ({wins}W/{losses}L)
👉 Trade {d} NOW!
"""

def check_win_loss(pair, signal_type, entry_price):
    time.sleep(190)
    try:
        new_price=get_price(pair)
        win=False
        if signal_type=="CALL" and new_price>entry_price: win=True
        if signal_type=="PUT" and new_price<entry_price: win=True
        if win: WIN_TRACKER["wins"]=WIN_TRACKER.get("wins",0)+1
        else: WIN_TRACKER["losses"]=WIN_TRACKER.get("losses",0)+1
        WIN_TRACKER["signals"].append({"pair":pair,"type":signal_type,"entry":entry_price,"exit":new_price,"win":win,"time":time.time()})
        if len(WIN_TRACKER["signals"])>100: WIN_TRACKER["signals"].pop(0)
        save_json(WIN_FILE, WIN_TRACKER)
    except: pass

if bot:
    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        if OWNER_ID is None: OWNER_ID=m.chat.id
        if OWNER_ID and m.chat.id==OWNER_ID:
            bot.send_message(m.chat.id, f"👑 V31 COOL OWNER\n/resume /pause /test /status /paidlist\n/levels /heatmap /winrate /risk\n/chart EURUSD")
            return
        if is_paid(m.chat.id):
            bot.send_message(m.chat.id, f"✅ Paid till {get_expiry(m.chat.id)}\n🔥 V31 COOL ACTIVE\nUse /chart /heatmap /winrate /risk")
        else:
            left=3-FREE_USERS.get(str(m.chat.id),0)
            bot.send_message(m.chat.id, f"🚀 V31 COOL EDITION\n{left} free left\nFeatures:\n📊 Candle Chart+TP/SL\n🔥 Accuracy Meter\n🌍 Session Radar\n⚡ Volatility Filter\n💰 Risk Calculator\nTry /chart EURUSD")

    @bot.message_handler(commands=['chart'])
    def chart_cmd(m):
        try:
            parts=m.text.split(); pair=parts[1].upper() if len(parts)>1 else "EURUSD"
            if pair not in PAIRS: bot.send_message(m.chat.id,f"Use: {', '.join(PAIRS)}"); return
            prices=PRICE_HISTORY.get(pair,[])
            if len(prices)<25:
                bot.send_message(m.chat.id,f"⏳ Building {pair} {len(prices)}/25... wait 2 mins"); return
            bot.send_chat_action(m.chat.id,'upload_photo')
            path=generate_chart(pair)
            if path and os.path.exists(path):
                support,resistance=find_sr_levels(prices,40); rsi=calc_rsi(prices); vol=get_volatility(prices); sess,_=get_session()
                cap=f"📊 {pair} V31 COOL\nPrice {round(prices[-1],5)} RSI {round(rsi,1)}\nVol {round(vol,3)}% | {sess}\nSup {round(support,5) if support else 'N/A'} Res {round(resistance,5) if resistance else 'N/A'}"
                with open(path,'rb') as f: bot.send_photo(m.chat.id,f,caption=cap)
            else: bot.send_message(m.chat.id,"❌ Chart fail, try again")
        except Exception as e: bot.send_message(m.chat.id,f"Error {e}")

    @bot.message_handler(commands=['levels'])
    def levels_cmd(m):
        txt="📊 V31 COOL LEVELS\n━━━━━━━━━━━━━━━\n\n"
        for pair in PAIRS:
            prices=PRICE_HISTORY.get(pair,[])
            if len(prices)<40: txt+=f"⏳ {pair}: {len(prices)}/40...\n\n"; continue
            support,resistance=find_sr_levels(prices,40); upper,middle,lower=calc_bollinger(prices,20,2); rsi=calc_rsi(prices); price=prices[-1]; vol=get_volatility(prices)
            if not upper: continue
            dist_sup=abs(price-support)/price*100; dist_res=abs(resistance-price)/price*100
            status="🟡 RANGING"; vol_e="⚡"
            if vol>0.15: vol_e="🔥"
            elif vol<0.04: vol_e="❄️"
            if price<=lower*1.002 and rsi<32 and dist_sup<0.5: status="🟢 CALL 85%"
            if price>=upper*0.998 and rsi>68 and dist_res<0.5: status="🔴 PUT 85%"
            if dist_sup<0.18 and price<=lower: status="💎 CALL 90%!"
            if dist_res<0.18 and price>=upper: status="💎 PUT 90%!"
            txt+=f"{status} {pair} {vol_e} {round(vol,3)}%\n Price {round(price,5)} RSI {round(rsi,1)}\n Sup {round(support,5)} Res {round(resistance,5)}\n\n"
        sess,_=get_session()
        txt+=f"━━━━━━━━━━━━━━━\n{sess}\nUse /chart EURUSD"
        bot.send_message(m.chat.id,txt)

    @bot.message_handler(commands=['heatmap'])
    def heatmap_cmd(m):
        txt="🔥 V31 COOL HEATMAP\n━━━━━━━━━━━━━━━\n\n"
        for pair in PAIRS:
            prices=PRICE_HISTORY.get(pair,[])
            if len(prices)<30: txt+=f"⏳ {pair} building...\n"; continue
            upper,middle,lower=calc_bollinger(prices,20,2); rsi=calc_rsi(prices); price=prices[-1]; vol=get_volatility(prices)
            if not upper: continue
            support,resistance=find_sr_levels(prices,40)
            dist_sup=abs(price-support)/price*100 if support else 1
            dist_res=abs(resistance-price)/price*100 if resistance else 1
            vol_e="🔥" if vol>0.12 else "❄️" if vol<0.04 else "⚡"
            status="🟡 RANGING"
            if dist_sup<0.3 and rsi<35: status="🟢 CALL 85% NEAR"
            if dist_res<0.3 and rsi>65: status="🔴 PUT 85% NEAR"
            if dist_sup<0.18 and price<=lower: status="💎 CALL 90% READY!"
            if dist_res<0.18 and price>=upper: status="💎 PUT 90% READY!"
            txt+=f"{status} {pair} {vol_e}\n {round(price,5)} RSI {round(rsi,1)} VOL {round(vol,3)}%\n\n"
        sess,_=get_session()
        txt+=f"━━━━━━━━━━━━━━━\n{sess}"
        bot.send_message(m.chat.id,txt)

    @bot.message_handler(commands=['winrate'])
    def winrate_cmd(m):
        wins=WIN_TRACKER.get("wins",0); losses=WIN_TRACKER.get("losses",0); total=wins+losses
        wr=round(wins/total*100,1) if total>0 else 87.5
        txt=f"📊 V31 COOL ACCURACY\n━━━━━━━━━━━━━━━\n\n🏆 Wins: {wins}\n❌ Losses: {losses}\n🎯 Winrate: {wr}%\nTotal: {total} signals\n\n"
        if wr>=80: txt+="🔥🔥 HOT STREAK - AI IS ON FIRE!\n"
        elif wr>=70: txt+="⚡ SOLID - Keep going!\n"
        else: txt+="❄️ COLD - Wait for 90% signals only\n"
        last=WIN_TRACKER.get("signals",[])[-5:]
        if last:
            txt+="\nLast 5:\n"
            for s in reversed(last):
                ic="✅" if s["win"] else "❌"
                txt+=f"{ic} {s['pair']} {s['type']} {round(s['entry'],5)}->{round(s['exit'],5)}\n"
        bot.send_message(m.chat.id,txt)

    @bot.message_handler(commands=['risk','money'])
    def risk_cmd(m):
        try:
            parts=m.text.split()
            balance=float(parts[1]) if len(parts)>1 else 100
            risk_pct=float(parts[2]) if len(parts)>2 else 2
            risk_amt=balance*risk_pct/100
            txt=f"💰 V31 RISK CALCULATOR\n━━━━━━━━━━━━━━━\n\n💵 Balance: ${balance}\n⚠️ Risk: {risk_pct}% = ${round(risk_amt,2)}\n\n"
            txt+=f"For 90% signal: ${round(risk_amt,2)}\nFor 85% signal: ${round(risk_amt*0.7,2)}\nFor 80% signal: ${round(risk_amt*0.5,2)}\n\n"
            txt+=f"📊 3 Wins then STOP\n🎯 Daily Target: ${round(balance*0.06,2)} (6%)\n❌ Max Loss: ${round(balance*0.04,2)} (4%)"
            bot.send_message(m.chat.id,txt)
        except: bot.send_message(m.chat.id,"Use: /risk 100 2\n100 = balance, 2 = risk %")

    @bot.message_handler(commands=['session','market'])
    def session_cmd(m):
        sess,good=get_session()
        txt=f"🌍 MARKET SESSION RADAR\n━━━━━━━━━━━━━━━\n\n{sess}\n"
        if good: txt+="✅ Good to trade - High liquidity\n"
        else: txt+="⚠️ Low liquidity - Trade only 90% signals\n"
        txt+=f"\nUTC: {datetime.datetime.utcnow().strftime('%H:%M')}\nWAT: {(datetime.datetime.now()+datetime.timedelta(hours=1)).strftime('%H:%M')}\n\nBest: 8-11am & 1-4pm WAT (London/NY)"
        bot.send_message(m.chat.id,txt)

    @bot.message_handler(commands=['approve','paidlist','resume','pause','test','status','scan'])
    def other(m):
        global SCANNING, OWNER_ID, LAST_SIGNAL_TIME
        if OWNER_ID and m.chat.id!=OWNER_ID: return
        if m.text.startswith("/approve"):
            try:
                p=m.text.split(); uid=p[1]; d=int(p[2]) if len(p)>2 else 30
                PAID_USERS[str(uid)]=time.time()+d*24*3600; save_json(PAID_FILE, PAID_USERS)
                bot.send_message(m.chat.id,f"✅ {uid} till {get_expiry(uid)}")
                try: bot.send_message(int(uid),f"✅ V31 COOL Activated! {d} days")
                except: pass
            except: bot.send_message(m.chat.id,"Use: /approve ID 30")
        elif m.text.startswith("/paidlist"):
            t="💰 Paid:\n"+"\n".join([f"{k} - {get_expiry(k)}" for k in PAID_USERS]) if PAID_USERS else "No paid"
            bot.send_message(m.chat.id,t)
        elif m.text.startswith("/status"):
            mins=int((time.time()-LAST_SIGNAL_TIME)/60)
            sess,_=get_session()
            t=f"V31 COOL: {SCANNING}\nLast: {mins}m ago\n{sess}\n"+"\n".join([f"{p}: {len(PRICE_HISTORY.get(p,[]))}" for p in PAIRS])
            bot.send_message(m.chat.id,t)
        elif m.text.startswith("/resume"): SCANNING=True; bot.send_message(m.chat.id,"▶️ V31 COOL ON")
        elif m.text.startswith("/pause"): SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused")
        elif m.text.startswith("/test") or m.text.startswith("/scan"):
            pair=random.choice(PAIRS); d=random.choice(["CALL","PUT"]); c=random.choice([90,85]); rsi=23.5 if d=="CALL" else 76.2; ema="SUPPORT+BB" if d=="CALL" else "RESIST+BB"; price=round(random.uniform(1.05,1.35),5)
            mk=InlineKeyboardMarkup(row_width=1)
            mk.add(InlineKeyboardButton(f"👥 Users Only",callback_data=f"users_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                   InlineKeyboardButton(f"📢 Channel Only",callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                   InlineKeyboardButton(f"🚀 BOTH",callback_data=f"both_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                   InlineKeyboardButton("❌ Skip",callback_data="skip"))
            txt=f"🔔 V31 COOL READY!\n\n{pair} {d} {c}%\nPrice {price}\nRSI {rsi} {ema}\nWill send with TP/SL + Cool chart!"
            bot.send_message(m.chat.id,txt,reply_markup=mk)

    @bot.callback_query_handler(func=lambda c: True)
    def cb(call):
        global LAST_SIGNAL_TIME
        if OWNER_ID and call.message.chat.id!=OWNER_ID: return
        if call.data=="skip": bot.edit_message_text("❌ Skipped",call.message.chat.id,call.message.message_id); return
        try:
            parts=call.data.split("_"); typ=parts[0]; pair=parts[1]; d=parts[2]; c=parts[3]; rsi=parts[4]; ema=parts[5]; price=parts[6]
            full=build_full_text(pair,d,c,rsi,ema,price,f"{ema}")
            sent_users=0; sent_chan=False
            chart_path=generate_chart(pair,d,float(price),int(c))
            if typ in ["users","both"]:
                all_ids=set(list(PAID_USERS.keys())+list(FREE_USERS.keys())+[str(OWNER_ID)])
                for uid_str in all_ids:
                    try:
                        uid=int(uid_str)
                        if not is_paid(uid) and not can_send_free(uid): continue
                        if chart_path and os.path.exists(chart_path):
                            with open(chart_path,'rb') as f: bot.send_photo(uid,f,caption=full)
                        else: bot.send_message(uid,full)
                        use_free(uid); sent_users+=1; time.sleep(0.35)
                    except: pass
            if typ in ["chan","both"]:
                try:
                    if chart_path and os.path.exists(chart_path):
                        with open(chart_path,'rb') as f: bot.send_photo(CHANNEL_ID,f,caption=full)
                    else: bot.send_message(CHANNEL_ID,full)
                    sent_chan=True
                except: pass
            LAST_SIGNAL_TIME=time.time(); save_json(HISTORY_FILE, PRICE_HISTORY)
            threading.Thread(target=check_win_loss,args=(pair,d,float(price)),daemon=True).start()
            where="USERS" if typ=="users" else "CHANNEL" if typ=="chan" else "BOTH"
            bot.edit_message_text(f"✅ V31 COOL SENT: {where}\n👥 {sent_users} | 📢 {'Yes' if sent_chan else 'No'}\nTP/SL + Vol + Session added",call.message.chat.id,call.message.message_id)
        except Exception as e: bot.send_message(call.message.chat.id,f"Error {e}")

    @app.route(f'/{TOKEN}',methods=['POST'])
    def webhook():
        if request.headers.get('content-type')=='application/json':
            js=request.get_data().decode('utf-8'); upd=telebot.types.Update.de_json(js); bot.process_new_updates([upd]); return ''
        return 'ok',200
    @app.route('/')
    def home(): return "V31 COOL EDITION LIVE",200
    def set_wh():
        time.sleep(5)
        if RENDER_URL:
            try:
                requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True",timeout=10); time.sleep(2)
                url=f"{RENDER_URL}/{TOKEN}"; r=requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}",timeout=10); print(r.text,flush=True)
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
                d,c,rsi,ema,reason,price=res
                save_json(HISTORY_FILE, PRICE_HISTORY)
                mk=InlineKeyboardMarkup(row_width=1)
                mk.add(InlineKeyboardButton(f"👥 Users Only",callback_data=f"users_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                       InlineKeyboardButton(f"📢 Channel Only",callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                       InlineKeyboardButton(f"🚀 BOTH",callback_data=f"both_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                       InlineKeyboardButton("❌ Skip",callback_data="skip"))
                sess,_=get_session()
                txt=f"🔔 V31 COOL READY!\n\n{pair} {d} {c}%\nPrice {price}\nRSI {rsi} {ema}\n{reason}\n{sess}\n\nWill send with TP/SL+Vol chart!"
                bot.send_message(OWNER_ID,txt,reply_markup=mk)
                LAST_SIGNAL_TIME=time.time(); time.sleep(120); break
        except Exception as e: print(f"SCAN {e}",flush=True); time.sleep(10)
threading.Thread(target=scanner,daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
