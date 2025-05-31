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
    MessageEvent, TextMessage, TextSendMessage,
    LocationMessage, FlexSendMessage
)
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_CHANNEL_SECRET"):
    raise ValueError("❌ 請確認 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 已設置在環境變數中")

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

user_locations = {}

def create_db():
    conn = sqlite3.connect('toilets.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS toilets
                 (name TEXT, type TEXT, latitude REAL, longitude REAL, address TEXT)''')
    conn.commit()
    conn.close()

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2*asin(sqrt(a))
    r = 6371000  # 地球半徑（公尺）
    return c * r

def get_nearest_toilets(lat, lon, radius=500):
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
    response = requests.post(overpass_url, data=query)
    data = response.json()
    return data.get('elements', [])

@app.route("/")
def home():
    return "✅ LINE Bot is running!"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    secret = os.getenv("LINE_CHANNEL_SECRET")
    hash = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    calculated_signature = base64.b64encode(hash).decode()

    if calculated_signature != signature:
        print("❌ Invalid signature")
        abort(400)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ Invalid signature")
        abort(400)
    except LineBotApiError as e:
        print(f"❌ LineBot API error: {e}")
        abort(500)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text.strip()
    user_id = event.source.user_id

    if "廁所" in user_text:
        if user_id in user_locations:
            lat, lon = user_locations[user_id]
            toilets = get_nearest_toilets(lat, lon)

            if not toilets:
                reply_text = "🚽 很抱歉，未能找到附近的廁所。"
                line_bot_api.reply_message(
                    event.reply_token, TextSendMessage(text=reply_text)
                )
                return

            nearest_toilet = None
            min_distance = float('inf')

            for toilet in toilets:
                if toilet.get('type') == 'node':
                    toilet_lat = toilet.get('lat')
                    toilet_lon = toilet.get('lon')
                else:
                    center = toilet.get('center')
                    if center:
                        toilet_lat = center.get('lat')
                        toilet_lon = center.get('lon')
                    else:
                        continue
                if toilet_lat is None or toilet_lon is None:
                    continue
                distance = haversine(lat, lon, toilet_lat, toilet_lon)
                if distance < min_distance:
                    nearest_toilet = toilet
                    min_distance = distance

            if nearest_toilet:
                toilet_name = nearest_toilet.get('tags', {}).get('name', '無名稱')
                if nearest_toilet.get('type') == 'node':
                    toilet_lat = nearest_toilet['lat']
                    toilet_lon = nearest_toilet['lon']
                else:
                    toilet_lat = nearest_toilet.get('center', {}).get('lat')
                    toilet_lon = nearest_toilet.get('center', {}).get('lon')

                distance_str = f"{min_distance:.2f} 公尺"
                map_url = f"https://www.google.com/maps/search/?api=1&query={toilet_lat},{toilet_lon}"

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
                            {
                                "type": "text",
                                "text": toilet_name,
                                "weight": "bold",
                                "size": "lg",
                                "wrap": True
                            },
                            {
                                "type": "text",
                                "text": f"距離你 {distance_str}",
                                "size": "sm",
                                "color": "#666666",
                                "margin": "md"
                            }
                        ]
                    },
                    "footer": {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
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
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="🚽 找不到適合的廁所。")
                )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請先傳送您目前的位置，讓我幫您找附近的廁所喔！")
            )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請輸入「廁所」來查詢附近廁所，或先傳送您目前的位置。")
        )

@handler.add(MessageEvent, message=LocationMessage)
def handle_location_message(event):
    user_id = event.source.user_id
    lat = event.message.latitude
    lon = event.message.longitude

    user_locations[user_id] = (lat, lon)

    reply_text = f"📍 位置已更新！您現在位於：\n緯度：{lat}\n經度：{lon}\n請輸入「廁所」查詢附近廁所。"
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    create_db()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
