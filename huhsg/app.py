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
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Initialize Flask and LINE API
app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# Ensure favorites file exists
def ensure_favorites_file():
    try:
        if not os.path.exists("favorites.txt"):
            with open("favorites.txt", "w", encoding="utf-8") as f:
                pass
    except Exception as e:
        logging.error(f"Error creating favorites.txt: {e}")
        raise

ensure_favorites_file()

user_locations = {}
MAX_TOILETS_REPLY = 5
used_reply_tokens = set()
reply_token_expiry = timedelta(minutes=1)

# Haversine distance calculation
def haversine(lat1, lon1, lat2, lon2):
    try:
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        return 2 * asin(sqrt(a)) * 6371000
    except Exception as e:
        logging.error(f"Error calculating distance: {e}")
        return 0

# Update query to include more places like restaurants, pubs, hospitals, stadiums, etc.
def query_overpass_places_with_toilets(lat, lon, radius=1000):
    url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    (
      node["amenity"="toilets"](around:{radius},{lat},{lon});
      node["shop"="convenience"](around:{radius},{lat},{lon});
      node["amenity"="school"](around:{radius},{lat},{lon});
      node["shop"="mall"](around:{radius},{lat},{lon});
      node["amenity"="library"](around:{radius},{lat},{lon});
      node["amenity"="restaurant"](around:{radius},{lat},{lon});
      node["amenity"="pub"](around:{radius},{lat},{lon});
      node["amenity"="hospital"](around:{radius},{lat},{lon});
      node["amenity"="stadium"](around:{radius},{lat},{lon});
      node["amenity"="bus_station"](around:{radius},{lat},{lon});
      node["amenity"="train_station"](around:{radius},{lat},{lon});
      node["amenity"="airport"](around:{radius},{lat},{lon});
    );
    out center;
    """
    try:
        resp = requests.post(url, data=query, headers={"User-Agent": "LineBotPlacesWithToilets/1.0"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logging.error(f"Overpass API 查詢失敗：{e}")
        return []

    places_with_toilets = []
    for elem in data.get("elements", []):
        if "center" in elem:
            t_lat, t_lon = elem["center"]["lat"], elem["center"]["lon"]
        elif elem["type"] == "node":
            t_lat, t_lon = elem["lat"], elem["lon"]
        else:
            continue
        
        name = elem.get("tags", {}).get("name", "無名稱")
        amenity_type = elem["tags"].get("amenity", "未知")
        
        # Check if the place has a toilet
        if "toilets" in elem.get("tags", {}):
            places_with_toilets.append({
                "name": f"{name} (有廁所)",
                "lat": t_lat,
                "lon": t_lon,
                "type": amenity_type,
                "distance": haversine(lat, lon, t_lat, t_lon)
            })

    return sorted(places_with_toilets, key=lambda x: x["distance"])

def create_place_flex_messages(places, user_lat, user_lon):
    bubbles = []
    for p in places[:MAX_TOILETS_REPLY]:
        map_url = f"https://staticmap.openstreetmap.de/staticmap.php?center={p['lat']},{p['lon']}&zoom=15&size=600x300&markers={p['lat']},{p['lon']}&format=png"
        dist = haversine(user_lat, user_lon, p['lat'], p['lon'])
        bubble = {
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": map_url,
                "size": "full",
                "aspectMode": "cover",
                "aspectRatio": "20:13"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": p['name'], "weight": "bold", "size": "lg"},
                    {"type": "text", "text": f"距離：{dist:.1f} 公尺", "size": "sm", "color": "#555555"},
                    {"type": "text", "text": f"類型：{p['type']}", "size": "sm", "color": "#aaaaaa"}
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
                        "action": URIAction(label="導航至該場所", uri=f"https://www.openstreetmap.org/?mlat={p['lat']}&mlon={p['lon']}")
                    }
                ]
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
    return 'OK'

@app.route('/')
def index():
    return "Line Bot API is running!"

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    text = event.message.text.lower()
    uid = event.source.user_id
    if event.reply_token in used_reply_tokens:
        return
    used_reply_tokens.add(event.reply_token)

    if text == "附近廁所":
        if uid not in user_locations:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請先傳送位置"))
            return
        lat, lon = user_locations[uid]
        places = query_overpass_places_with_toilets(lat, lon)
        
        if not places:  # 如果查詢結果為空，發送文字訊息
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="附近好像沒廁所ㄟ，只能原地解放了:)"))
            return
        
        msg = create_place_flex_messages(places, lat, lon)
        line_bot_api.reply_message(event.reply_token, FlexSendMessage("附近有廁所的公共場所", msg))

    elif text == "我的最愛":
        favs = get_user_favorites(uid)
        if not favs:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="你尚未收藏任何廁所"))
            return
        msg = create_place_flex_messages(favs, user_locations[uid][0], user_locations[uid][1])
        line_bot_api.reply_message(event.reply_token, FlexSendMessage("我的最愛", msg))

    elif text == "回饋":
        form_url = "https://docs.google.com/forms/d/e/1FAIpQLSdsibz15enmZ3hJsQ9s3BiTXV_vFXLy0llLKlpc65vAoGo_hg/viewform?usp=sf_link"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"💡 請透過下列連結回報問題或提供意見：\n{form_url}"))

@handler.add(PostbackEvent)
def handle_postback(event):
    uid = event.source.user_id
    data = event.postback.data
    action, name, lat, lon = data.split(":")
    if action == "add":
        for place in query_overpass_places_with_toilets(*user_locations[uid]):
            if place['name'] == name and str(place['lat']) == lat and str(place['lon']) == lon:
                add_to_favorites(uid, place)
                break
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ 已收藏 {name}"))
    elif action == "remove":
        if remove_from_favorites(uid, name, lat, lon):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"❌ 已移除 {name}"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="找不到該收藏"))

@handler.add(MessageEvent, message=LocationMessage)
def handle_location(event):
    uid = event.source.user_id
    lat, lon = event.message.latitude, event.message.longitude
    user_locations[uid] = (lat, lon)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ 位置已更新，點 '附近廁所' 查詢"))

if __name__ == '__main__':
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
