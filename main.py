# -*- coding: utf-8 -*-
import os, requests, time, threading, telebot, datetime, json
from telebot import types
from flask import Flask, request

BOT_TOKEN=os.environ.get("BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
CHANNEL_ID="@KEVINTRAILBLAZE"
ADMIN_ID=os.environ.get("ADMIN_ID")
ADMIN_CHAT_ID=None

bot=telebot.TeleBot(BOT_TOKEN)
prices_history=[]
last_signal_time={}
pending_signals={}
ACTIVE_FILE="active_signals.json"

def save_active():
    try:
        with open(ACTIVE_FILE,"w") as f:
            json.dump(active_signals,f)
    except: pass

def load_active():
    global active_signals
    try:
        if os.path.exists(ACTIVE_FILE):
            with open(ACTIVE_FILE,"r") as f:
                active_signals=json.load(f)
        else:
            active_signals=[]
    except:
        active_signals=[]

active_signals=[]
load_active()

app=Flask(__name__)
@app.route('/')
def home():
    return f"KEVIN GOLD ONLY V4 LIVE | Active {len(active_signals)} | Gold Price ${get_gold()}"

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except: pass
    return "OK", 200

@app.route('/setwebhook')
def set_webhook():
    try:
        bot.remove_webhook()
        time.sleep(1)
        ext_url = os.getenv("RENDER_EXTERNAL_URL")
        if ext_url:
            url = f"{ext_url}/{BOT_TOKEN}"
            bot.set_webhook(url=url)
            return f"Webhook set to {url}"
        return "No URL"
    except Exception as e:
        return f"Error {e}"

def get_gold():
    try:
        r=requests.get("https://api.gold-api.com/price/XAU", timeout=10).json()
        return float(r["price"])
    except:
        return 4195.60

def calc_rsi(prices, period=14):
    if len(prices) < period+1:
        return 50.0
    gains=[]; losses=[]
    for i in range(1, len(prices)):
        diff=prices[i]-prices[i-1]
        if diff>0:
            gains.append(diff); losses.append(0)
        else:
            gains.append(0); losses.append(abs(diff))
    if len(gains)<period:
        return 50.0
    avg_gain=sum(gains[-period:])/period
    avg_loss=sum(losses[-period:])/period
    if avg_loss==0: return 70.0
    if avg_gain==0: return 30.0
    rs=avg_gain/avg_loss
    return 100-(100/(1+rs))

def build_short_msg(symbol, price, rsi, action):
    sl=price-10 if action=="BUY" else price+10
    tp1=price+20 if action=="BUY" else price-20
    tp2=price+40 if action=="BUY" else price-40
    tp3=price+60 if action=="BUY" else price-60
    emoji="🟢 BUY" if action=="BUY" else "🔴 SELL"
    msg="👑 KEVIN TRAILBLAZE 👑\n"+emoji+" XAUUSD GOLD\n\n💠 Entry: $"+str(round(price,2))+"\n🛡️ SL: $"+str(round(sl,2))+"\n\n🎯 TP1: $"+str(round(tp1,2))+"\n🎯 TP2: $"+str(round(tp2,2))+"\n🎯 TP3: $"+str(round(tp3,2))+"\n\n📊 RSI: "+str(round(rsi,1))+"\n🔗 @KEVINTRAILBLAZE"
    data={"symbol":symbol,"action":action,"entry":price,"sl":sl,"tp1":tp1,"tp2":tp2,"tp3":tp3}
    return msg,data

def request_approval(symbol, price, rsi, action):
    global ADMIN_CHAT_ID
    target=None
    if ADMIN_ID:
        try: target=int(ADMIN_ID)
        except: pass
    if not target: target=ADMIN_CHAT_ID
    short_msg,data=build_short_msg(symbol, price, rsi, action)
    if not target:
        try:
            bot.send_message(CHANNEL_ID, short_msg)
            active_signals.append({"symbol":data["symbol"],"action":data["action"],"entry":data["entry"],"sl":data["sl"],"tp1":data["tp1"],"tp2":data["tp2"],"tp3":data["tp3"],"tp1_hit":False,"tp2_hit":False,"tp3_hit":False})
            save_active()
        except Exception as e: print(e)
        return
    sig_id=symbol+"_"+str(int(time.time()))
    pending_signals[sig_id]=data
    pending_signals[sig_id]["_msg"]=short_msg
    markup=types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ SEND", callback_data="approve_"+sig_id), types.InlineKeyboardButton("❌ REJECT", callback_data="reject_"+sig_id))
    try:
        bot.send_message(target, "🔔 NEW GOLD SIGNAL 👑\n\n"+short_msg+"\n\nSend to channel?", reply_markup=markup)
    except Exception as e: print(e)

def check_tp_hits(current_price, symbol):
    to_remove=[]
    for sig in active_signals[:]:
        if sig["symbol"]!=symbol: continue
        try:
            s_sym=sig["symbol"]; s_act=sig["action"]; s_ent=sig["entry"]; s_tp1=sig["tp1"]; s_tp2=sig["tp2"]; s_tp3=sig["tp3"]; s_sl=sig["sl"]
            if s_act=="BUY":
                if not sig.get("tp1_hit", False) and current_price>=s_tp1:
                    sig["tp1_hit"]=True; save_active()
                    try: bot.send_message(CHANNEL_ID, f"💸 TP1 HIT ✅\n{s_sym} BUY\n${round(s_ent,2)} -> ${round(s_tp1,2)}\n🔒 Move SL to BE\n@KEVINTRAILBLAZE")
                    except: pass
                if not sig.get("tp2_hit", False) and current_price>=s_tp2:
                    sig["tp2_hit"]=True; save_active()
                    try: bot.send_message(CHANNEL_ID, f"🏆 VICTORY 🏆\n{s_sym} TP1 + TP2 HIT\n@KEVINTRAILBLAZE")
                    except: pass
                if not sig.get("tp3_hit", False) and current_price>=s_tp3:
                    try: bot.send_message(CHANNEL_ID, f"🤑 JACKPOT 🤑\n{s_sym} ALL TP HIT!\n${round(s_ent,2)} -> ${round(s_tp3,2)}\n@KEVINTRAILBLAZE")
                    except: pass
                    to_remove.append(sig)
                if current_price<=s_sl:
                    try: bot.send_message(CHANNEL_ID, f"🛑 SL HIT {s_sym}")
                    except: pass
                    to_remove.append(sig)
            else:
                if not sig.get("tp1_hit", False) and current_price<=s_tp1:
                    sig["tp1_hit"]=True; save_active()
                    try: bot.send_message(CHANNEL_ID, f"💸 TP1 HIT ✅\n{s_sym} SELL\n${round(s_ent,2)} -> ${round(s_tp1,2)}\n@KEVINTRAILBLAZE")
                    except: pass
                if not sig.get("tp2_hit", False) and current_price<=s_tp2:
                    sig["tp2_hit"]=True; save_active()
                    try: bot.send_message(CHANNEL_ID, f"🏆 VICTORY 🏆\n{s_sym} TP1 + TP2 HIT\n@KEVINTRAILBLAZE")
                    except: pass
                if not sig.get("tp3_hit", False) and current_price<=s_tp3:
                    try: bot.send_message(CHANNEL_ID, f"🤑 JACKPOT 🤑\n{s_sym} ALL TP HIT!\n@KEVINTRAILBLAZE")
                    except: pass
                    to_remove.append(sig)
                if current_price>=s_sl:
                    try: bot.send_message(CHANNEL_ID, f"🛑 SL HIT {s_sym}")
                    except: pass
                    to_remove.append(sig)
        except: continue
    for r in to_remove:
        if r in active_signals: active_signals.remove(r)
    if to_remove: save_active()

def signal_loop():
    while True:
        try:
            now=time.time()
            g=get_gold()
            prices_history.append(g)
            if len(prices_history)>100: prices_history.pop(0)
            r=calc_rsi(prices_history)
            check_tp_hits(g,"GOLD")
            print(f"GOLD ${g} RSI {r} Active {len(active_signals)}", flush=True)
            # GOLD ONLY - No market close check, trade 24/7 since Gold now open
            if r<30 or r>70:
                has_gold=False
                for s in active_signals:
                    if s["symbol"]=="GOLD": has_gold=True
                if not has_gold:
                    if now-last_signal_time.get("GOLD",0)>3600: # 1 hour cooldown
                        act="BUY" if r<30 else "SELL"
                        request_approval("GOLD",g,r,act)
                        last_signal_time["GOLD"]=now
        except Exception as e:
            print("loop error", e)
        time.sleep(60)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        d=call.data
        if d.startswith("approve_"):
            sid=d.replace("approve_","")
            sd=pending_signals.pop(sid,None)
            if not sd:
                bot.answer_callback_query(call.id,"Done"); return
            msg=sd.get("_msg")
            bot.send_message(CHANNEL_ID, msg)
            active_signals.append({"symbol":sd["symbol"],"action":sd["action"],"entry":sd["entry"],"sl":sd["sl"],"tp1":sd["tp1"],"tp2":sd["tp2"],"tp3":sd["tp3"],"tp1_hit":False,"tp2_hit":False,"tp3_hit":False})
            save_active()
            bot.answer_callback_query(call.id,"✅ Sent!")
            bot.edit_message_text("✅ SENT to @KEVINTRAILBLAZE\n\n"+msg, call.message.chat.id, call.message.message_id)
        elif d.startswith("reject_"):
            pending_signals.pop(d.replace("reject_",""),None)
            bot.answer_callback_query(call.id,"❌ Rejected")
            bot.edit_message_text("❌ Rejected", call.message.chat.id, call.message.message_id)
    except Exception as e:
        print(e)

@bot.message_handler(commands=['start','price','active','signal','id','testsignal'])
def handle_start(message):
    global ADMIN_CHAT_ID
    if message.chat.type=="private":
        ADMIN_CHAT_ID=message.chat.id
    g=get_gold()
    rg=calc_rsi(prices_history) if len(prices_history)>2 else 50.0
    txt=message.text
    if txt.startswith('/id'):
        bot.reply_to(message, "Your ID: "+str(message.from_user.id)); return
    if txt.startswith('/testsignal'):
        bot.reply_to(message, "🔍 Creating TEST GOLD signal... check DM!")
        request_approval("GOLD", g, 28.5, "BUY"); return
    if txt.startswith('/active'):
        if len(active_signals)==0:
            bot.reply_to(message, "📭 No active GOLD signals - Waiting for RSI <30 or >70\nBot analyzing every 60s... Gold is OPEN ✅")
        else:
            t="📊 ACTIVE GOLD ("+str(len(active_signals))+"):\n"
            for s in active_signals:
                t+=s["symbol"]+" "+s["action"]+" Entry $"+str(round(s["entry"],2))+"\n"
            bot.reply_to(message,t)
        return
    if txt.startswith('/signal') or txt.startswith('/price'):
        bot.reply_to(message, f"🔍 GOLD ANALYSIS 👑\n\n🥇 GOLD: ${round(g,2)} RSI: {round(rg,1)} OPEN ✅ 24/7\n\n⏳ Waiting for RSI <30 BUY or >70 SELL\nScanning every 60s AUTO...\nActive: {len(active_signals)}\n\nChannel: @KEVINTRAILBLAZE"); return
    bot.reply_to(message, f"👑 KEVIN GOLD ONLY V4 ✅\n\n🥇 GOLD: ${g} OPEN ✅\nRSI: {round(rg,1)}\n\nGOLD ONLY - BTC REMOVED\n\nCommands:\n/signal - Analyze gold\n/active - Check active\n/testsignal - Test\n/price /id\n\nBot AUTO sends itself every 60s!")

threading.Thread(target=signal_loop,daemon=True).start()

if __name__=="__main__":
    try:
        bot.remove_webhook()
        time.sleep(1)
        ext_url = os.getenv("RENDER_EXTERNAL_URL")
        if ext_url:
            bot.set_webhook(url=f"{ext_url}/{BOT_TOKEN}")
            print(f"Webhook set {ext_url}", flush=True)
    except Exception as e:
        print(f"Webhook err {e}", flush=True)
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
