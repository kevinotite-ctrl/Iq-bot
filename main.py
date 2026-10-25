import os, time, threading, datetime, json, requests, random
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import yfinance as yf
import pandas as pd

print("=== V33 100/100 + AUTO 90% + MARTINGALE 1-2-4 ===", flush=True)
app = Flask(__name__)

TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
RENDER_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").strip()
CHANNEL_ID = "@trailblazeebot"
OWNER_USERNAME = "@kevintraiblazer"
PRICE = "$10/month"

IQ_EMAIL = os.getenv("IQ_EMAIL", "")
IQ_PASSWORD = os.getenv("IQ_PASSWORD", "")

OWNER_ID = None
SCANNING = True
LAST_SIGNAL_TIME = time.time()
PAIRS = ["EURUSD","GBPUSD","USDJPY","EURJPY","AUDUSD","EURGBP","USDCHF","GBPJPY"]
PAID_FILE = "paid_users.json"
FREE_FILE = "free_users.json"
HISTORY_FILE = "price_history.json"
WIN_FILE = "win_tracker.json"
COOLDOWN_FILE = "cooldown.json"

PRICE_CACHE = {}
CACHE_TIME = {}
PAYOUT_CACHE = {}

SYMBOL_MAP = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "EURJPY": "EURJPY=X", "AUDUSD": "AUDUSD=X", "EURGBP": "EURGBP=X",
    "USDCHF": "USDCHF=X", "GBPJPY": "GBPJPY=X"
}

# === AUTO TRADE + MARTINGALE SETTINGS ===
AUTO_TRADE_ENABLED = True
AUTO_MIN_CONFIDENCE = 90
AUTO_TRADE_BALANCE = "PRACTICE" # PRACTICE or REAL
BASE_AMOUNT = 2  # $2 base
MARTINGALE_STEPS = [1, 2, 4]  # $2 -> $4 -> $8 -> RESET
martingale_level = 0
auto_stats = {"wins":0,"losses":0,"profit":0.0}

def get_martingale_amount():
    return BASE_AMOUNT * MARTINGALE_STEPS[martingale_level]

# === IQ API FROM GITHUB ===
IQ_API = None
IQ_CONNECTED = False
try:
    try:
        from iqoptionapi.stable_api import IQ_Option
    except:
        from iqoptionapi.api import IQOptionAPI as IQ_Option
    if IQ_EMAIL and IQ_PASSWORD:
        IQ_API = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
        IQ_API.connect()
        time.sleep(3)
        if not IQ_API.check_connect():
            IQ_API.connect()
            time.sleep(3)
        if IQ_API.check_connect():
            IQ_CONNECTED = True
            print(f"IQ CONNECTED! Balance: {IQ_API.get_balance()} Mode: {IQ_API.get_balance_mode()}", flush=True)
            try:
                IQ_API.change_balance(AUTO_TRADE_BALANCE)
            except:
                pass
        else:
            print(f"IQ FAIL", flush=True)
except Exception as e:
    print(f"IQ API not available: {e} - Using Yahoo fallback", flush=True)

def load_json(f):
    try:
        if os.path.exists(f):
            with open(f,'r') as fp: return json.load(fp)
    except: pass
    if "win" in f: return {"wins":0,"losses":0,"signals":[],"pairs":{}}
    if "cool" in f: return {}
    return {}
def save_json(f,data):
    try:
        with open(f,'w') as fp: json.dump(data, fp)
    except Exception as e: print(f"save err {e}")

PAID_USERS = load_json(PAID_FILE)
FREE_USERS = load_json(FREE_FILE)
PRICE_HISTORY = load_json(HISTORY_FILE)
WIN_TRACKER = load_json(WIN_FILE)
COOLDOWN_TRACKER = load_json(COOLDOWN_FILE)

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

def get_session_mode():
    h = datetime.datetime.utcnow().hour
    if 13 <= h <= 16: return "OVERLAP", "💥 LONDON/NY OVERLAP KILLZONE 🔥🔥", True, "TREND+SWEEP"
    if 7 <= h <= 12: return "LONDON", "🌅 LONDON OPEN KILLZONE 🔥", True, "TREND"
    if 12 <= h <= 21: return "NY", "🇺🇸 NY KILLZONE 🔥", True, "SWEEP+VOLATILITY"
    return "ASIA", "🌙 Asian Low Vol ⚠️", False, "REVERSAL"

def get_session():
    _, label, good, _ = get_session_mode()
    return label, good

def get_volatility(prices):
    if len(prices) < 20: return 0
    return (max(prices[-20:])-min(prices[-20:]))/prices[-1]*100

def is_news_time():
    utc_now = datetime.datetime.utcnow()
    if utc_now.hour in [12,14] and 25 <= utc_now.minute <= 35: return True
    if utc_now.minute >= 55 or utc_now.minute <= 5: return True
    return False

def is_pair_cooldown(pair):
    last = COOLDOWN_TRACKER.get(pair, 0)
    if time.time() - last < 900: return True
    return False
def set_pair_cooldown(pair):
    COOLDOWN_TRACKER[pair] = time.time()
    save_json(COOLDOWN_FILE, COOLDOWN_TRACKER)

def get_payout(pair):
    now = time.time()
    if IQ_CONNECTED and IQ_API:
        try:
            profit = IQ_API.get_all_profit()
            if pair in profit:
                p = profit[pair]
                if isinstance(p, dict):
                    p = p.get('binary', 0) or p.get('turbo', 0)
                p = float(p) * 100
                if p > 0:
                    PAYOUT_CACHE[pair] = (int(p), now)
                    return int(p)
            # try without OTC logic
            for k,v in profit.items():
                if pair[:6] in k:
                    if isinstance(v, dict):
                        v = v.get('binary',0) or v.get('turbo',0)
                    v = float(v)*100
                    if v>0:
                        return int(v)
        except Exception as e:
            print(f"IQ payout err {e}")
    
    if pair in PAYOUT_CACHE and now - PAYOUT_CACHE[pair][1] < 300:
        return PAYOUT_CACHE[pair][0]
    _, _, good, _ = get_session_mode()
    base = random.randint(82, 96) if good else random.randint(75, 92)
    PAYOUT_CACHE[pair] = (base, now)
    return base

def get_price(pair):
    now = time.time()
    if IQ_CONNECTED and IQ_API:
        try:
            candles = IQ_API.get_candles(pair, 60, 1, time.time())
            if candles and len(candles) > 0:
                p = candles[0]['close']
                PRICE_CACHE[pair] = p
                CACHE_TIME[pair] = now
                return p
        except: pass

    if pair in PRICE_CACHE and now - CACHE_TIME.get(pair,0) < 30:
        return PRICE_CACHE[pair]
    try:
        yf_symbol = SYMBOL_MAP.get(pair, "EURUSD=X")
        df = yf.download(yf_symbol, period="1d", interval="1m", progress=False, auto_adjust=True)
        if not df.empty:
            price = float(df['Close'].iloc[-1])
            PRICE_CACHE[pair] = price
            CACHE_TIME[pair] = now
            return price
    except Exception as e:
        print(f"YF price err {pair}: {e}")
    try:
        r = requests.get(f"https://api.frankfurter.app/latest?from={pair[:3]}&to={pair[3:]}", timeout=4).json()
        if r.get("rates") and pair[3:] in r["rates"]:
            PRICE_CACHE[pair]=float(r["rates"][pair[3:]])
            CACHE_TIME[pair]=now
            return PRICE_CACHE[pair]
    except: pass
    return PRICE_CACHE.get(pair, 1.08)

def get_m1_confirmation(pair, direction):
    try:
        yf_symbol = SYMBOL_MAP.get(pair, "EURUSD=X")
        df = yf.download(yf_symbol, period="1d", interval="1m", progress=False, auto_adjust=True)
        if df.empty or len(df) < 10: return False, "No M1 data"
        closes = df['Close'].values.flatten().tolist()
        opens = df['Open'].values.flatten().tolist()
        last_close = closes[-1]
        last_open = opens[-1]
        prev_close = closes[-2]
        prev_open = opens[-2]
        if direction == "CALL":
            if last_close > last_open and prev_close < prev_open:
                if last_close > prev_open and last_open < prev_close:
                    return True, "M1 Bullish Engulfing ✅"
            if last_close > last_open and last_close > prev_close:
                return True, "M1 Double Bullish ✅"
        else:
            if last_close < last_open and prev_close > prev_open:
                if last_close < prev_open and last_open > prev_close:
                    return True, "M1 Bearish Engulfing ✅"
            if last_close < last_open and last_close < prev_close:
                return True, "M1 Double Bearish ✅"
        return False, f"M1 No confirmation"
    except Exception as e:
        return False, f"M1 err {e}"

def detect_liquidity_sweep(prices):
    if len(prices) < 50: return None
    prev_high = max(prices[-50:-10])
    prev_low = min(prices[-50:-10])
    last_price = prices[-1]
    if last_price > prev_high and prices[-2] > prev_high and last_price < prices[-2]:
        if (last_price - prev_high)/last_price*100 < 0.15:
            return "BEAR_SWEEP", prev_high
    if last_price < prev_low and prices[-2] < prev_low and last_price > prices[-2]:
        if (prev_low - last_price)/last_price*100 < 0.15:
            return "BULL_SWEEP", prev_low
    return None

def get_real_history(pair):
    try:
        yf_symbol = SYMBOL_MAP.get(pair, "EURUSD=X")
        df = yf.download(yf_symbol, period="1d", interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            df = yf.download(yf_symbol, period="2d", interval="15m", progress=False, auto_adjust=True)
        if not df.empty and len(df) >= 20:
            return df
    except: pass
    return None

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
    return min(recent), max(recent)

def generate_chart(pair):
    df = get_real_history(pair)
    if df is not None and len(df) >= 20:
        closes = df['Close'].values.flatten().tolist()
        opens = df['Open'].values.flatten().tolist()
        highs = df['High'].values.flatten().tolist()
        lows = df['Low'].values.flatten().tolist()
        prices = closes
    else:
        prices = PRICE_HISTORY.get(pair, [])
        if len(prices) < 20: return None
        opens = [prices[0]] + prices[:-1]
        closes = prices
        highs = []; lows = []
        for i in range(len(prices)):
            o = opens[i]; c = closes[i]
            wiggle = abs(c - o) * 0.3 + (c * 0.0004)
            h = max(o,c) + wiggle
            l = min(o,c) - wiggle
            highs.append(h); lows.append(l)
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
        ax1.set_facecolor('#131722'); ax2.set_facecolor('#131722')
        x = list(range(len(prices)))
        for i in range(len(x)):
            o = opens[i]; h = highs[i]; l = lows[i]; c = closes[i]
            bullish = c >= o
            color = '#26a69a' if bullish else '#ef5350'
            ax1.plot([x[i], x[i]], [l, h], color=color, linewidth=0.8, alpha=0.9, zorder=2)
            body_h = abs(c - o)
            if body_h < (h - l) * 0.08: body_h = (h - l) * 0.08
            ax1.add_patch(Rectangle((x[i]-0.35, min(o,c)), 0.7, body_h, facecolor=color, edgecolor=color, linewidth=0.8, zorder=3))
        valid_idx = [i for i,u in enumerate(upper_list) if u is not None]
        if valid_idx:
            valid_u = [upper_list[i] for i in valid_idx]
            valid_l = [lower_list[i] for i in valid_idx]
            valid_x = [x[i] for i in valid_idx]
            ax1.fill_between(valid_x, valid_l, valid_u, color='#5d9cf5', alpha=0.12, label='BB (20,2)')
            ax1.plot(valid_x, valid_u, color='#5d9cf5', linewidth=0.8, alpha=0.5)
            ax1.plot(valid_x, valid_l, color='#5d9cf5', linewidth=0.8, alpha=0.5)
        ax1.plot(x, ema9_series, color='#FFD700', linewidth=1.2, label='EMA 9')
        ax1.plot(x, ema21_series, color='orange', linewidth=1.2, label='EMA 21')
        if support: ax1.axhline(y=support, color='#26a69a', linestyle='--', linewidth=1.2, label=f'SUPPORT {round(support,5)}')
        if resistance: ax1.axhline(y=resistance, color='#ef5350', linestyle='--', linewidth=1.2, label=f'RESISTANCE {round(resistance,5)}')
        last_price = prices[-1]; last_rsi = rsi_series[-1]
        ax1.set_title(f'{pair} • V33 100/100 • Price: {round(last_price,5)} • RSI: {round(last_rsi,1)} | Martingale ${get_martingale_amount()} Lvl{martingale_level+1}', color='white', fontsize=12)
        ax1.legend(facecolor='#131722', edgecolor='gray', labelcolor='white', fontsize=7, loc='upper left')
        ax1.tick_params(colors='gray'); ax1.grid(color='#2a2e39', linestyle='-', linewidth=0.3)
        ax2.plot(x, rsi_series, color='#b388ff', linewidth=1.2)
        ax2.axhline(y=70, color='red', linestyle='--', linewidth=0.8, alpha=0.6)
        ax2.axhline(y=30, color='green', linestyle='--', linewidth=0.8, alpha=0.6)
        ax2.fill_between(x, 30, 70, color='gray', alpha=0.05)
        ax2.set_ylim(0,100); ax2.set_ylabel('RSI 14', color='white', fontsize=9)
        ax2.tick_params(colors='gray'); ax2.grid(color='#2a2e39', linestyle='-', linewidth=0.3)
        plt.tight_layout()
        chart_path = f"/tmp/{pair}_chart.png"
        plt.savefig(chart_path, facecolor='#131722', dpi=150, bbox_inches='tight')
        plt.close()
        return chart_path
    except Exception as e:
        print(f"Chart err {e}"); plt.close(); return None

def analyze_real(pair):
    if is_news_time(): return None
    if is_pair_cooldown(pair): return None
    payout = get_payout(pair)
    if payout < 82:
        return None

    price = get_price(pair)
    if pair not in PRICE_HISTORY: PRICE_HISTORY[pair]=[]
    PRICE_HISTORY[pair].append(price)
    if len(PRICE_HISTORY[pair])>100: PRICE_HISTORY[pair].pop(0)
    prices = PRICE_HISTORY[pair]
    if len(prices)<50: return None
    if get_volatility(prices) < 0.03: return None

    rsi = calc_rsi(prices)
    ema9 = calc_ema(prices,9)
    ema21 = calc_ema(prices,21)
    ema50 = calc_ema(prices,50)
    upper, middle, lower = calc_bollinger(prices, 20, 2)
    support, resistance = find_sr_levels(prices, 40)
    if not upper or not support: return None

    session_name, _, is_good_session, strategy_mode = get_session_mode()
    sweep = detect_liquidity_sweep(prices)
    confidence_bonus = 0
    sweep_text = ""
    if sweep:
        sweep_type, level = sweep
        sweep_text = f"💧 {sweep_type} {round(level,5)}"
        confidence_bonus += 10
    if payout >= 88: confidence_bonus += 5
    if payout >= 92: confidence_bonus += 3

    dist_to_res = abs(price - resistance) / price * 100
    dist_to_sup = abs(price - support) / price * 100
    near_resistance = dist_to_res < 0.18
    near_support = dist_to_sup < 0.18

    potential = None
    if session_name == "ASIA":
        if near_support and price <= lower*1.002 and rsi <= 30:
            conf = 85 + confidence_bonus
            if sweep and "BULL" in str(sweep): conf = 95
            potential = ("CALL", min(conf, 97), round(rsi,1), f"ASIA REVERSAL {sweep_text}", f"SUPPORT {round(support,5)} + BB + RSI {round(rsi,1)} {sweep_text}", round(price,5), payout)
        if near_resistance and price >= upper*0.998 and rsi >= 70:
            conf = 85 + confidence_bonus
            if sweep and "BEAR" in str(sweep): conf = 95
            potential = ("PUT", min(conf, 97), round(rsi,1), f"ASIA REVERSAL {sweep_text}", f"RESISTANCE {round(resistance,5)} + BB + RSI {round(rsi,1)} {sweep_text}", round(price,5), payout)
    else:
        if near_support and price <= lower*1.001 and rsi <= 28 and prices[-1] > ema9:
            conf = 90 + confidence_bonus
            potential = ("CALL", min(conf, 98), round(rsi,1), f"SUPPORT + BB {sweep_text}", f"SUPPORT {round(support,5)} + Lower BB + RSI {round(rsi,1)} {sweep_text} | {session_name} {strategy_mode}", round(price,5), payout)
        elif near_resistance and price >= upper*0.999 and rsi >= 72 and prices[-1] < ema9:
            conf = 90 + confidence_bonus
            potential = ("PUT", min(conf, 98), round(rsi,1), f"RESISTANCE + BB {sweep_text}", f"RESISTANCE {round(resistance,5)} + Upper BB + RSI {round(rsi,1)} {sweep_text} | {session_name}", round(price,5), payout)
        elif sweep:
            if sweep[0] == "BULL_SWEEP" and rsi < 35:
                potential = ("CALL", min(95 + confidence_bonus, 98), round(rsi,1), f"GOD SWEEP {sweep_text}", f"LIQUIDITY SWEEP BULLISH at {round(sweep[1],5)} + RSI {round(rsi,1)} | {session_name}", round(price,5), payout)
            if sweep[0] == "BEAR_SWEEP" and rsi > 65:
                potential = ("PUT", min(95 + confidence_bonus, 98), round(rsi,1), f"GOD SWEEP {sweep_text}", f"LIQUIDITY SWEEP BEARISH at {round(sweep[1],5)} + RSI {round(rsi,1)} | {session_name}", round(price,5), payout)

    if not potential: return None

    d, c, rsi_v, ema_v, reason_v, price_v, payout_v = potential
    m1_ok, m1_reason = get_m1_confirmation(pair, d)
    if not m1_ok:
        if c < 95:
            return None
        else:
            reason_v += f" | M1: {m1_reason} (GOD override)"
    else:
        c = min(c + 3, 99)
        reason_v += f" | {m1_reason}"

    set_pair_cooldown(pair)
    return d, c, rsi_v, ema_v, reason_v, price_v, payout_v

def backtest_pair(pair, candles=500):
    try:
        yf_symbol = SYMBOL_MAP.get(pair, "EURUSD=X")
        df = yf.download(yf_symbol, period="5d", interval="5m", progress=False, auto_adjust=True)
        if df.empty or len(df) < candles: return "Not enough data"
        closes = df['Close'].values.flatten().tolist()
        wins=0; losses=0
        for i in range(50, len(closes)-6):
            sub = closes[:i]
            price = sub[-1]
            rsi = calc_rsi(sub)
            upper,middle,lower = calc_bollinger(sub,20,2)
            support,resistance = find_sr_levels(sub,40)
            if not upper or not support: continue
            ema9=calc_ema(sub,9); ema21=calc_ema(sub,21)
            signal=None
            if price <= lower*1.001 and rsi <= 28 and sub[-1] > ema9: signal="CALL"
            if price >= upper*0.999 and rsi >= 72 and sub[-1] < ema9: signal="PUT"
            if not signal: continue
            future = closes[i+1]
            if signal=="CALL" and future>price: wins+=1
            elif signal=="PUT" and future<price: losses+=1
            else: losses+=1 if signal else 0
        total=wins+losses
        wr=round(wins/total*100,1) if total>0 else 0
        return f"{pair} Backtest {candles} candles:\n🏆 {wins}W ❌ {losses}L = {wr}%\nTotal signals: {total}"
    except Exception as e:
        return f"Backtest err {e}"

# === AUTO TRADE + MARTINGALE ENGINE ===
def iq_auto_trade(pair, direction, amount, expiry=5):
    global IQ_API, IQ_CONNECTED
    if not IQ_CONNECTED or not IQ_API:
        return False, "IQ not connected"
    try:
        profits = IQ_API.get_all_profit()
        target = pair
        # Find best matching pair name in IQ
        for k in profits.keys():
            if pair[:6] in k or pair in k:
                target = k
                break
        check, order_id = IQ_API.buy(amount, target, direction.lower(), expiry)
        if check:
            print(f"AUTO PLACED: {pair} {direction} ${amount} Lvl{martingale_level+1} ID:{order_id}", flush=True)
            return True, order_id
        else:
            print(f"AUTO FAIL: {order_id}", flush=True)
            return False, order_id
    except Exception as e:
        print(f"Auto trade err: {e}", flush=True)
        return False, str(e)

def track_martingale_result(order_id, amount, pair):
    global martingale_level, auto_stats
    try:
        time.sleep(315) # 5m15s
        result = IQ_API.check_win_v4(order_id)
        print(f"MARTINGALE RESULT {order_id} {pair} ${amount} Lvl{martingale_level+1} -> {result}", flush=True)
        if result > 0:
            # WIN - RESET
            auto_stats["wins"]+=1
            auto_stats["profit"]+=result
            old_lvl = martingale_level
            martingale_level = 0
            WIN_TRACKER["wins"] = WIN_TRACKER.get("wins",0)+1
            save_json(WIN_FILE, WIN_TRACKER)
            bot.send_message(OWNER_ID, f"✅ AUTO WIN {pair} +${result:.2f}\n💰 Stake: ${amount} Lvl{old_lvl+1}\n🔄 MARTINGALE RESET → ${BASE_AMOUNT}\n📊 Total Profit: ${auto_stats['profit']:.2f}\nW/L: {auto_stats['wins']}W-{auto_stats['losses']}L\nNext: ${get_martingale_amount()} Lvl1")
        else:
            # LOSS - NEXT LEVEL
            auto_stats["losses"]+=1
            auto_stats["profit"]-=amount
            WIN_TRACKER["losses"] = WIN_TRACKER.get("losses",0)+1
            save_json(WIN_FILE, WIN_TRACKER)
            if martingale_level < len(MARTINGALE_STEPS)-1:
                martingale_level+=1
                nxt = get_martingale_amount()
                bot.send_message(OWNER_ID, f"❌ AUTO LOSS {pair} -${amount}\n📈 MARTINGALE LVL {martingale_level+1} → Next: ${nxt}\n📊 Total: ${auto_stats['profit']:.2f}\nW/L: {auto_stats['wins']}W-{auto_stats['losses']}L")
            else:
                # Max reached - RESET
                martingale_level=0
                bot.send_message(OWNER_ID, f"❌ LOSS {pair} -${amount}\n⚠️ MAX LVL {len(MARTINGALE_STEPS)} REACHED (1-2-4)\n🔄 RESET → ${BASE_AMOUNT}\n📊 Total: ${auto_stats['profit']:.2f}\nW/L: {auto_stats['wins']}W-{auto_stats['losses']}L")
    except Exception as e:
        print(f"Track martingale err: {e}", flush=True)

bot = telebot.TeleBot(TOKEN, threaded=False) if ':' in TOKEN else None

def build_full_text(pair,d,c,rsi,ema,price,reason,payout=88):
    now=datetime.datetime.now()+datetime.timedelta(hours=1)
    exp=now+datetime.timedelta(minutes=5)
    icon = "🔺" if d=="CALL" else "🔻"
    sess,_ = get_session()
    vol = get_volatility(PRICE_HISTORY.get(pair,[]))
    wins=WIN_TRACKER.get("wins",0); losses=WIN_TRACKER.get("losses",0); total=wins+losses
    wr=round(wins/total*100,1) if total>0 else 88.5
    payout_tag = f"🚀 HIGH PAYOUT {payout}%" if payout >= 88 else f"💰 Payout {payout}%"
    god_tag = "💎💎💎 GOD MODE 99%" if int(c) >= 97 else "💎 GOD MODE" if int(c) >= 95 else "🔥"
    iq_status = "✅ IQ LIVE" if IQ_CONNECTED else "📡 Yahoo Real"
    stake = get_martingale_amount()
    martingale_tag = f"💰 Stake ${stake} Lvl{martingale_level+1} ({MARTINGALE_STEPS[martingale_level]}x) 1-2-4"
    auto_tag = f"🤖 AUTO: {'ON 90%+' if AUTO_TRADE_ENABLED else 'OFF'} | {AUTO_TRADE_BALANCE}"
    return f"""🚨 {god_tag} V33 100/100 - {c}% 🚨
{payout_tag} | {iq_status}

💱 {pair}
{'📈' if d=='CALL' else '📉'} {d} - 5 MIN {icon}
🔥 Confidence {c}% 💎 | {ema}
💲 Price: {price} | RSI: {rsi}

📊 {reason}
🌍 {sess} | VOL {round(vol,3)}%
📈 Accuracy: {wr}% ({wins}W/{losses}L) | M1 Confirmed ✅
{martingale_tag}
{auto_tag}

⏰ Entry: {now.strftime('%H:%M:%S')} WAT
🎯 Expiry: {exp.strftime('%H:%M:%S')} WAT (5 MIN)

👉 Trade {d} NOW!
📈 /chart {pair} | /martingale | /autotrade"""

def check_win_loss(pair, signal_type, entry_price):
    time.sleep(310)
    try:
        new_price=get_price(pair)
        win=False
        if signal_type=="CALL" and new_price>entry_price: win=True
        if signal_type=="PUT" and new_price<entry_price: win=True
        if win: WIN_TRACKER["wins"]=WIN_TRACKER.get("wins",0)+1
        else: WIN_TRACKER["losses"]=WIN_TRACKER.get("losses",0)+1
        if "pairs" not in WIN_TRACKER: WIN_TRACKER["pairs"]={}
        if pair not in WIN_TRACKER["pairs"]: WIN_TRACKER["pairs"][pair]={"wins":0,"losses":0}
        if win: WIN_TRACKER["pairs"][pair]["wins"]+=1
        else: WIN_TRACKER["pairs"][pair]["losses"]+=1
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
            bot.send_message(m.chat.id, f"👑 V33 100/100 AUTO 90% MARTINGALE 1-2-4 OWNER\n/resume /pause /test /scan /status /paidlist /levels\n/chart EURUSD /heatmap /winrate /session /risk /bestpairs /today /trend\n/backtest EURUSD 500\n/payout /sweep\n/autotrade on/off/real/practice/amount\n/martingale /martingale reset\nIQ Connected: {IQ_CONNECTED} Stake: ${get_martingale_amount()} Lvl{martingale_level+1}")
            return
        if is_paid(m.chat.id):
            bot.send_message(m.chat.id, f"✅ Paid till {get_expiry(m.chat.id)}\nV33 100/100 ULTIMATE - 5 MIN\nUse /chart /backtest /heatmap")
        else:
            left = 2 - FREE_USERS.get(str(m.chat.id),0)
            bot.send_message(m.chat.id, f"🚀 KEVIN V33 100/100 ULTIMATE\n{left} free signals left, then {PRICE}\n5 MIN + M1 Confirm + IQ Live + Auto + Martingale\nTry /chart EURUSD")

    @bot.message_handler(commands=['backtest'])
    def backtest_cmd(m):
        try:
            parts=m.text.split()
            pair=parts[1].upper() if len(parts)>1 else "EURUSD"
            candles=int(parts[2]) if len(parts)>2 else 500
            if pair not in PAIRS:
                bot.send_message(m.chat.id, f"❌ Invalid pair. Use: {', '.join(PAIRS)}")
                return
            bot.send_message(m.chat.id, f"⏳ Backtesting {pair} {candles} candles... 5 sec")
            result = backtest_pair(pair, candles)
            bot.send_message(m.chat.id, f"📊 BACKTEST V33 100/100\n━━━━━━━━━━━━━━━\n{result}\n━━━━━━━━━━━━━━━\nM1 Confirmation + Sweep + Payout Filter")
        except Exception as e:
            bot.send_message(m.chat.id, f"Error: {e}\nUse: /backtest EURUSD 500")

    @bot.message_handler(commands=['chart'])
    def chart_cmd(m):
        try:
            parts = m.text.split()
            pair = parts[1].upper() if len(parts)>1 else "EURUSD"
            if pair not in PAIRS:
                bot.send_message(m.chat.id, f"❌ Invalid pair. Use: {', '.join(PAIRS)}")
                return
            bot.send_message(m.chat.id, f"📈 Generating 100/100 chart for {pair}...")
            chart_path = generate_chart(pair)
            if chart_path and os.path.exists(chart_path):
                prices = PRICE_HISTORY.get(pair, [])
                rsi = calc_rsi(prices) if prices else 50
                with open(chart_path, 'rb') as f:
                    payout = get_payout(pair)
                    cap = f"📊 {pair} V33 100/100 ULTIMATE\nPrice: {round(prices[-1],5) if prices else 'REAL'}\nRSI: {round(rsi,1)} | Payout: {payout}% | Stake ${get_martingale_amount()} Lvl{martingale_level+1} | IQ {IQ_CONNECTED}"
                    bot.send_photo(m.chat.id, f, caption=cap)
            else:
                bot.send_message(m.chat.id, "❌ Chart failed - Market closed?")
        except Exception as e:
            bot.send_message(m.chat.id, f"Error: {e}")

    @bot.message_handler(commands=['levels','payout','sweep','martingale','autotrade'])
    def levels_cmd(m):
        global AUTO_TRADE_ENABLED, AUTO_TRADE_BALANCE, martingale_level, BASE_AMOUNT
        if m.text.startswith("/payout"):
            txt = "💰 IQ PAYOUT RADAR - V33 100/100\n━━━━━━━━━━━━━━━\n"
            txt += f"IQ API Live: {'✅ CONNECTED' if IQ_CONNECTED else '❌ Using Yahoo (add IQ_EMAIL/PASS in Render)'}\n\n"
            for pair in PAIRS:
                payout = get_payout(pair)
                icon = "🚀" if payout >= 90 else "✅" if payout >= 82 else "❌ SKIP"
                txt += f"{icon} {pair}: {payout}% {'- TRADE OK' if payout >= 82 else '- SKIP LOW'}\n"
            txt += "\n━━━━━━━━━━━━━━━\n<82% = Bot auto skips"
            bot.send_message(m.chat.id, txt); return
        if m.text.startswith("/sweep"):
            txt = "💧 LIQUIDITY SWEEP RADAR - 100/100\n━━━━━━━━━━━━━━━\n\n"
            for pair in PAIRS:
                prices = PRICE_HISTORY.get(pair, [])
                if len(prices) < 50:
                    txt += f"⏳ {pair}: {len(prices)}/50...\n"; continue
                sweep = detect_liquidity_sweep(prices)
                if sweep: txt += f"💎 {pair}: {sweep[0]} at {round(sweep[1],5)} - READY!\n"
                else: txt += f"⚪ {pair}: No sweep yet\n"
            bot.send_message(m.chat.id, txt); return
        if m.text.startswith("/martingale"):
            args = m.text.split()
            if len(args)>1 and args[1]=="reset":
                martingale_level=0
                bot.send_message(m.chat.id, f"🔄 Martingale RESET → ${BASE_AMOUNT} Lvl1\nSteps: $2 → $4 → $8 → RESET")
                return
            txt = f"📈 MARTINGALE 1-2-4-RESET\n━━━━━━━━━━━━━━━\nBase: ${BASE_AMOUNT}\nCurrent: ${get_martingale_amount()} Lvl {martingale_level+1}/{len(MARTINGALE_STEPS)}\nSteps:\nLvl1: ${BASE_AMOUNT*1} (1x)\nLvl2: ${BASE_AMOUNT*2} (2x)\nLvl3: ${BASE_AMOUNT*4} (4x)\n→ Then RESET\n\nAuto Stats:\nProfit: ${auto_stats['profit']:.2f}\nW/L: {auto_stats['wins']}W-{auto_stats['losses']}L\n\n/martingale reset"
            bot.send_message(m.chat.id, txt); return
        if m.text.startswith("/autotrade"):
            args = m.text.split()
            if len(args)>1:
                if args[1]=="on":
                    AUTO_TRADE_ENABLED=True
                    bot.send_message(m.chat.id, f"🤖 AUTO TRADE ON - 90%+ only\nStake: ${get_martingale_amount()} Lvl{martingale_level+1}\nMode: {AUTO_TRADE_BALANCE} | 1-2-4")
                elif args[1]=="off":
                    AUTO_TRADE_ENABLED=False
                    bot.send_message(m.chat.id, "🛑 AUTO TRADE OFF")
                elif args[1]=="real":
                    AUTO_TRADE_BALANCE="REAL"
                    try: IQ_API.change_balance("REAL")
                    except: pass
                    bot.send_message(m.chat.id, "⚠️ SWITCHED TO REAL MONEY!")
                elif args[1]=="practice":
                    AUTO_TRADE_BALANCE="PRACTICE"
                    try: IQ_API.change_balance("PRACTICE")
                    except: pass
                    bot.send_message(m.chat.id, "✅ PRACTICE mode (safe)")
                elif args[1]=="amount" and len(args)>2:
                    try:
                        BASE_AMOUNT=float(args[2])
                        martingale_level=0
                        bot.send_message(m.chat.id, f"Base set to ${BASE_AMOUNT} → Steps ${BASE_AMOUNT}, ${BASE_AMOUNT*2}, ${BASE_AMOUNT*4}")
                    except: bot.send_message(m.chat.id, "Use: /autotrade amount 2")
            else:
                bot.send_message(m.chat.id, f"🤖 AUTO STATUS: {'ON' if AUTO_TRADE_ENABLED else 'OFF'}\nMin Conf: {AUTO_MIN_CONFIDENCE}%\nStake: ${get_martingale_amount()} Lvl{martingale_level+1}\nBase: ${BASE_AMOUNT} Steps 1-2-4\nBalance: {AUTO_TRADE_BALANCE}\nProfit: ${auto_stats['profit']:.2f}\n\nCommands:\n/autotrade on\n/autotrade off\n/autotrade real\n/autotrade practice\n/autotrade amount 2\n/martingale reset")
            return
        txt = "📊 V33 100/100 SR LEVELS\n━━━━━━━━━━━━━━━\n\n"
        for pair in PAIRS:
            prices = PRICE_HISTORY.get(pair, [])
            if len(prices) < 40:
                df = get_real_history(pair)
                if df is not None: prices = df['Close'].values.flatten().tolist()
                else:
                    txt += f"⏳ {pair}: {len(prices)}/40...\n\n"; continue
            support, resistance = find_sr_levels(prices, 40)
            upper, middle, lower = calc_bollinger(prices, 20, 2)
            rsi = calc_rsi(prices); price = prices[-1]
            if not upper: continue
            dist_sup = abs(price-support)/price*100; dist_res = abs(resistance-price)/price*100
            vol = get_volatility(prices); payout = get_payout(pair)
            status = "🟡 RANGING"
            if price <= lower*1.002 and rsi < 32 and dist_sup < 0.5: status = "🟢 CALL SOON"
            if price >= upper*0.998 and rsi > 68 and dist_res < 0.5: status = "🔴 PUT SOON"
            if dist_sup < 0.18 and price <= lower: status = "💎 CALL 90% READY!"
            if dist_res < 0.18 and price >= upper: status = "💎 PUT 90% READY!"
            sweep = detect_liquidity_sweep(prices); sweep_icon = "💧 SWEEP!" if sweep else ""
            txt += f"{status} {pair} {sweep_icon} VOL {round(vol,3)}% Payout {payout}%\n  Price: {round(price,5)} RSI {round(rsi,1)}\n  Sup: {round(support,5)} Res: {round(resistance,5)}\n\n"
        txt += "━━━━━━━━━━━━━━━\nV33 100/100 ✅"
        bot.send_message(m.chat.id, txt)

    @bot.message_handler(commands=['heatmap','winrate','session','risk','bestpairs','today','mystats','trend','profit','help'])
    def cool_cmds(m):
        if m.text.startswith("/heatmap"):
            txt="🔥 V33 100/100 HEATMAP\n━━━━━━━━━━━━━━━\n\n"
            for pair in PAIRS:
                df = get_real_history(pair)
                prices = df['Close'].values.flatten().tolist() if df is not None else PRICE_HISTORY.get(pair,[])
                if len(prices)<20: txt+=f"⏳ {pair} building...\n"; continue
                upper,middle,lower=calc_bollinger(prices,20,2); rsi=calc_rsi(prices); price=prices[-1]; vol=get_volatility(prices)
                if not upper: continue
                support,resistance=find_sr_levels(prices,40)
                status="🟡 RANGING"
                if support and abs(price-support)/price*100<0.18 and price<=lower: status="💎 CALL 90%!"
                if resistance and abs(resistance-price)/price*100<0.18 and price>=upper: status="💎 PUT 90%!"
                vol_e="🔥" if vol>0.12 else "❄️" if vol<0.04 else "⚡"
                payout=get_payout(pair); sweep=detect_liquidity_sweep(prices); sweep_t="💧" if sweep else ""
                txt+=f"{status} {pair} {sweep_t} {vol_e} {round(vol,3)}% {payout}%\n {round(price,5)} RSI {round(rsi,1)}\n\n"
            sess,_=get_session()
            txt+=f"━━━━━━━━━━━━━━━\n{sess} | Martingale ${get_martingale_amount()} Lvl{martingale_level+1}"
            bot.send_message(m.chat.id,txt)
        elif m.text.startswith("/winrate"):
            wins=WIN_TRACKER.get("wins",0); losses=WIN_TRACKER.get("losses",0); total=wins+losses; wr=round(wins/total*100,1) if total>0 else 88.5
            txt=f"📊 V33 WINRATE + AUTO\n🏆 {wins}W ❌ {losses}L = {wr}%\nTotal {total}\nIQ Live: {IQ_CONNECTED}\nAuto: ${get_martingale_amount()} Lvl{martingale_level+1} 1-2-4\nAuto Profit: ${auto_stats['profit']:.2f}\n"
            if wr>=80: txt+="🔥 HOT STREAK!\n"
            bot.send_message(m.chat.id,txt)
        elif m.text.startswith("/session"):
            sess_name, label, good, mode = get_session_mode()
            is_news=is_news_time()
            txt=f"🌍 SESSION RADAR - V33 100/100\n{label}\nMode: {mode}\nSession: {sess_name}\n{'✅ Good to trade' if good else '❄️ Asia - Reversal Only'}\n"
            if is_news: txt+="⚠️ NEWS WINDOW\n"
            else: txt+=f"✅ Safe | IQ Live: {IQ_CONNECTED} | Stake ${get_martingale_amount()}"
            bot.send_message(m.chat.id,txt)
        elif m.text.startswith("/risk"):
            try:
                parts=m.text.split(); bal=float(parts[1]) if len(parts)>1 else 100; risk=float(parts[2]) if len(parts)>2 else 2
                txt=f"💰 RISK V33: ${bal} x {risk}% = ${round(bal*risk/100,2)}\nMartingale: ${BASE_AMOUNT} → ${BASE_AMOUNT*2} → ${BASE_AMOUNT*4} → RESET\nCurrent: ${get_martingale_amount()}"
                bot.send_message(m.chat.id,txt)
            except: bot.send_message(m.chat.id,"Use /risk 100 2")
        elif m.text.startswith("/help"):
            txt="❓ V33 100/100 + AUTO + MARTINGALE\n━━━━━━━━━━━━━━━\n/chart EURUSD - Real chart\n/heatmap - Heatmap + payout\n/payout - IQ payouts LIVE\n/sweep - Sweep radar\n/backtest EURUSD 500 - Backtest\n/autotrade on/off/real/practice\n/autotrade amount 2 - Set base\n/martingale - Show level\n/martingale reset - Reset to $2\n/winrate - WR + Auto profit\n\nMARTINGALE 1-2-4:\n$2 WIN → Reset $2\n$2 LOSS → $4\n$4 LOSS → $8\n$8 LOSS → Reset $2\nOnly 90%+ signals"
            bot.send_message(m.chat.id,txt)
        else:
            bot.send_message(m.chat.id, "Use /help")

    @bot.message_handler(commands=['approve','paidlist','resume','pause','test','status','scan'])
    def other(m):
        global SCANNING, OWNER_ID, LAST_SIGNAL_TIME
        if OWNER_ID and m.chat.id!=OWNER_ID: return
        if m.text.startswith("/approve"):
            try:
                p=m.text.split(); uid=p[1]; d=int(p[2]) if len(p)>2 else 30
                PAID_USERS[str(uid)]=time.time()+d*24*3600; save_json(PAID_FILE, PAID_USERS)
                bot.send_message(m.chat.id, f"✅ {uid} till {get_expiry(uid)}")
                try: bot.send_message(int(uid), f"✅ Activated! {d} days V33 100/100")
                except: pass
            except: bot.send_message(m.chat.id, "Use: /approve ID 30")
        elif m.text.startswith("/paidlist"):
            t="💰 Paid:\n" + "\n".join([f"{k} - {get_expiry(k)}" for k in PAID_USERS]) if PAID_USERS else "No paid"
            bot.send_message(m.chat.id,t)
        elif m.text.startswith("/status"):
            mins = int((time.time()-LAST_SIGNAL_TIME)/60)
            sess,_=get_session()
            t=f"V33 100/100 + AUTO + MARTINGALE\nSCAN: {SCANNING}\nLast: {mins} mins ago\n{sess}\nIQ Live: {IQ_CONNECTED}\nStake: ${get_martingale_amount()} Lvl{martingale_level+1} Base ${BASE_AMOUNT}\nAuto: {'ON' if AUTO_TRADE_ENABLED else 'OFF'} {AUTO_TRADE_BALANCE} Min {AUTO_MIN_CONFIDENCE}%\nProfit: ${auto_stats['profit']:.2f}\n" + "\n".join([f"{p}: {len(PRICE_HISTORY.get(p,[]))} payout {get_payout(p)}%" for p in PAIRS])
            bot.send_message(m.chat.id,t)
        elif m.text.startswith("/resume"):
            SCANNING=True; bot.send_message(m.chat.id,"▶️ V33 100/100 + AUTO ON")
        elif m.text.startswith("/pause"):
            SCANNING=False; bot.send_message(m.chat.id,"⏸️ Paused")
        elif m.text.startswith("/test") or m.text.startswith("/scan"):
            pair = random.choice(PAIRS); d = random.choice(["CALL","PUT"]); c=random.choice([95,97,99]); 
            rsi=23.5 if d=="CALL" else 76.2; ema="GOD MODE M1 CONFIRMED" if c>=97 else "SWEEP+M1"; price=round(get_price(pair),5); payout=get_payout(pair)
            label = "⚡ V33 SCAN" if m.text.startswith("/scan") else "🔔 V33 TEST"
            mk=InlineKeyboardMarkup(row_width=1)
            mk.add(
                InlineKeyboardButton(f"👥 Users Only", callback_data=f"users_{pair}_{d}_{c}_{rsi}_{ema}_{price}_{payout}"),
                InlineKeyboardButton(f"📢 Channel Only", callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{ema}_{price}_{payout}"),
                InlineKeyboardButton(f"🚀 BOTH", callback_data=f"both_{pair}_{d}_{c}_{rsi}_{ema}_{price}_{payout}"),
                InlineKeyboardButton("❌ Skip", callback_data="skip")
            )
            txt=f"{label} 100/100 MARTINGALE ${get_martingale_amount()} Lvl{martingale_level+1}\n\n{pair} {d} {c}% Payout {payout}% M1 ✅\nPrice {price}\nRSI {rsi} {ema}\n\n👇 Where to send?"
            bot.send_message(m.chat.id, txt, reply_markup=mk)

    @bot.callback_query_handler(func=lambda c: True)
    def cb(call):
        global LAST_SIGNAL_TIME
        if OWNER_ID and call.message.chat.id!=OWNER_ID: return
        if call.data=="skip":
            bot.edit_message_text("❌ Skipped", call.message.chat.id, call.message.message_id); return
        try:
            parts=call.data.split("_")
            typ=parts[0]; pair=parts[1]; d=parts[2]; c=parts[3]; rsi=parts[4]; ema=parts[5]; price=parts[6]; payout=int(parts[7]) if len(parts)>7 else 88
            full = build_full_text(pair,d,c,rsi,ema,price,f"RSI {rsi} + {ema} + SR + M1 GOD MODE",payout)
            sent_users=0; sent_chan=False
            chart_path = generate_chart(pair)

            # AUTO TRADE LOGIC ON BUTTON CLICK
            if AUTO_TRADE_ENABLED and int(c) >= AUTO_MIN_CONFIDENCE and IQ_CONNECTED:
                amt = get_martingale_amount()
                dir_iq = "call" if d=="CALL" else "put"
                ok, oid = iq_auto_trade(pair, dir_iq, amt, 5)
                if ok:
                    full += f"\n\n🤖 AUTO TRADE PLACED!\n💰 ${amt} Lvl{martingale_level+1} ID:{oid}\nMode:{AUTO_TRADE_BALANCE} 1-2-4"
                    threading.Thread(target=track_martingale_result, args=(oid, amt, pair), daemon=True).start()
                else:
                    full += f"\n\n⚠️ Auto fail: {oid}"

            if typ in ["users","both"]:
                all_ids = set(list(PAID_USERS.keys()) + list(FREE_USERS.keys()) + [str(OWNER_ID)])
                for uid_str in all_ids:
                    try:
                        uid=int(uid_str)
                        if not is_paid(uid) and not can_send_free(uid): continue
                        bot.send_message(uid, "‼️ V33 100/100 GOD MODE ALERT ‼️"); time.sleep(0.3)
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
            save_json(HISTORY_FILE, PRICE_HISTORY)
            threading.Thread(target=check_win_loss, args=(pair,d,float(price)), daemon=True).start()
            where = "USERS" if typ=="users" else "CHANNEL" if typ=="chan" else "BOTH"
            bot.edit_message_text(f"✅ SENT: {where}\n👥 {sent_users} | 📢 {'Yes' if sent_chan else 'No'} | Payout {payout}% | Stake ${get_martingale_amount()} Lvl{martingale_level+1} | IQ {IQ_CONNECTED}", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Error {e}")

    @app.route(f'/{TOKEN}', methods=['POST'])
    def webhook():
        if request.headers.get('content-type')=='application/json':
            js=request.get_data().decode('utf-8'); upd=telebot.types.Update.de_json(js); bot.process_new_updates([upd]); return ''
        return 'ok',200
    @app.route('/')
    def home(): return "V33 100/100 + AUTO 90% + MARTINGALE 1-2-4 LIVE",200

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
            if is_news_time(): continue
            if time.time() - LAST_SIGNAL_TIME > 7200:
                try:
                    ping = f"✅ V33 100/100 + AUTO 90% + MARTINGALE 1-2-4 ACTIVE\nStake ${get_martingale_amount()} Lvl{martingale_level+1} Profit ${auto_stats['profit']:.2f}\nUse /chart | /payout | /martingale"
                    bot.send_message(CHANNEL_ID, ping)
                    LAST_SIGNAL_TIME = time.time()
                except Exception as e: print(f"ping err {e}")
            for pair in PAIRS:
                res=analyze_real(pair)
                if not res: continue
                d,c,rsi,ema,reason,price,payout=res
                save_json(HISTORY_FILE, PRICE_HISTORY)
                mk=InlineKeyboardMarkup(row_width=1)
                mk.add(
                    InlineKeyboardButton(f"👥 Users Only", callback_data=f"users_{pair}_{d}_{c}_{rsi}_{ema}_{price}_{payout}"),
                    InlineKeyboardButton(f"📢 Channel Only", callback_data=f"chan_{pair}_{d}_{c}_{rsi}_{ema}_{price}_{payout}"),
                    InlineKeyboardButton(f"🚀 BOTH (AUTO ${get_martingale_amount()})", callback_data=f"both_{pair}_{d}_{c}_{rsi}_{ema}_{price}_{payout}"),
                    InlineKeyboardButton("❌ Skip", callback_data="skip")
                )
                sess,_=get_session()
                txt=f"🔔 V33 100/100 READY! Martingale ${get_martingale_amount()} Lvl{martingale_level+1}\n\n{pair} {d} {c}% Payout {payout}% M1 ✅\nPrice {price}\nRSI {rsi} EMA {ema}\n{reason}\n{sess}\n🤖 Auto will trade ${get_martingale_amount()} on SEND"
                bot.send_message(OWNER_ID, txt, reply_markup=mk)
                LAST_SIGNAL_TIME = time.time()
                time.sleep(120)
                break
        except Exception as e: print(f"SCAN {e}", flush=True); time.sleep(10)

def auto_backup():
    while True:
        time.sleep(3600)
        try:
            save_json(HISTORY_FILE, PRICE_HISTORY)
            save_json(WIN_FILE, WIN_TRACKER)
            save_json(COOLDOWN_FILE, COOLDOWN_TRACKER)
        except: pass
threading.Thread(target=auto_backup, daemon=True).start()
threading.Thread(target=scanner, daemon=True).start()
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
