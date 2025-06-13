import os
import logging
from math import radians, cos, sin, asin, sqrt
import requests
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, LocationMessage,
    FlexSendMessage, PostbackEvent, TextSendMessage, PostbackAction, URIAction
)

# Load environment variables
load_dotenv()

# Initialize Flask and LINE API
app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# Ensure favorites file exists
def ensure_favorites_file():
    if not os.path.exists("favorites.txt"):
        with open("favorites.txt", "w", encoding="utf-8") as f:
            pass  # Create an empty file if it doesn't exist

# Ensure the favorites.txt file exists at the start
ensure_favorites_file()

user_locations = {}
last_toilet_by_user = {}
MAX_TOILETS_REPLY = 5

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Calculate the distance using the Haversine formula
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * asin(sqrt(a)) * 6371000

# Read toilets from text file
def query_local_toilets(lat, lon):
    toilets = []
    try:
        toilets_file_path = os.path.join(os.path.dirname(__file__), 'toilets.txt')
        with open(toilets_file_path, 'r', encoding='utf-8') as file:
            next(file)
            for line in file:
                data = line.strip().split(',')
                if len(data) != 13:
                    continue
                country, city, village, number, name, address, admin, latitude, longitude, grade, type2, type_, exec_, diaper = data
                try:
                    t_lat, t_lon = float(latitude), float(longitude)
                except ValueError:
                    continue
                dist = haversine(lat, lon, t_lat, t_lon)
                toilets.append({
                    "name": name or "無名稱", 
                    "lat": t_lat, 
                    "lon": t_lon,
                    "address": address or "", 
                    "distance": dist, 
                    "type": type_
                })
    except FileNotFoundError:
        logging.error("toilets.txt not found.")
        return []

    return sorted(toilets, key=lambda x: x['distance'])

# Query OpenStreetMap for nearby toilets and other locations like shops, restaurants, and public transport
def query_overpass_toilets(lat, lon, radius=1000):
    url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    (
      node["amenity"="toilets"](around:{radius},{lat},{lon});
      way["amenity"="toilets"](around:{radius},{lat},{lon});
      relation["amenity"="toilets"](around:{radius},{lat},{lon});
      node["amenity"="toilets"]["shop"](around:{radius},{lat},{lon});
      node["amenity"="toilets"]["restaurant"](around:{radius},{lat},{lon});
      node["amenity"="toilets"]["public_transport"](around:{radius},{lat},{lon});
    );
    out center;
    """
    try:
        resp = requests.post(url, data=query, headers={"User-Agent": "LineBotToiletFinder/1.0"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logging.error(f"Overpass API 查詢失敗：{e}")
        return []

    toilets = []
    for elem in data.get("elements", []):
        if elem["type"] == "node":
            t_lat, t_lon = elem["lat"], elem["lon"]
        elif "center" in elem:
            t_lat, t_lon = elem["center"]["lat"], elem["center"]["lon"]
        else:
            continue
        dist = haversine(lat, lon, t_lat, t_lon)
        name = elem.get("tags", {}).get("name", "無名稱")
        toilets.append({"name": name, "lat": t_lat, "lon": t_lon, "address": "", "distance": dist, "type": "osm"})
    toilets.sort(key=lambda x: x["distance"])
    return toilets

# Add toilet to favorites
def add_to_favorites(user_id, toilet):
    with open("favorites.txt", "a", encoding="utf-8") as file:
        file.write(f"{user_id},{toilet['name']},{toilet['lat']},{toilet['lon']},{toilet['address']}\n")

# Remove toilet from favorites
def remove_from_favorites(user_id, name):
    try:
        with open("favorites.txt", "r", encoding="utf-8") as file:
            lines = file.readlines()
        with open("favorites.txt", "w", encoding="utf-8") as file:
            for line in lines:
                if not line.startswith(f"{user_id},{name},"):
                    file.write(line)
        return True
    except Exception as e:
        logging.error(f"Error removing favorite: {e}")
        return False

# Get user's favorites from file
def get_user_favorites(user_id):
    favorites = []
    try:
        with open("favorites.txt", "r", encoding="utf-8") as file:
            for line in file:
                data = line.strip().split(',')
                if data[0] == user_id:
                    favorites.append({
                        "name": data[1],
                        "lat": float(data[2]),
                        "lon": float(data[3]),
                        "address": data[4],
                        "type": "favorite",
                        "distance": 0
                    })
    except FileNotFoundError:
        logging.error("favorites.txt not found.")
    return favorites

def create_toilet_flex_messages(toilets, show_delete=False):
    bubbles = []
    for t in toilets[:MAX_TOILETS_REPLY]:
        # 使用 OpenStreetMap 靜態地圖服務的 URL
        map_url = f"https://staticmap.openstreetmap.de/staticmap.php?center={t['lat']},{t['lon']}&zoom=15&size=600x300&markers={t['lat']},{t['lon']}&format=png"
        
        # 打印地圖 URL 用於調試
        print(f"Map URL: {map_url}")  # 用於檢查 URL 是否有效

        bubble = {
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": map_url,  # 使用 OpenStreetMap 靜態地圖服務的 URL
                "size": "full",
                "aspectMode": "cover",
                "aspectRatio": "20:13"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": t['name'] if t['name'] else "無名稱", "weight": "bold", "size": "lg"},
                    {"type": "text", "text": f"距離：{t['distance']:.1f} 公尺", "size": "sm", "color": "#555555", "margin": "md"},
                    {"type": "text", "text": f"地址：{t['address']}", "size": "sm", "color": "#aaaaaa", "wrap": True, "margin": "md"},
                    {"type": "text", "text": f"類型：{t['type']}", "size": "sm", "color": "#aaaaaa", "margin": "md"}
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#00BFFF",
                        "action": URIAction(
                            label="導航至最近廁所",
                            uri=f"https://www.openstreetmap.org/?mlat={t['lat']}&mlon={t['lon']}"
                        )
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#FFA07A",
                        "action": {
                            "type": "postback",
                            "label": "刪除最愛" if show_delete else "加入最愛",
                            "data": f"{'remove' if show_delete else 'add'}:{t['name']}"
                        }
                    }
                ],
                "spacing": "sm",
                "flex": 0
            }
        }
        bubbles.append(bubble)

    return {"type": "carousel", "contents": bubbles}

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except LineBotApiError as e:
        logging.error(f"LINE Bot API error: {e}")
    return 'OK'

@app.route('/')
def index():
    return "Line Bot API is running!"

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    text = event.message.text.lower()
    uid = event.source.user_id

    try:
        if text == "附近廁所":
            if uid not in user_locations:
                line_bot_api.push_message(uid, TextSendMessage(text="請先傳送位置"))
                return
            lat, lon = user_locations[uid]
            local_toilets = query_local_toilets(lat, lon)
            osm_toilets = query_overpass_toilets(lat, lon)
            all_toilets = local_toilets + osm_toilets  # Combine local and OSM toilets
            last_toilet_by_user[uid] = all_toilets[0] if all_toilets else None
            msg = create_toilet_flex_messages(all_toilets)
            line_bot_api.push_message(uid, FlexSendMessage("附近廁所", msg))

        elif text == "我的最愛":
            favs = get_user_favorites(uid)
            if not favs:
                line_bot_api.push_message(uid, TextSendMessage(text="你尚未收藏任何廁所"))
                return
            msg = create_toilet_flex_messages(favs, show_delete=True)
            line_bot_api.push_message(uid, FlexSendMessage("我的最愛", msg))

    except LineBotApiError as e:
        logging.error(f"LINE Bot API error: {e}")
        line_bot_api.push_message(uid, TextSendMessage(text="處理錯誤，請稍後再試。"))

@handler.add(PostbackEvent)
def handle_postback(event):
    data = event.postback.data
    uid = event.source.user_id
    if data.startswith("add:"):
        name = data[4:]
        toilet = last_toilet_by_user.get(uid)
        if toilet and toilet['name'] == name:
            add_to_favorites(uid, toilet)
            line_bot_api.push_message(uid, TextSendMessage(text=f"✅ 已收藏 {name}"))
    elif data.startswith("remove:"):
        name = data[7:]
        if remove_from_favorites(uid, name):
            line_bot_api.push_message(uid, TextSendMessage(text=f"❌ 已移除 {name}"))
        else:
            line_bot_api.push_message(uid, TextSendMessage(text="找不到該收藏"))

@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    uid = event.source.user_id
    lat, lon = event.message.latitude, event.message.longitude
    user_locations[uid] = (lat, lon)
    line_bot_api.push_message(uid, TextSendMessage(text="✅ 位置已更新，點 '附近廁所' 查詢"))

if __name__ == '__main__':
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
