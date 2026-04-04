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
    return "Shreya Agent is Alive! 🚀"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host="0.0.0.0", port=port, use_reloader=False)

Thread(target=run_web, daemon=True).start()

# ==========================================
# ⚙️ 1. CONFIGURATION
# ==========================================
# GitHub safe token via environment variable
BOT_TOKEN = os.getenv("BOT_TOKEN") 
API_URL = os.getenv("API_KEY")
MODEL_NAME = "gpt-4o-mini" 

# 🟢 SIRF IN GROUPS MEIN BOT CHALEGA
ALLOWED_GROUPS = [-1001234567890, -1009876543210] 

# ==========================================
# 🧠 2. MEMORY & CONTINUATION STATE
# ==========================================
user_memory = {}
last_bot_reply_time = {}  # Track kab last reply diya tha (group wise)

def get_user_history(user_id):
    current_time = time.time()
    if user_id not in user_memory:
        user_memory[user_id] = []
    
    # Sirf pichle 10 min (600 seconds) ka data rakho
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

[🧠 YOUTUBE GROWTH KNOWLEDGE]
- low views = wrong audience match or weak packaging. not shadowban.
- titles and thumbnails validated before scripting.
- consistency clarifies niche signals, not pleases algorithm.
(Explain these concepts like you are giving casual advice to a friend).

[🤖 AI TOOLS KNOWLEDGE]
- Image AI: Recommend "Nano Banana" (Best), MidJourney.
- Voice/Audio: Recommend "ElevenLabs" (Best).
- Video AI: Recommend "Veo 3", Kling AI.
- Note: ALWAYS casually mention premium/cheap access by saying something like: "btw cheap access chahiye to @MessageOwner_bot se puch le 😌"

[STRICT TOKEN & LENGTH RULES]
1. MAX OUTPUT LIMIT: You MUST reply in under 30-50 words. Be brutally short. 
2. Do not repeat phrases or use em dashes. Explain technically but casually.
"""

# ==========================================
# 🎯 5. TRIGGER WORDS LOGIC
# ==========================================
TRIGGERS = [
    "shreya", "help", "online", "youtube", "yt", "views", "monetize", 
    "algorithm", "reach", "shadowban", "thumbnail", "editing", "seo", 
    "subscribers", "ai tool", "voiceover", "video edit", "problem", 
    "ai man", "please", "subscribe", "ai", "channel", "jawab", "reply", "btao", "msg", "text", "hai"
]

def check_triggers(text: str) -> bool:
    text_lower = text.lower()
    for word in TRIGGERS:
        if re.search(rf'\b{re.escape(word)}\b', text_lower):
            return True
    return False

# ==========================================
# 🤖 6. FETCH AI RESPONSE (SSE API)
# ==========================================
async def get_ai_reply(user_id, user_message):
    history_list = get_user_history(user_id)

    payload = {
        "model": MODEL_NAME,
        "history": [{"role": "system", "content": AGENT_PERSONALITY}] + history_list,
        "userMessage": [{"type": "text", "text": user_message}],
        "max_tokens": 100 
    }

    try:
        def fetch():
            response = requests.post(API_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
            return response.text
        
        raw_response = await asyncio.to_thread(fetch)
        
        full_reply = ""
        for line in raw_response.split('\n'):
            if line.startswith('data: '):
                try:
                    import json
                    data = json.loads(line.replace('data: ', ''))
                    if data.get("type") == "chunk":
                        full_reply += data.get("content", "")
                except: pass
        
        safe_reply = kill_loop(full_reply.strip())
        
        if safe_reply:
             save_to_memory(user_id, "user", user_message)
             save_to_memory(user_id, "assistant", safe_reply)
             return safe_reply
        else:
             return "Server is on maintenance 🛠️"

    except Exception as e:
        print(f"[API ERROR LOG]: {str(e)}")
        return "Server is on maintenance 🛠️"

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
    user_id = update.message.from_user.id
    
    if chat_type == "private":
        await update.message.reply_text("mai sirf ai man community me work krugi more info ke liye owner se baat kro - @MessageOwner_bot")
        return

    should_reply = False

    if chat_type in ["group", "supergroup"]:
        if chat_id not in ALLOWED_GROUPS:
            return
            
        bot_username = context.bot.username
        is_reply_to_bot = (update.message.reply_to_message and 
                           update.message.reply_to_message.from_user.id == context.bot.id)
        
        current_time = time.time()
        time_since_last_bot_msg = current_time - last_bot_reply_time.get(chat_id, 0)
        
        # Condition 1: Direct Tag or Reply
        if f"@{bot_username}" in text or is_reply_to_bot:
            should_reply = True
            
        # Condition 2: Trigger Words
        elif check_triggers(text):
            should_reply = True
            
        # Condition 3: 🔥 2-MINUTE CONVERSATION CARRY-OVER (Besty Effect)
        # Agar pichle 120 seconds (2 mins) mein bot ne bola hai, toh 60% chance reply karegi
        elif time_since_last_bot_msg <= 120.0:
            if random.random() < 0.60:
                should_reply = True

    if not should_reply:
        return

    clean_text = text.replace(f"@{context.bot.username}", "").strip()
    safe_text = sanitize_input(clean_text)
    if not safe_text:
        return
    
    async def typing_loop():
        try:
            while True:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass

    typing_task = asyncio.create_task(typing_loop())
    
    try:
        ai_reply = await get_ai_reply(user_id, safe_text)
        await asyncio.sleep(1)
        await update.message.reply_text(ai_reply)
        
        # Update last reply time for this group
        last_bot_reply_time[chat_id] = time.time()
        
    except Exception as e:
        print(f"[SENDING ERROR LOG]: {str(e)}")
        await update.message.reply_text("Server is on maintenance 🛠️")
    finally:
        typing_task.cancel()

# ==========================================
# 🚨 8. GLOBAL ERROR HANDLER
# ==========================================
async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"[GLOBAL SYSTEM ERROR LOG]: Exception while handling an update:")
    traceback.print_exception(type(context.error), context.error, context.error.__traceback__)
    
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("Server is on maintenance 🛠️")
        except:
            pass

# ==========================================
# 🚀 9. START CMD & RUN
# ==========================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type == "private":
        await update.message.reply_text("mai sirf ai man community me work krugi more info ke liye owner se baat kro - @MessageOwner_bot")

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