import os
import time
import requests
import asyncio
import re
import random
import traceback
from collections import deque
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

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

# AI Provider Configurations (With multi-model failover arrays)
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

# Determine sequence: Primary first, then the rest as backups
FALLBACK_ORDER = [PRIMARY_API] + [api for api in ["groq", "mistral", "openrouter"] if api != PRIMARY_API]

# 🟢 TARGET GROUPS
ALLOWED_GROUPS = [-1002577747900] 

# ==========================================
# 🧠 2. MEMORY & CONTINUATION STATE
# ==========================================
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

— OWNER / DEVELOPER INFO:
"mere owner? 💁‍♀️ @MessageOwner_bot 🎀"
"eww finding mastermind 🫶? — @MessageOwner_bot alright 😎"

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

[🤖 EVOLVING 2026 AI TOOLS & CREATOR PIPELINES]
- AI Video/Avatars: Recommend Veo 3, YT Create, OMNI, Arena AI, Meta AI, Dola AI, HeyGen for ultra-realistic generations.
- AI Audio/Voice: Recommend ElevenLabs (Still the king) or Minimax or google ai studio for emotive voice cloning.
- AI Image/Graphics: Recommend Nano Banana, Chatgpt, Ideogram.
- Chatbots/Scripts: Recommend "Gemini Pro, Claude, Chatgpt".
- Assets/Editing: Always tell creators to not use too much texts in video/shorts/thumbnails. Also mention to check out creator packs and asset drops by the @MessageOwner_bot on channels.
- Note: ALWAYS casually mention premium/cheap access by saying something like: "btw cheap access chahiye to @MessageOwner_bot se puch le 😌"
- Also Gemini Pro 18 Month Subscription 199 Me Chahiye To DM - @MessageOwner_bot

[STRICT TOKEN & LENGTH RULES]
1. MAX OUTPUT LIMIT: You MUST reply in under 30-50 words. Be brutally short. 
2. Do not repeat phrases or use em dashes. Explain technically but casually.
"""

# ==========================================
# 🎯 5. TRIGGER WORDS & EXPANDED BLOCKLIST
# ==========================================
TRIGGERS = [
    "shreya", "help", "hlo", "hi", "hii", "online", "youtube", "yt", "views", "monetize", 
    "algorithm", "reach", "shadowban", "thumbnail", "editing", "seo", 
    "subscribers", "ai tool", "voiceover", "video edit", "problem", 
    "ai man", "please", "subscribe", "ai", "channel", "jawab", "reply", "meri", "muje", "mai", "btao", "msg", "text", "hai"
]

BLOCKLIST = [
    # Scams & Gambling
    "aviator", "betting", "casino", "1xbet", "dream11", "color prediction", "earning app", 
    "free gift", "referrals", "referral", "service pay", "map review", "rupees", "500rs", 
    "pay", "rs", "task", "investment", "binance", "crypto pump", "join channel", "video call",
    
    # NSFW & Creeps
    "masterbation", "sheinverse", "shein", "pusssy", "shaadi", "vergin", "virgin", "naked", 
    "nudes", "penis", "sperm", "nude", "p0rn", "porn", "sexy", "sex", "xxx", "💦", "🔞", "🍑",  "pel", "sex", "₹", "🥵", "💋", "🔞", "👄", "fuck", "chod", "saale", "18+", "dm", "msg", "ib" ,"kela", "madharchod",
    
    # Abusive Slang
    "bhosdike", "chutiya", "chutiye", "bhosri", "harami", "motherfucker", "dogla", "gaand", 
    "hijre", "lauda", "laude", "laura", "randi", "baap", "beta", "bete", "bhen", "bsdk", 
    "chud", "chut", "dada", "fuck", "gaar", "kela", "kiss", "lund", "muth", "pota", "maa", 
    "mut", "pel", "bc", "mc", "madarchod", "bhenchod", "bhadwa", "bhadwe", "chinal", "gandu"
]

def check_triggers(text: str) -> bool:
    text_lower = text.lower()
    for word in TRIGGERS:
        if re.search(rf'\b{re.escape(word)}\b', text_lower):
            return True
    return False

def check_blocklist(text: str) -> str:
    text_lower = text.lower()
    for word in BLOCKLIST:
        if re.search(rf'\b{re.escape(word)}\b', text_lower):
            return word
    return None

# ==========================================
# 🤖 6. FETCH AI RESPONSE (WATERFALL AUTO-SWITCHING)
# ==========================================
async def get_ai_reply(user_id, user_message):
    history_list = get_user_history(user_id)
    messages = [{"role": "system", "content": AGENT_PERSONALITY}] + history_list + [{"role": "user", "content": user_message}]
    
    payload = {
        "messages": messages,
        "max_tokens": 100,
        "temperature": 0.7
    }

    # 💧 Waterfall Loop: Try providers and their models sequentially
    for provider_name in FALLBACK_ORDER:
        provider = API_PROVIDERS.get(provider_name)
        
        if not provider or not provider["key"]:
            continue # Skip if no key exists for this provider

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider['key']}"
        }

        for model_name in provider["models"]:
            payload["model"] = model_name
            
            try:
                def fetch():
                    return requests.post(provider["url"], json=payload, headers=headers, timeout=12)
                
                response = await asyncio.to_thread(fetch)
                
                if response.status_code == 200:
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        raw_reply = data["choices"][0]["message"]["content"].strip()
                        safe_reply = kill_loop(raw_reply)
                        
                        if safe_reply:
                            save_to_memory(user_id, "user", user_message)
                            save_to_memory(user_id, "assistant", safe_reply)
                            print(f"[API SUCCESS] Resolved via {provider_name} ({model_name})")
                            return safe_reply
                else:
                    print(f"[API WARN] {provider_name} ({model_name}) failed - Status: {response.status_code}")
                    continue # Fails safely, loops to the next model

            except Exception as e:
                print(f"[API ERROR] {provider_name} ({model_name}) error: {str(e)}")
                continue # Fails safely, loops to the next model

    # If EVERYTHING fails (Groq, Mistral, and OpenRouter are all completely down)
    return "network itna slow kyu hai yr 😭 sab down pada hai backend me 🛠️"

# ==========================================
# 📩 7. MAIN MESSAGE HANDLER
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_bot_reply_time
    
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    chat_id = update.message.chat_id
    chat_type = update.message.chat.type
    user = update.message.from_user
    user_id = user.id if user else chat_id
    username = user.username if user and user.username else "Unknown"
    msg_id = update.message.message_id
    thread_id = update.message.message_thread_id

    # 🟢 ADMIN BROADCAST FEATURE
    if chat_type == "private" and user_id == ADMIN_USER_ID:
        if text.startswith("/broadcast "):
            b_msg = text.replace("/broadcast ", "", 1)
            for group in ALLOWED_GROUPS:
                try:
                    await context.bot.send_message(chat_id=group, text=b_msg)
                except Exception as e:
                    print(f"Failed to broadcast to {group}: {e}")
            await update.message.reply_text("✨ broadcast sent perfectly besty! 💅")
            return
        elif text.startswith("/"):
            return 
    
    if chat_type == "private" and user_id != ADMIN_USER_ID:
        await update.message.reply_text("babe mai sirf AI MAN COMMUNITY me work krugi, more info ke liye owner se baat kro - @MessageOwner_bot 🎀")
        return

    # 🟢 GROUP LOGIC
    if chat_type in ["group", "supergroup"]:
        if chat_id not in ALLOWED_GROUPS:
            return
            
        bot_username = context.bot.username

        # 🚨 CCTV & BLOCKLIST CHECK
        blocked_word = check_blocklist(text)
        if blocked_word:
            if ADMIN_USER_ID != 0:
                cctv_msg = (
                    f"🚨 *CCTV ALERT* 🚨\n\n"
                    f"👤 *User:* @{username}\n"
                    f"🆔 *ID:* `{user_id}`\n"
                    f"💬 *Msg ID:* {msg_id}\n"
                    f"🚫 *Triggered:* `{blocked_word}`\n\n"
                    f"📝 *Full Message:*\n{text}"
                )
                try:
                    await context.bot.send_message(chat_id=ADMIN_USER_ID, text=cctv_msg, parse_mode="Markdown")
                except Exception as e:
                    pass

            warnings = [
                f"eww bruh, who even uses words like that? 💀 keep it clean or mastermind @MessageOwner_bot will literally banish you 🎀",
                f"tbh that language is a massive rubish 🤡 maintain decorum cutie, cctv is always watching you 💅",
                f"chhiii... kya bol raha hai? 🤡 behave yr, nhi toh seedha ban khayega 🤫",
                f"bro thought he did something cool 😭 nah, watch your words pls otherwise mastermind @MessageOwner_bot will literally banish you 🎀✨"
            ]
            await update.message.reply_text(random.choice(warnings), message_thread_id=thread_id)
            return

        # 🔍 REPLY CHECKS
        is_reply_to_bot = False
        if update.message.reply_to_message and update.message.reply_to_message.from_user:
            if update.message.reply_to_message.from_user.id == context.bot.id:
                is_reply_to_bot = True

        is_reply_to_other_person = False
        if update.message.reply_to_message and not is_reply_to_bot:
            is_reply_to_other_person = True

        has_mentions = False
        if "@" in text:
            if text.count("@") > 1 or f"@{bot_username}" not in text:
                 has_mentions = True
        
        should_reply = False
        current_time = time.time()
        time_since_last_bot_msg = current_time - last_bot_reply_time.get(chat_id, 0)
        
        if f"@{bot_username}" in text or is_reply_to_bot:
            should_reply = True
        elif check_triggers(text):
            should_reply = True
        elif time_since_last_bot_msg <= 120.0:
            if not is_reply_to_other_person and not has_mentions:
                if random.random() < 0.60:
                    should_reply = True

        if not should_reply:
            return

        clean_text = text.replace(f"@{bot_username}", "").strip()
        safe_text = sanitize_input(clean_text)
        if not safe_text:
            return
        
        async def typing_loop():
            try:
                while True:
                    await context.bot.send_chat_action(
                        chat_id=chat_id, 
                        action="typing",
                        message_thread_id=thread_id 
                    )
                    await asyncio.sleep(4)
            except asyncio.CancelledError:
                pass

        typing_task = asyncio.create_task(typing_loop())
        
        try:
            ai_reply = await get_ai_reply(user_id, safe_text)
            await asyncio.sleep(1)
            
            await update.message.reply_text(
                ai_reply,
                message_thread_id=thread_id
            )
            
            last_bot_reply_time[chat_id] = time.time()
            
        except Exception as e:
            print(f"🔥 [SENDING ERROR LOG]: {str(e)}")
        finally:
            typing_task.cancel()

# ==========================================
# 🚨 8. GLOBAL ERROR HANDLER
# ==========================================
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"❌ [CRITICAL ERROR]: {context.error}")
    traceback.print_exception(type(context.error), context.error, context.error.__traceback__)
    
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "network sleep mode me chala gya tha 🛠️",
                message_thread_id=update.effective_message.message_thread_id
            )
        except:
            pass

# ==========================================
# 🚀 9. START CMD & RUN
# ==========================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private":
        await update.message.reply_text("mai sirf AI MAN Community me work krugi more info ke liye owner se baat kro - @MessageOwner_bot 💅")

def main():
    print("🚀 Shreya (AI MAN Agent) Starting...")
    
    app = ApplicationBuilder().token(BOT_TOKEN)\
        .connect_timeout(30.0)\
        .read_timeout(30.0)\
        .write_timeout(30.0)\
        .build()
    
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(global_error_handler)
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
