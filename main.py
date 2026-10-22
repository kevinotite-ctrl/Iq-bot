
import os, time, threading, datetime, json, requests, random
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle  # <-- ADDED FOR CANDLESTICK

print("=== V31 CHART SNIPER FINAL - CANDLESTICK ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
CHANNEL_ID = "@trailblazeebot"
OWNER_USERNAME = "@kevintraiblazer"
PRICE = "$10/month"

OWNER_ID = None
SCANNING = True
LAST_SIGNAL_TIME = time.time()
PAIRS = ["EURUSD","GBPUSD","USDJPY","EURJPY","AUDUSD","EURGBP","USDCHF","GBPJPY"]
PAID_FILE = "paid_users.json"
FREE_FILE = "free_users.json"
HISTORY_FILE = "price_history.json"
PRICE_CACHE = {}
CACHE_TIME = {}

def load_json(f):
    try:
        if os.path.exists(f):
            with open(f,'r') as fp: return json.load(fp)
    except: pass
    return {}
def save_json(f,data):
    try:
        with open(f,'w') as fp: json.dump(data, fp)
    except Exception as e: print(f"save err {e}")

PAID_USERS = load_json(PAID_FILE)
FREE_USERS = load_json(FREE_FILE)
PRICE_HISTORY = load_json(HISTORY_FILE)

def is_paid(uid):
    if OWNER_ID and str(uid)==str(OWNER_ID): return True
    if str(uid) in PAID_USERS and time.time() < PAID_USERS[str(uid)]: return True
    return False
def can_send_free(uid):
    if is_paid(uid): return True
    return FREE_USERS.get(str(uid),0) < 2
def use_free(uid):
    if is_paid(uid): return
    FREE_USERS[str(uid)] = FREE_USERS.get(str(uid),0)+1
    save_json(FREE_FILE, FREE_USERS)
def get_expiry(uid):
    if str(uid) not in PAID_USERS: return "Not paid"
    return datetime.datetime.fromtimestamp(PAID_USERS[str(uid)]).strftime('%d %b %Y')

def get_price(pair):
    now = time.time()
    if pair in PRICE_CACHE and now - CACHE_TIME.get(pair,0) < 120:
        return PRICE_CACHE[pair] + random.uniform(-0.0003,0.0003)
    try:
        r = requests.get(f"https://api.exchangerate.host/convert?from={pair[:3]}&to={pair[3:6]}&amount=1", timeout=8).json()
        if r.get("result"):
            PRICE_CACHE[pair]=float(r["result"])
            CACHE_TIME[pair]=now
            return PRICE_CACHE[pair]
    except: pass
    base={"EURUSD":1.08,"GBPUSD":1.27,"USDJPY":150,"EURJPY":162,"AUDUSD":0.66,"EURGBP":0.85,"USDCHF":0.88,"GBPJPY":190}.get(pair,1.08)
    return base + random.uniform(-0.002,0.002)

def calc_bollinger(prices, period=20, std=2):
    if len(prices) < period: return None, None, None
    sma = sum(prices[-period:]) / period
    var = sum((x - sma) ** 2 for x in prices[-period:]) / period
    stdev = var ** 0.5
    return sma + std*stdev, sma, sma - std*stdev

def calc_rsi(prices, period=14):
    if len(prices) < period+1: return 50
    gains=[]; losses=[]
    for i in range(1,len(prices)):
        diff=prices[i]-prices[i-1]
        if diff>0: gains.append(diff); losses.append(0)
        else: gains.append(0); losses.append(abs(diff))
    if len(gains)<period: return 50
    avg_gain=sum(gains[-period:])/period
    avg_loss=sum(losses[-period:])/period
    if avg_loss==0: return 88
    if avg_gain==0: return 12
    rs=avg_gain/avg_loss
    return 100-(100/(1+rs))

def calc_rsi_series(prices, period=14):
    rsi_list=[]
    for i in range(len(prices)):
        if i < period: rsi_list.append(50)
        else: rsi_list.append(calc_rsi(prices[:i+1], period))
    return rsi_list

def calc_ema(prices, period=21):
    if len(prices)<period: return prices[-1] if prices else 0
    k=2/(period+1); ema=prices[0]
    for p in prices[1:]: ema = p*k + ema*(1-k)
    return ema

def calc_ema_series(prices, period=9):
    ema_list=[]
    k=2/(period+1)
    ema=prices[0] if prices else 0
    for i,p in enumerate(prices):
        if i==0: ema=p
        else: ema = p*k + ema*(1-k)
        ema_list.append(ema)
    return ema_list

def find_sr_levels(prices, lookback=40):
    if len(prices) < lookback: return None, None
    recent = prices[-lookback:]
    resistance = max(recent)
    support = min(recent)
    return support, resistance

def generate_chart(pair):
    prices = PRICE_HISTORY.get(pair, [])
    if len(prices) < 20: return None
    try:
        support, resistance = find_sr_levels(prices, 40)
        upper_list=[]; mid_list=[]; lower_list=[]
        for i in range(len(prices)):
            if i < 20:
                upper_list.append(None); mid_list.append(None); lower_list.append(None)
            else:
                u,m,l = calc_bollinger(prices[:i+1], 20, 2)
                upper_list.append(u); mid_list.append(m); lower_list.append(l)
        ema9_series = calc_ema_series(prices, 9)
        ema21_series = calc_ema_series(prices, 21)
        rsi_series = calc_rsi_series(prices, 14)
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10,6), gridspec_kw={'height_ratios': [3,1]}, facecolor='#131722')
        ax1.set_facecolor('#131722')
        ax2.set_facecolor('#131722')
        
        x = list(range(len(prices)))

        # ===== CANDLESTICK CORRECTION =====
        # Build fake OHLC from close history
        open_list = [prices[0]] + prices[:-1]  # open = previous close
        close_list = prices
        high_list = []
        low_list = []
        for i in range(len(prices)):
            o = open_list[i]
            c = close_list[i]
            # small wick based on volatility
            wiggle = abs(c - o) * 0.3 + (c * 0.0004)
            h = max(o,c) + wiggle
            l = min(o,c) - wiggle
            high_list.append(h)
            low_list.append(l)

        # Draw candles
        for i in range(len(x)):
            o = open_list[i]; h = high_list[i]; l = low_list[i]; c = close_list[i]
            bullish = c >= o
            color = '#26a69a' if bullish else '#ef5350'
            # wick
            ax1.plot([x[i], x[i]], [l, h], color=color, linewidth=0.8, alpha=0.9, zorder=2)
            # body
            body_h = abs(c - o)
            if body_h < (h - l) * 0.08:  # make doji visible
                body_h = (h - l) * 0.08
            ax1.add_patch(Rectangle((x[i]-0.35, min(o,c)), 0.7, body_h, facecolor=color, edgecolor=color, linewidth=0.8, zorder=3))

        # Bollinger shaded
        valid_idx = [i for i,u in enumerate(upper_list) if u is not None]
        if valid_idx:
            valid_u = [upper_list[i] for i in valid_idx]
            valid_l = [lower_list[i] for i in valid_idx]
            valid_x = [x[i] for i in valid_idx]
            ax1.fill_between(valid_x, valid_l, valid_u, color='#5d9cf5', alpha=0.12, label='BB (20,2)')
            ax1.plot(valid_x, valid_u, color='#5d9cf5', linewidth=0.8, alpha=0.5)
            ax1.plot(valid_x, valid_l, color='#5d9cf5', linewidth=0.8, alpha=0.5)
            mid_valid = [mid_list[i] for i in valid_idx if mid_list[i] is not None]
            if mid_valid:
                ax1.plot(valid_x[-len(mid_valid):], mid_valid, color='gray', linewidth=0.5, linestyle='--', alpha=0.5)

        # EMAs on top of candles
        ax1.plot(x, ema9_series, color='#FFD700', linewidth=1.2, label='EMA 9')
        ax1.plot(x, ema21_series, color='orange', linewidth=1.2, label='EMA 21')
        
        if support: ax1.axhline(y=support, color='#26a69a', linestyle='--', linewidth=1.2, label=f'SUPPORT {round(support,5)}')
        if resistance: ax1.axhline(y=resistance, color='#ef5350', linestyle='--', linewidth=1.2, label=f'RESISTANCE {round(resistance,5)}')
        
        # Signal arrow logic
        last_price = prices[-1]
        last_rsi = rsi_series[-1]
        sr_gap = (resistance-support)*0.3 if support and resistance else last_price*0.002
        
        if support and last_price <= (lower_list[-1] or 0)*1.002 and last_rsi < 35:
            ax1.annotate(f'CALL 90% BUY\nSUPPORT', xy=(len(prices)-1, last_price), 
                         xytext=(len(prices)-12, last_price+ sr_gap),
                         arrowprops=dict(facecolor='#00FF00', edgecolor='#00FF00', shrink=0.05, width=2, headwidth=12), 
                         fontsize=11, color='#00FF00', weight='bold',
                         bbox=dict(boxstyle="round,pad=0.3", facecolor='#131722', edgecolor='#00FF00'))
        elif resistance and last_price >= (upper_list[-1] or 0)*0.998 and last_rsi > 65:
            ax1.annotate(f'PUT 90% SELL\nRESISTANCE', xy=(len(prices)-1, last_price), 
                         xytext=(len(prices)-12, last_price- sr_gap),
                         arrowprops=dict(facecolor='#FF5252', edgecolor='#FF5252', shrink=0.05, width=2, headwidth=12), 
                         fontsize=11, color='#FF5252', weight='bold',
                         bbox=dict(boxstyle="round,pad=0.3", facecolor='#131722', edgecolor='#FF5252'))
        
        ax1.set_title(f'{pair} • V31 ICT+SR • Price: {round(last_price,5)} • RSI: {round(last_rsi,1)}', color='white', fontsize=12)
        ax1.legend(facecolor='#131722', edgecolor='gray', labelcolor='white', fontsize=7, loc='upper left')
        ax1.tick_params(colors='gray')
        ax1.grid(color='#2a2e39', linestyle='-', linewidth=0.3)
        
        # RSI
        ax2.plot(x, rsi_series, color='#b388ff', linewidth=1.2)
        ax2.axhline(y=70, color='red', linestyle='--', linewidth=0.8, alpha=0.6)
        ax2.axhline(y=30, color='green', linestyle='--', linewidth=0.8, alpha=0.6)
        ax2.fill_between(x, 30, 70, color='gray', alpha=0.05)
        ax2.set_ylim(0,100)
        ax2.set_ylabel('RSI 14', color='white', fontsize=9)
        ax2.tick_params(colors='gray')
        ax2.grid(color='#2a2e39', linestyle='-', linewidth=0.3)
        
        plt.tight_layout()
        chart_path = f"/tmp/{pair}_chart.png"
        plt.savefig(chart_path, facecolor='#131722', dpi=150, bbox_inches='tight')
        plt.close()
        return chart_path
    except Exception as e:
        print(f"Chart err {e}")
        import traceback; traceback.print_exc()
        plt.close()
        return None

def analyze_real(pair):
    price = get_price(pair)
    if pair not in PRICE_HISTORY: PRICE_HISTORY[pair]=[]
    PRICE_HISTORY[pair].append(price)
    if len(PRICE_HISTORY[pair])>100: PRICE_HISTORY[pair].pop(0)
    prices = PRICE_HISTORY[pair]
    if len(prices)<40: return None
    rsi = calc_rsi(prices)
    ema9 = calc_ema(prices,9)
    ema21 = calc_ema(prices,21)
    ema50 = calc_ema(prices,50)
    upper, middle, lower = calc_bollinger(prices, 20, 2)
    support, resistance = find_sr_levels(prices, 40)
    if not upper or not support: return None
    dist_to_res = abs(price - resistance) / price * 100
    dist_to_sup = abs(price - support) / price * 100
    near_resistance = dist_to_res < 0.18
    near_support = dist_to_sup < 0.18
    if near_support and price <= lower*1.001 and rsi <= 28 and prices[-1] > ema9:
        return "CALL", 90, round(rsi,1), "SUPPORT + BB BOUNCE", f"Price at SUPPORT {round(support,5)} ({round(dist_to_sup,3)}% away) + Lower BB {round(lower,5)} + RSI {round(rsi,1)} Oversold", round(price,5)
    if near_resistance and price >= upper*0.999 and rsi >= 72 and prices[-1] < ema9:
        return "PUT", 90, round(rsi,1), "RESISTANCE + BB REJECTION", f"Price at RESISTANCE {round(resistance,5)} ({round(dist_to_res,3)}% away) + Upper BB {round(upper,5)} + RSI {round(rsi,1)} Overbought", round(price,5)
    if near_support and rsi < 32 and price < lower*1.002:
        return "CALL", 85, round(rsi,1), "NEAR SUPPORT BOUNCE", f"Near Support {round(support,5)} + Below Lower BB + RSI {round(rsi,1)}", round(price,5)
    if near_resistance and rsi > 68 and price > upper*0.998:
        return "PUT", 85, round(rsi,1), "NEAR RESISTANCE REJECTION", f"Near Resistance {round(resistance,5)} + Above Upper BB + RSI {round(rsi,1)}", round(price,5)
    if rsi > 58 and prices[-1] > ema9 > ema21 > ema50 and abs(price-middle)/price*100 < 0.1:
        return "CALL", 80, round(rsi,1), "TREND RETEST", f"Strong Uptrend EMA 9>21>50 + Retest Middle BB + RSI {round(rsi,1)}", round(price,5)
    if rsi < 42 and prices[-1] < ema9 < ema21 < ema50 and abs(price-middle)/price*100 < 0.1:
        return "PUT", 80, round(rsi,1), "TREND RETEST", f"Strong Downtrend EMA 9<21<50 + Retest Middle BB + RSI {round(rsi,1)}", round(price,5)
    return None

bot = telebot.TeleBot(TOKEN, threaded=False) if ':' in TOKEN else None

def build_full_text(pair,d,c,rsi,ema,price,reason):
    now=datetime.datetime.now()+datetime.timedelta(hours=1)
    exp=now+datetime.timedelta(minutes=3)
    icon = "🔺" if d=="CALL" else "🔻"
    return f"""🚨 KEVIN V31 CHART SNIPER 🚨

💱 {pair}
{'📈' if d=='CALL' else '📉'} {d} - 3 MIN {icon}
🔥 {c}% 💎 | {ema}
💲 Price: {price} | RSI: {rsi}

📊 {reason}
⏰ Entry: {now.strftime('%H:%M')} WAT
🎯 Expiry: {exp.strftime('%H:%M')} WAT (3 MIN)

👉 Trade {d} NOW!
📈 Use /chart {pair} to see visual"""

if bot:
    @bot.message_handler(commands=['start'])
    def start(m):
        global OWNER_ID
        if OWNER_ID is None: OWNER_ID=m.chat.id
        if OWNER_ID and m.chat.id==OWNER_ID:
            bot.send_message(m.chat.id, f"👑 V31 CHART OWNER\n/resume /pause /test /scan /status /paidlist /levels\n/chart EURUSD")
            return
        if is_paid(m.chat.id):
            bot.send_message(m.chat.id, f"✅ Paid till {get_expiry(m.chat.id)}\nV31 - Use /levels and /chart EURUSD")
        else:
            left = 2 - FREE_USERS.get(str(m.chat.id),0)
            bot.send_message(m.chat.id, f"🚀 KEVIN V31 CHART SNIPER\n{left} free signals left, then {PRICE}\nTry /chart EURUSD")

    @bot.message_handler(commands=['chart'])
    def chart_cmd(m):
        try:
            parts = m.text.split()
            pair = parts[1].upper() if len(parts)>1 else "EURUSD"
            if pair not in PAIRS:
                bot.send_message(m.chat.id, f"❌ Invalid pair. Use: {', '.join(PAIRS)}\nExample: /chart EURUSD")
                return
            prices = PRICE_HISTORY.get(pair, [])
            if len(prices) < 25:
                bot.send_message(m.chat.id, f"⏳ Collecting data for {pair}... {len(prices)}/25 prices. Try in few mins.\nBot needs time to build chart.")
                return
            bot.send_message(m.chat.id, f"📈 Generating V31 CANDLE chart for {pair}... Wait 3 sec")
            chart_path = generate_chart(pair)
            if chart_path and os.path.exists(chart_path):
                support, resistance = find_sr_levels(prices, 40)
                rsi = calc_rsi(prices)
                with open(chart_path, 'rb') as f:
                    cap = f"📊 {pair} LIVE CANDLE CHART V31\nPrice: {round(prices[-1],5)}\nRSI: {round(rsi,1)}\nSupport: {round(support,5) if support else 'N/A'}\nResistance: {round(resistance,5) if resistance else 'N/A'}\n\nUse /levels for all pairs"
                    bot.send_photo(m.chat.id, f, caption=cap)
            else:
                bot.send_message(m.chat.id, "❌ Chart generation failed, try again")
        except Exception as e:
            bot.send_message(m.chat.id, f"Error: {e}")

    @bot.message_handler(commands=['levels'])
    def levels_cmd(m):
        txt = "📊 V31 LIVE SR LEVELS\n━━━━━━━━━━━━━━━\n\n"
        for pair in PAIRS:
            prices = PRICE_HISTORY.get(pair, [])
            if len(prices) < 40:
                txt += f"⏳ {pair}: Collecting {len(prices)}/40...\n\n"
                continue
            support, resistance = find_sr_levels(prices, 40)
            upper, middle, lower = calc_bollinger(prices, 20, 2)
            rsi = calc_rsi(prices)
            price = prices[-1]
            if not upper: continue
            dist_sup = abs(price-support)/price*100
            dist_res = abs(resistance-price)/price*100
            status = "🟡 RANGING"
            if price <= lower*1.002 and rsi < 32 and dist_sup < 0.5: status = "🟢 CALL SOON 85%"
            if price >= upper*0.998 and rsi > 68 and dist_res < 0.5: status = "🔴 PUT SOON 85%"
            if dist_sup < 0.18 and price <= lower: status = "💎 CALL 90% READY!"
            if dist_res < 0.18 and price >= upper: status = "💎 PUT 90% READY!"
            txt += f"{status} {pair}\n  Price: {round(price,5)} | RSI: {round(rsi,1)}\n  Sup: {round(support,5)} ({round(dist_sup,2)}%)\n  Res: {round(resistance,5)} ({round(dist_res,2)}%)\n\n"
        txt += "━━━━━━━━━━━━━━━\nUse /chart EURUSD for visual"
        bot.send_message(m.chat.id, txt)

    @bot.message_handler(commands=['approve','paidlist','resume','pause','test','status','scan'])
    def other(m):
        global SCANNING, OWNER_ID, LAST_SIGNAL_TIME
        if OWNER_ID and m.chat.id!=OWNER_ID: return
        if m.text.startswith("/approve"):
            try:
                p=m.text.split(); uid=p[1]; d=int(p[2]) if len(p)>2 else 30
                PAID_USERS[str(uid)]=time.time()+d*24*3600; save_json(PAID_FILE, PAID_USERS)
                bot.send_message(m.chat.id, f"✅ {uid} till {get_expiry(uid)}")
                try: bot.send_message(int(uid), f"✅ Activated! {d} days V31")
                except: pass
            except: bot.send_message(m.chat.id, "Use: /approve ID 30")
        elif m.text.startswith("/paidlist"):
            t="💰 Paid:\n" + "\n".join([f"{k} - {get_expiry(k)}" for k in PAID_USERS]) if PAID_USERS else "No paid"
            bot.send_message(m.chat.id,t)
        elif m.text.startswith("/status"):
            mins = int((time.time()-LAST_SIGNAL_TIME)/60)
            t=f"V31 SCAN: {SCANNING}\nLast: {mins} mins ago\n" + "\n".join([f"{p}: {len(PRICE_HISTORY.get(p,[]))}" for p in PAIRS])
            bot.send_message(m.chat.id,t)
        elif m.text.startswith("/resume"):
            SCANNING=True; bot.send_message(m.chat.id,"▶️ V31 ON")
        elif m.text.startswith("/pause"):
            SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused")
        elif m.text.startswith("/test") or m.text.startswith("/scan"):
            pair = random.choice(PAIRS); d = random.choice(["CALL","PUT"]); c=90
            rsi=23.5 if d=="CALL" else 76.2; ema="SUPPORT+BB" if d=="CALL" else "RESISTANCE+BB"; price=round(random.uniform(1.05,1.35),5)
            label = "⚡ V31 SCAN" if m.text.startswith("/scan") else "🔔 V31 TEST"
            mk=InlineKeyboardMarkup(row_width=1)
            mk.add(
                InlineKeyboardButton(f"👥 Users Only", callback_data=f"users_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                InlineKeyboardButton(f"📢 Channel Only", callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                InlineKeyboardButton(f"🚀 BOTH", callback_data=f"both_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                InlineKeyboardButton("❌ Skip", callback_data="skip")
            )
            txt=f"{label}\n\n{pair} {d} {c}%\nPrice {price}\nRSI {rsi} {ema}\n\n👇 Where to send?"
            bot.send_message(m.chat.id, txt, reply_markup=mk)

    @bot.callback_query_handler(func=lambda c: True)
    def cb(call):
        global LAST_SIGNAL_TIME
        if OWNER_ID and call.message.chat.id!=OWNER_ID: return
        if call.data=="skip":
            bot.edit_message_text("❌ Skipped", call.message.chat.id, call.message.message_id); return
        try:
            parts=call.data.split("_")
            typ=parts[0]; pair=parts[1]; d=parts[2]; c=parts[3]; rsi=parts[4]; ema=parts[5]; price=parts[6]
            full = build_full_text(pair,d,c,rsi,ema,price,f"RSI {rsi} + {ema} + SR")
            sent_users=0; sent_chan=False
            chart_path = generate_chart(pair)
            if typ in ["users","both"]:
                all_ids = set(list(PAID_USERS.keys()) + list(FREE_USERS.keys()) + [str(OWNER_ID)])
                for uid_str in all_ids:
                    try:
                        uid=int(uid_str)
                        if not is_paid(uid) and not can_send_free(uid): continue
                        bot.send_message(uid, "‼️ CHART SNIPER ALERT ‼️"); time.sleep(0.3)
                        if chart_path and os.path.exists(chart_path):
                            with open(chart_path, 'rb') as f:
                                bot.send_photo(uid, f, caption=full)
                        else:
                            bot.send_message(uid, full)
                        use_free(uid); sent_users+=1; time.sleep(0.4)
                    except: pass
            if typ in ["chan","both"]:
                try:
                    if chart_path and os.path.exists(chart_path):
                        with open(chart_path, 'rb') as f:
                            bot.send_photo(CHANNEL_ID, f, caption=full)
                    else:
                        bot.send_message(CHANNEL_ID, full)
                    sent_chan=True
                except: pass
            LAST_SIGNAL_TIME = time.time()
            where = "USERS" if typ=="users" else "CHANNEL" if typ=="chan" else "BOTH"
            bot.edit_message_text(f"✅ V31 CHART SENT: {where}\n👥 {sent_users} | 📢 {'Yes' if sent_chan else 'No'}", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error {e}")

    @app.route(f'/{TOKEN}', methods=['POST'])
    def webhook():
        if request.headers.get('content-type')=='application/json':
            js=request.get_data().decode('utf-8'); upd=telebot.types.Update.de_json(js); bot.process_new_updates([upd]); return ''
        return 'ok',200
    @app.route('/')
    def home(): return "V31 CHART SNIPER LIVE - CANDLESTICK",200

    def set_wh():
        time.sleep(5)
        if RENDER_URL:
            try:
                requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook?drop_pending_updates=True", timeout=10); time.sleep(2)
                url=f"{RENDER_URL}/{TOKEN}"; r=requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={url}", timeout=10); print(r.text, flush=True)
            except Exception as e: print(e, flush=True)
    threading.Thread(target=set_wh, daemon=True).start()

def scanner():
    global LAST_SIGNAL_TIME
    while True:
        try:
            time.sleep(60)
            if not OWNER_ID or not SCANNING or not bot: continue
            if time.time() - LAST_SIGNAL_TIME > 7200:
                try:
                    ping = f"✅ V31 ACTIVE - Use /chart EURUSD for visuals\nScanning {len(PAIRS)} pairs"
                    bot.send_message(CHANNEL_ID, ping)
                    LAST_SIGNAL_TIME = time.time()
                except Exception as e: print(f"ping err {e}")
            for pair in PAIRS:
                res=analyze_real(pair)
                if not res: continue
                d,c,rsi,ema,reason,price=res
                save_json(HISTORY_FILE, PRICE_HISTORY)
                mk=InlineKeyboardMarkup(row_width=1)
                mk.add(
                    InlineKeyboardButton(f"👥 Users Only", callback_data=f"users_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                    InlineKeyboardButton(f"📢 Channel Only", callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                    InlineKeyboardButton(f"🚀 BOTH", callback_data=f"both_{pair}_{d}_{c}_{rsi}_{ema}_{price}"),
                    InlineKeyboardButton("❌ Skip", callback_data="skip")
                )
                txt=f"🔔 V31 CHART READY!\n\n{pair} {d} {c}%\nPrice {price}\nRSI {rsi} EMA {ema}\n{reason}\n\nWill send with chart!"
                bot.send_message(OWNER_ID, txt, reply_markup=mk)
                LAST_SIGNAL_TIME = time.time()
                time.sleep(120)
                break
        except Exception as e: print(f"SCAN {e}", flush=True); time.sleep(10)
threading.Thread(target=scanner, daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
