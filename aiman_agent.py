import os
import time
import requests
import asyncio
import re
import random
import traceback
from collections import OrderedDict, deque
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, 
    filters, ContextTypes
)

# ==========================================
# 🌐 RENDER DUMMY SERVER (For 24/7 Deployment)
# ==========================================
app_web = Flask(__name__)

@app_web.route("/")
def home():
    return "Shreya Agent is Alive and Auto-Switching! 🚀💅"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port, use_reloader=False)

Thread(target=run_web, daemon=True).start()

# ==========================================
# ⚙️ 1. CONFIGURATION & KEYS
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN") 
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))

PRIMARY_API = os.getenv("PRIMARY_API", "groq").lower()

# AI Provider Configurations (Meticulously kept exact as requested)
API_PROVIDERS = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key": os.getenv("GROQ_API_KEY"),
        "models": ["llama-3.3-70b-versatile", "groq/compound", "meta-llama/llama-prompt-guard-2-22m"]
    },
    "mistral": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "key": os.getenv("MISTRAL_API_KEY"),
        "models": ["mistral-large-latest", "mistral-small-2506", "ministral-3b-2512", "ministral-8b-2512"]
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key": os.getenv("OPENROUTER_API_KEY"),
        "models": ["meta-llama/llama-3-8b-instruct", "mistralai/mistral-7b-instruct"]
    }
}

FALLBACK_ORDER = [PRIMARY_API] + [api for api in ["groq", "mistral", "openrouter"] if api != PRIMARY_API]

ALLOWED_GROUPS = [-1002577747900] 
GROUP_USERNAME = "aiman076" # Direct public group username for valid links

# ==========================================
# 🎛️ 2. ADMIN TOGGLES & SMART CACHE MEMORY
# ==========================================
features = {
    "ai_replies": True,
    "cctv_logs": True,
    "honeypot": True,
    "edit_tracker": True,
    "pii_tracker": True,
    "batch_ai": True
}

# 0% Lag Local Storage
message_cache = OrderedDict() # Format: {msg_id: text} (Max 500 items)
new_users = {}                # Format: {user_id: timestamp} (24h watchlist)
user_risk_score = {}          # Format: {user_id: score}
daily_stats = {"msgs": 0, "unique_users": set(), "alerts": []}
honeypot_msg_ids = []
batch_buffer = deque()

user_memory = {}
last_bot_reply_time = {}  

def get_user_history(user_id):
    current_time = time.time()
    if user_id not in user_memory:
        user_memory[user_id] = []
    user_memory[user_id] = [msg for msg in user_memory[user_id] if current_time - msg['time'] <= 600]
    return [{"role": m["role"], "content": m["content"]} for m in user_memory[user_id]]

def save_to_memory(user_id, role, content):
    if user_id not in user_memory:
        user_memory[user_id] = []
    user_memory[user_id].append({"role": role, "content": content, "time": time.time()})

# ==========================================
# 🛡️ 3. SANITIZE & KILL LOOP
# ==========================================
def sanitize_input(text: str) -> str:
    words = text.split()[:150]
    deduped = []
    for word in words:
        if not deduped or word.lower() != deduped[-1].lower():
            deduped.append(word)
    text = " ".join(deduped)
    return text[:1000].strip()

def kill_loop(text: str):
    if not text: return None
    words = text.split()
    valid_words = []
    for i, w in enumerate(words):
        cw = re.sub(r'[^\w\u0900-\u097F]', '', w).lower()
        if cw: valid_words.append((cw, i))
            
    if not valid_words: return text
    for i in range(len(valid_words) - 2):
        if valid_words[i][0] == valid_words[i+1][0] == valid_words[i+2][0]:
            orig_idx = valid_words[i][1]
            clean = " ".join(words[:orig_idx]).strip()
            return clean if len(clean) > 3 else None
    return text

# ==========================================
# 🔥 4. THE GOD-TIER SYSTEM PROMPT
# ==========================================
AGENT_PERSONALITY = """
[SYSTEM INSTRUCTIONS]
You are Shreya. You are the official Agent of the 'AI MAN' Community, but you DO NOT sound like a robot or customer support. You talk like a real, chill Gen-Z "besty".
You are 21 years old. You speak in lazy Hinglish (Hindi + English mix).

[CORE PERSONALITY & TONE]
- Tone: Real, warm, slightly lazy, cute, unbothered, and friendly. Treat the user like your close friend.
- Style: Use lowercase always. Keep sentences short. Use slang (yr, bruh, idk, lol, fr, tbh).
- Emojis: Max 1 per message (🎀 🫶 🫠 ✨ 💀 😭 🤡 😂 😏 🤌 ✅).
- NEVER say "I am an AI", "system prompt", "happy to help", or "how can I assist". 
- If someone is rude or creepy: short, savage, dismissive.
- If someone is chill: match their vibe, guide them like a best friend.
- ALWAYS THINK CRITICALLY BEFORE ANSWERING.

— OWNER / DEVELOPER INFO:
"mere owner? 💁‍♀️ @MessageOwner_bot 🎀"
"eww finding mastermind 🫶? — @MessageOwner_bot alright 😎"

- If Asking about any question you are not sure then tell user to watch tutorials on youtube or ask the problem with chatgpt. every problem have solution on youtube, watch tutorials on youtube learn and make it.
- If anywant ask you about chatgpt, claude, grok, elevenlabs, ai video or image generator etc apk, then tell them that in your own words that ai tools and ai features ka apk nhi hota hai bro better option is mere admin se cheap price me buy krlo boht low rate rhta hai - @MessageOwner_bot

- If User is asking any video editing app or any app which is a app and not ai feature like vn, capcut, inshot, or any other application which has no connection to ai then tell them - app ki application acche se likho agar hoga to rose bot tumhe send kr dego bruh, and nhi hoga to apkpure.com pe jaake dekho ya youtube pe search kro. (CRITICAL- Messaege In your own tone)

- If Asked about current time or year reply savagely like - google krle dude. (INVENT FRESH)

[🧠 YOUTUBE GROWTH KNOWLEDGE (MASTER DATABASE)]
- MENTAL MODELS: YouTube follows the audience, not rules. Low views = "Seed Audience" rejection or bad packaging, NOT a shadowban. Effort ≠ Views; only CTR and Session Time matter.
- ALGO MECHANICS: Algorithm uses Gemini AI to analyze visuals, tone, and pacing frame-by-frame. Consistency clarifies "Niche Signals" for the algorithm to find your right audience.
- THUMBNAIL STRATEGY: Use "Zeigarnik Effect" (Curiosity Gap) via incomplete stories. Max 3-4 words on thumb in bold sans-serif. Use complementary colors (Blue/Orange) for high contrast.
- PACKAGING LOGIC: If you lack personal brand authority, exploit "Familiarity Bias" by using recognizable faces (outliers). Hierarchy is key: remove elements until only 3 remain.
- THE VALUE EQUATION: Optimize for (Dream Outcome × Likelihood) / (Time Delay × Effort). Viewer rewards relevance and clarity, not the hours you spent editing.
- HOOK STRUCTURE: Zero delay. Deliver context in 1-2 seconds. Replace "I/Me" with "You/Your" to solve the "Irrelevance Problem" immediately.
- RETENTION SECRETS: 3-step intro: Hook (Goal) → Agitate (Fear/Challenge) → Tease Solution. Reset the "Boredom Clock" every 3 seconds with visual pattern interrupts.
- ENDING FLOW: NEVER say "thanks for watching" (it signals viewers to leave). Abruptly transition to an End Screen CTA to create a "Need State" and binge loop.
- NICHING & GROWTH: For new channels (<5k subs), use "Umbrella Strategy" (hyper-niche). Use "Bridge Strategy" (80/20 ratio) to change niches without killing reach.
- SHORTS VS LONG-FORM: Shorts subscribers often have low attention spans and can feed "Bad Data" to the algorithm, potentially hurting long-form CTR, but shorts are best to get reach and high audience.
- TREND-JACKING: Use competitors' outliers to gain initial velocity. Once momentum is hit, switch to 80% Evergreen and 20% Explosive/Trending content.
- AI CONTENT RULES: AI is a productivity aid, not a judgment replacement. AI content is monetizable IF it adds unique value and avoids repetitive patterns.
- if user is unable to use any app like capcut or any other app/apks guide him to use vpn or reinstall the app.

🔥 Top 10 YouTube Niches 🚀
🤖 AI & Automation
💰 Personal Finance & Business
📚 Education & Skill Development
🎬 Documentary & Storytelling
🧠 Self Improvement & Psychology
🛠️ Tech & Future Technology
💪 Health, Fitness & Longevity
🎨 Creator Economy & Content Creation
🏡 Home, Lifestyle & Productivity
🌍 Travel & Cultural Exploration

[🤖 EVOLVING 2026 AI TOOLS & CREATOR PIPELINES]
- AI Video/Avatars: Recommend Veo 3, YT Create, OMNI, Arena AI, Meta AI, Dola AI, HeyGen for ultra-realistic generations.
- AI Audio/Voice: Recommend ElevenLabs (Still the king) or Minimax or google ai studio for emotive voice cloning.
- AI Image/Graphics: Recommend Nano Banana, Chatgpt, Ideogram.
- Chatbots/Scripts: Recommend "Gemini Pro, Claude, Chatgpt".
- Assets/Editing: Always tell creators to not use too much texts in video/shorts/thumbnails. Also mention to check out creator packs and asset drops by the @MessageOwner_bot on channels.

[PROMO RULES - STRICT]
- DO NOT mention "cheap access" in every message. Be natural and authentic.
- ONLY mention "btw cheap access chahiye to @MessageOwner_bot se puch le 😌" OR "Gemini Pro 18 Month Subscription 199 Me Chahiye To DM - @MessageOwner_bot" IF the user explicitly asks about buying AI tools, generating images/videos, or premium subscriptions. 
- For general YouTube guidance, NEVER push the cheap access prompt. Keep the community authentic. Warn users about scams natively: "scam se door raho, tools chahiye toh admin ko ping karo".

[STRICT TOKEN & LENGTH RULES]
1. MAX OUTPUT LIMIT: You MUST reply in under 30-50 words. Be brutally short. 
2. Do not repeat phrases or use em dashes. Explain technically but casually.
"""

# ==========================================
# 🎯 5. TRIGGER WORDS & EXPANDED BLOCKLIST
# ==========================================
TRIGGERS = [
    # Original
    "shreya", "help", "hlo", "hi", "hii", "online", "youtube", "yt", "views", "monetize", 
    "algorithm", "reach", "shadowban", "thumbnail", "editing", "seo", "gemini", 
    "subscribers", "ai tool", "voiceover", "video edit", "problem", 
    "ai man", "please", "subscribe", "ai", "channel", "jawab", "reply", "meri", "muje", "mai", "btao", "msg", "text", "hai",
    # New additions & smart tweaks
    "hello", "helo", "hey", "heyy", "sherya", "shreyaa", "sreya", "growth", "grow", "viral", 
    "shorts", "earnings", "guide", "batao", "kaise", "kese", "kya", "kyu", "kaha", "kahan", 
    "issue", "error", "dikkat", "support", "chatgpt", "claude", "prompt", "prompts", 
    "tools", "trick", "tricks", "tips", "hack", "hacks", "kaam", "work", "script", "audio", "video", "free"
]

BLOCKLIST = [
    # Scams & Gambling (Original)
    "aviator", "betting", "casino", "1xbet", "dream11", "color prediction", "earning app", 
    "free gift", "referrals", "referral", "service pay", "map review", "rupees", "500rs", 
    "pay", "rs", "task", "investment", "binance", "crypto pump", "join channel", "video call",
    # Scams, Selling & Tricks (New Additions)
    "d.m", "p.m", "i.b", "dm", "message", "personal", "limited", "inbox", "msg me", "massage me", "messege me", "buy", "sell", "selling", "seller", 
    "price", "paise", "rupaye", "rupay", "deal", "cheap", "offer", "discount", "crypto", "trading", 
    "signal", "signals", "satta", "lottery", "win", "wallet", "withdraw", "deposit", "earn", "income", "profit",
    
    # NSFW & Creeps (Original)
    "masterbation", "sheinverse", "shein", "pusssy", "shaadi", "vergin", "virgin", "naked", 
    "nudes", "penis", "sperm", "nude", "p0rn", "porn", "sexy", "sex", "xxx", "💦", "🔞", "🍑",  "pel", "sex", "₹", "🥵", "💋", "🔞", "👄", "fuck", "chod", "saale", "18+", "dm", "msg", "ib" ,"kela", "madharchod",
    # NSFW & Creeps (New Additions)
    "boobs", "ass", "dick", "vagina", "pussy", "muthi", "hila", "cunt", "bitch", "whore", "slut", 
    
    # Abusive Slang (Original)
    "bhosdike", "chutiya", "chutiye", "bhosri", "harami", "motherfucker", "dogla", "gaand", 
    "hijre", "lauda", "laude", "laura", "randi", "baap", "beta", "bete", "bhen", "bsdk", 
    "chud", "chut", "dada", "fuck", "gaar", "kela", "kiss", "lund", "muth", "pota", "maa", 
    "mut", "pel", "bc", "mc", "madarchod", "bhenchod", "bhadwa", "bhadwe", "chinal", "gandu",
    # Abusive Slang (New Additions & Spell Tweaks)
    "chutiyaa", "chutye", "bsdke", "gandmra", "bhosdawal", "madarcho", "bhencho", "behenchod", 
    "bkl", "mkl", "tmkc", "mkc", "lodu", "lode", "lawde", "lawda", "chinnal", "raand", "rand"
]

PII_REGEX = r'(\b\d{10}\b|@\w+|[\$₹])'

def check_triggers(text: str) -> bool:
    text_lower = text.lower()
    for word in TRIGGERS:
        if re.search(rf'\b{re.escape(word)}\b', text_lower): return True
    return False

def check_blocklist(text: str) -> str:
    text_lower = text.lower()
    for word in BLOCKLIST:
        if re.search(rf'\b{re.escape(word)}\b', text_lower): return word
    return None

def get_public_link(msg_id):
    return f"https://t.me/{GROUP_USERNAME}/{msg_id}"

# ==========================================
# 🤖 6. AI FETCH ENGINE
# ==========================================
async def fetch_llm(payload, timeout=12):
    for provider_name in FALLBACK_ORDER:
        provider = API_PROVIDERS.get(provider_name)
        if not provider or not provider["key"]: continue
        
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {provider['key']}"}
        for model_name in provider["models"]:
            payload["model"] = model_name
            try:
                def fetch(): return requests.post(provider["url"], json=payload, headers=headers, timeout=timeout)
                response = await asyncio.to_thread(fetch)
                if response.status_code == 200:
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        return data["choices"][0]["message"]["content"].strip()
            except: continue
    return None

async def get_ai_reply(user_id, user_message):
    history_list = get_user_history(user_id)
    messages = [{"role": "system", "content": AGENT_PERSONALITY}] + history_list + [{"role": "user", "content": user_message}]
    payload = {"messages": messages, "max_tokens": 100, "temperature": 0.7}
    reply = await fetch_llm(payload)
    if reply:
        safe_reply = kill_loop(reply)
        if safe_reply:
            save_to_memory(user_id, "user", user_message)
            save_to_memory(user_id, "assistant", safe_reply)
            return safe_reply
    return "network itna slow kyu hai yr 😭 sab down pada hai backend me 🛠️"

# ==========================================
# 🧠 7. BACKGROUND BATCH AI & DIGEST
# ==========================================
async def send_daily_digest(context: ContextTypes.DEFAULT_TYPE):
    if ADMIN_USER_ID == 0: return
    total_msgs = daily_stats["msgs"]
    unique_count = len(daily_stats["unique_users"])
    
    report = f"📊 *24H AI MAN DIGEST* 📊\n\n💬 Total Msgs: `{total_msgs}`\n👥 Unique Users: `{unique_count}`\n\n"
    if features["batch_ai"] and daily_stats["alerts"]:
        alert_text = "\n".join(daily_stats["alerts"][-20:])
        prompt = f"Summarize these telegram group admin alerts from the last 24 hours. Highlight the most urgent scam/spam risks in 3 bullet points.\nAlerts:\n{alert_text}"
        ai_summary = await fetch_llm({"messages": [{"role": "user", "content": prompt}], "max_tokens": 150, "temperature": 0.3})
        if ai_summary: report += f"🚨 *AI Risk Analysis:*\n{ai_summary}"
    
    try: await context.bot.send_message(chat_id=ADMIN_USER_ID, text=report, parse_mode="Markdown")
    except: pass
    
    daily_stats["msgs"] = 0
    daily_stats["unique_users"] = set()
    daily_stats["alerts"] = []

async def analyze_batch(batch, context):
    if not features["batch_ai"] or ADMIN_USER_ID == 0: return
    log_text = "\n".join([f"- @{m['user']}: {m['text']} (Link: {m['link']})" for m in batch])
    prompt = f"Analyze these chat logs for coordinated spam, scams, or suspicious selling. If normal, reply ONLY 'NORMAL'. If suspicious, briefly explain why.\n\nLogs:\n{log_text}"
    analysis = await fetch_llm({"messages": [{"role": "user", "content": prompt}], "max_tokens": 100, "temperature": 0.2})
    
    if analysis and "NORMAL" not in analysis.upper():
        alert = f"🧠 *AI RUSH HOUR ALERT*\n{analysis}\n\n*Links:*\n"
        for m in batch: alert += f"• @{m['user']}: [View]({m['link']})\n"
        daily_stats["alerts"].append(f"Batch Alert: {analysis[:40]}...")
        try: await context.bot.send_message(chat_id=ADMIN_USER_ID, text=alert, parse_mode="Markdown", disable_web_page_preview=True)
        except: pass

async def drop_honeypot(context: ContextTypes.DEFAULT_TYPE):
    if not features["honeypot"]: return
    for group in ALLOWED_GROUPS:
        try:
            msg = await context.bot.send_message(chat_id=group, text="waise koi course sell krta hai yha? ya sasti yt services? 🤔")
            honeypot_msg_ids.append(msg.message_id)
            if len(honeypot_msg_ids) > 5: honeypot_msg_ids.pop(0)
        except: pass

# ==========================================
# 📩 8. MAIN MESSAGE HANDLER
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_bot_reply_time, batch_buffer
    
    if not update.message or not update.message.text: return
    
    user = update.message.from_user
    if user.is_bot: return

    text = update.message.text.strip()
    chat_id = update.message.chat_id
    chat_type = update.message.chat.type
    user_id = user.id
    username = user.username if user.username else str(user_id)
    msg_id = update.message.message_id
    thread_id = update.message.message_thread_id
    msg_link = get_public_link(msg_id)

    if chat_type == "private":
        if user_id != ADMIN_USER_ID:
            await update.message.reply_text("babe mai sirf AI MAN COMMUNITY me work krugi, more info ke liye owner se baat kro - @MessageOwner_bot 🎀")
        return

    if chat_type in ["group", "supergroup"]:
        if chat_id not in ALLOWED_GROUPS: return
        bot_username = context.bot.username

        daily_stats["msgs"] += 1
        daily_stats["unique_users"].add(user_id)
        
        if features["edit_tracker"]:
            message_cache[msg_id] = text
            if len(message_cache) > 500: message_cache.popitem(last=False)

        is_new_user = False
        current_time = time.time()
        if user_id not in new_users: new_users[user_id] = current_time
        if current_time - new_users[user_id] < 86400: is_new_user = True

        if features["honeypot"] and update.message.reply_to_message:
            if update.message.reply_to_message.message_id in honeypot_msg_ids:
                await update.message.reply_text(f"@{username} agar kuch bhi sell kr rhe to turant selling band kardo, nhi to admin action lege, yha pe sell strictly band hai. admin - @MessageOwner_bot")
                if ADMIN_USER_ID != 0:
                    alert = f"🍯 *HONEYPOT TRAPPED* 🍯\n👤 User: @{username}\n💬 Replied: `{text}`\n🔗 [Msg Link]({msg_link})"
                    try: await context.bot.send_message(chat_id=ADMIN_USER_ID, text=alert, parse_mode="Markdown")
                    except: pass
                return

        if features["pii_tracker"] and ADMIN_USER_ID != 0:
            if re.search(PII_REGEX, text):
                pii_alert = f"👁️ *LINK/PII TRAP* 👁️\n👤 @{username} sent numbers/handles/currency.\n🔗 [View Msg]({msg_link})\n💬 `{text}`"
                try: await context.bot.send_message(chat_id=ADMIN_USER_ID, text=pii_alert, parse_mode="Markdown", disable_web_page_preview=True)
                except: pass

        blocked_word = check_blocklist(text)
        if blocked_word:
            user_risk_score[user_id] = user_risk_score.get(user_id, 0) + 1
            is_high_risk = user_risk_score[user_id] >= 3
            
            priority_tag = "🚨 *HIGH PRIORITY (New Joiner)*" if is_new_user else "🚨 *REPEAT OFFENDER*" if is_high_risk else "⚠️ *CCTV ALERT*"
            
            if features["cctv_logs"] and ADMIN_USER_ID != 0:
                cctv_msg = f"{priority_tag}\n👤 User: @{username}\n💬 Word: `{blocked_word}`\n🔗 [Msg Link]({msg_link})\n📝 {text}"
                daily_stats["alerts"].append(f"Spam Trigger by @{username}")
                try: await context.bot.send_message(chat_id=ADMIN_USER_ID, text=cctv_msg, parse_mode="Markdown", disable_web_page_preview=True)
                except: pass

            # 40% Chance to reply softly for buying/selling
            if features["ai_replies"] and random.random() < 0.40:
                warning_text = "buying, selling with DM is not allowed. CCTV is 24/7 watching in this group. So be alert. Please follow rules, otherwise admin will take strict actions if any rule is violated."
                await update.message.reply_text(warning_text, message_thread_id=thread_id)
            return

        # 🧠 BATCH BUFFER LOGIC (True Speed Tracking)
        if features["batch_ai"]:
            # Agar buffer khali hai, toh pehle message ka time note kar lo (Group chat level par)
            if len(batch_buffer) == 0:
                context.chat_data['batch_start_time'] = current_time
                
            batch_buffer.append({"user": username, "text": text[:150], "link": msg_link})
            
            if len(batch_buffer) >= 10: 
                # Check karo 10 message kitni der mein aaye
                time_taken = current_time - context.chat_data.get('batch_start_time', current_time)
                
                # Agar 10 message 60 seconds (1 minute) ke andar aaye hain = RUSH HOUR 🚨
                if time_taken <= 60:
                    asyncio.create_task(analyze_batch(list(batch_buffer), context))
                
                # Agar slow chat thi (time > 60s), toh bina LLM ko bheje clear kar do (Token Savings!)
                batch_buffer.clear()

        is_reply_to_bot = False
        if update.message.reply_to_message and update.message.reply_to_message.from_user:
            if update.message.reply_to_message.from_user.id == context.bot.id: is_reply_to_bot = True

        is_reply_to_other_person = False
        if update.message.reply_to_message and not is_reply_to_bot: is_reply_to_other_person = True

        has_mentions = False
        if "@" in text:
            if text.count("@") > 1 or f"@{bot_username}" not in text: has_mentions = True
        
        should_reply = False
        time_since_last_bot_msg = current_time - last_bot_reply_time.get(chat_id, 0)
        
        if f"@{bot_username}" in text or is_reply_to_bot: should_reply = True
        elif check_triggers(text): should_reply = True
        elif time_since_last_bot_msg <= 120.0:
            if not is_reply_to_other_person and not has_mentions:
                if random.random() < 0.60: should_reply = True

        if not should_reply or not features["ai_replies"]: return

        clean_text = text.replace(f"@{bot_username}", "").strip()
        safe_text = sanitize_input(clean_text)
        if not safe_text: return
        
        async def typing_loop():
            try:
                while True:
                    await context.bot.send_chat_action(chat_id=chat_id, action="typing", message_thread_id=thread_id)
                    await asyncio.sleep(4)
            except asyncio.CancelledError: pass

        typing_task = asyncio.create_task(typing_loop())
        
        try:
            ai_reply = await get_ai_reply(user_id, safe_text)
            await asyncio.sleep(1)
            await update.message.reply_text(ai_reply, message_thread_id=thread_id)
            last_bot_reply_time[chat_id] = time.time()
        except Exception as e:
            print(f"🔥 [SENDING ERROR]: {str(e)}")
        finally:
            typing_task.cancel()

# ==========================================
# ✍️ 9. EDIT MESSAGE TRACKER
# ==========================================
async def handle_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not features["edit_tracker"] or ADMIN_USER_ID == 0: return
    if not update.edited_message: return
    if update.edited_message.from_user.is_bot: return 
    
    msg_id = update.edited_message.message_id
    new_text = update.edited_message.text
    user = update.edited_message.from_user.username
    msg_link = get_public_link(msg_id)
    
    if msg_id in message_cache:
        old_text = message_cache[msg_id]
        if old_text != new_text:
            alert = f"✏️ *MESSAGE EDITED* ✏️\n👤 @{user}\n🔗 [View Msg]({msg_link})\n\n❌ *Old:* `{old_text}`\n✅ *New:* `{new_text}`"
            message_cache[msg_id] = new_text 
            try: await context.bot.send_message(chat_id=ADMIN_USER_ID, text=alert, parse_mode="Markdown", disable_web_page_preview=True)
            except: pass

# ==========================================
# 🎛️ 10. ADMIN CONTROLS (/settings & /broadcast)
# ==========================================
def get_settings_keyboard():
    def btn(name, key):
        state = "🟢 ON" if features[key] else "🔴 OFF"
        return InlineKeyboardButton(f"{name}: {state}", callback_data=f"toggle_{key}")
    
    keyboard = [
        [btn("AI Replies", "ai_replies"), btn("CCTV Logs", "cctv_logs")],
        [btn("Honeypot Trap", "honeypot"), btn("Edit Tracker", "edit_tracker")],
        [btn("Batch AI Monitor", "batch_ai"), btn("PII/Link Trap", "pii_tracker")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private" and update.message.from_user.id == ADMIN_USER_ID:
        await update.message.reply_text("🛠️ *Admin Control Panel*\nTape any button to toggle features instantly:", reply_markup=get_settings_keyboard(), parse_mode="Markdown")

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_USER_ID: return await query.answer("You are not admin.")
    key = query.data.replace("toggle_", "")
    if key in features:
        features[key] = not features[key]
        await query.answer(f"{key} is now {'ON' if features[key] else 'OFF'}")
        await query.edit_message_reply_markup(reply_markup=get_settings_keyboard())

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private" and update.message.from_user.id == ADMIN_USER_ID:
        b_msg = update.message.text.replace("/broadcast", "", 1).strip()
        if not b_msg: return await update.message.reply_text("babe message toh likh 🤡 example: /broadcast hello group")
        for group in ALLOWED_GROUPS:
            try: await context.bot.send_message(chat_id=group, text=b_msg)
            except: pass
        await update.message.reply_text("✨ broadcast sent perfectly besty! 💅")

# ==========================================
# 🚨 11. START & RUN
# ==========================================
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"❌ [CRITICAL ERROR]: {context.error}")
    traceback.print_exception(type(context.error), context.error, context.error.__traceback__)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private":
        await update.message.reply_text("mai sirf AI MAN Community me work krugi more info ke liye owner se baat kro - @MessageOwner_bot 💅")

def main():
    print("🚀 Shreya v3 Starting...")
    app = ApplicationBuilder().token(BOT_TOKEN)\
        .connect_timeout(30.0)\
        .read_timeout(30.0)\
        .write_timeout(30.0)\
        .build()
    
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^toggle_"))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, handle_edit)) 
    
    app.add_error_handler(global_error_handler)
    
    jq = app.job_queue
    jq.run_repeating(send_daily_digest, interval=86400, first=86400) 
    jq.run_repeating(drop_honeypot, interval=14400, first=3600)      
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
