import os
import hmac
import hashlib
import base64
from math import radians, cos, sin, asin, sqrt
import sqlite3
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, LocationMessage,
    FlexSendMessage, BubbleContainer, BoxComponent, ImageComponent,
    TextComponent, ButtonComponent, MessageAction, LocationAction
)
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

user_locations = {}

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * asin(sqrt(a))
    r = 6371000
    return c * r

def query_local_toilets(lat, lon, radius=1000):
    conn = sqlite3.connect("toilets.db")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 設施名稱, 類別, 緯度, 經度, 位置 FROM toilets")
        toilets = []
        for row in cursor.fetchall():
            name, type_, t_lat, t_lon, address = row
            if not t_lat or not t_lon:
                continue
            try:
                t_lat = float(t_lat)
                t_lon = float(t_lon)
            except ValueError:
                continue
            distance = haversine(lat, lon, t_lat, t_lon)
            if distance <= radius:
                toilets.append({
                    "name": name or "無名稱",
                    "type": "local",
                    "lat": t_lat,
                    "lon": t_lon,
                    "address": address or "",
                    "distance": distance
                })
        return sorted(toilets, key=lambda x: x["distance"])
    except Exception as e:
        print("資料庫查詢錯誤：", e)
        return []
    finally:
        conn.close()

def query_overpass_toilets(lat, lon, radius=1000):
    overpass_url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    (
      node["amenity"="toilets"](around:{radius},{lat},{lon});
      way["amenity"="toilets"](around:{radius},{lat},{lon});
      relation["amenity"="toilets"](around:{radius},{lat},{lon});
    );
    out center;
    """
    try:
        response = requests.post(overpass_url, data=query, timeout=10)
        data = response.json()
    except Exception as e:
        print("Overpass API 查詢失敗：", e)
        return []

    toilets = []
    for item in data.get("elements", []):
        if item["type"] == "node":
            t_lat, t_lon = item["lat"], item["lon"]
        elif "center" in item:
            t_lat, t_lon = item["center"]["lat"], item["center"]["lon"]
        else:
            continue
        distance = haversine(lat, lon, t_lat, t_lon)
        name = item.get("tags", {}).get("name", "無名稱")
        toilets.append({
            "name": name,
            "type": "osm",
            "lat": t_lat,
            "lon": t_lon,
            "distance": distance
        })
    return sorted(toilets, key=lambda x: x["distance"])

def send_flex_buttons(reply_token):
    flex_content = BubbleContainer(
        hero=ImageComponent(
            url="https://i.imgur.com/RStA3pp.png",
            size="full",
            aspectMode="cover",
            aspectRatio="1.51:1"
        ),
        body=BoxComponent(
            layout="vertical",
            spacing="md",
            contents=[
                TextComponent(text="🚽 廁所小幫手", weight="bold", size="lg"),
                BoxComponent(
                    layout="horizontal",
                    spacing="md",
                    contents=[
                        ButtonComponent(
                            action=LocationAction(label="傳送位置"),
                            style="secondary",
                            height="sm",
                            color="#A7D6FF",
                            flex=1
                        ),
                        ButtonComponent(
                            action=MessageAction(label="查附近廁所", text="廁所"),
                            style="primary",
                            height="sm",
                            color="#55C9A6",
                            flex=1
                        )
                    ]
                )
            ]
        )
    )

    message = FlexSendMessage(
        alt_text="請傳送您目前的位置或查詢附近廁所",
        contents=flex_content
    )

    try:
        line_bot_api.reply_message(reply_token, message)
    except LineBotApiError as e:
        print(f"❌ 發送 Flex Message 錯誤：{e}")

@app.route("/")
def home():
    return "✅ LINE Bot is running!"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    hash = hmac.new(os.getenv("LINE_CHANNEL_SECRET").encode(), body.encode(), hashlib.sha256).digest()
    if base64.b64encode(hash).decode() != signature:
        abort(400)

    try:
        handler.handle(body, signature)
    except (InvalidSignatureError, LineBotApiError):
        abort(500)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text.strip().lower()
    user_id = event.source.user_id

    if user_text in ["開始", "menu", "start", "選單"]:
        send_flex_buttons(event.reply_token)
        return

    if "廁所" in user_text:
        if user_id not in user_locations:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請先傳送您目前的位置，讓我幫您找附近的廁所喔！"))
            return

        lat, lon = user_locations[user_id]
        toilets = query_local_toilets(lat, lon)
        if not toilets:
            toilets = query_overpass_toilets(lat, lon)

        if not toilets:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚽 很抱歉，未能找到附近的廁所。"))
            return

        toilet = toilets[0]
        map_url = f"https://www.google.com/maps/search/?api=1&query={toilet['lat']},{toilet['lon']}"
        source = "本地資料庫" if toilet["type"] == "local" else "OpenStreetMap"
        distance_str = f"{toilet['distance']:.2f} 公尺"

        flex_message = {
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": "https://i.imgur.com/BRO9ZQw.png",
                "size": "full",
                "aspectRatio": "20:13",
                "aspectMode": "cover"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": toilet["name"], "weight": "bold", "size": "lg"},
                    {"type": "text", "text": f"距離你 {distance_str}", "size": "sm", "color": "#666666", "margin": "md"},
                    {"type": "text", "text": f"來源：{source}", "size": "sm", "color": "#aaaaaa", "margin": "md"}
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "link",
                        "height": "sm",
                        "action": {
                            "type": "uri",
                            "label": "🗺 開啟地圖導航",
                            "uri": map_url
                        }
                    }
                ],
                "flex": 0
            }
        }

        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(alt_text="最近的廁所資訊", contents=flex_message)
        )
    else:
        reply_text = "請輸入「廁所」或傳送位置來查詢附近廁所 🗺️"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

@handler.add(MessageEvent, message=LocationMessage)
def handle_location_message(event):
    user_id = event.source.user_id
    lat, lon = event.message.latitude, event.message.longitude
    user_locations[user_id] = (lat, lon)
    reply = f"📍 位置已更新！\n緯度：{lat}\n經度：{lon}\n請輸入「廁所」查詢附近的廁所。"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)