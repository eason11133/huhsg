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
    FlexSendMessage, BubbleContainer, BoxComponent, TextComponent,
    URIAction, ButtonComponent, ImageComponent, CarouselContainer
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

def insert_toilet(name, type, latitude, longitude, address):
    conn = sqlite3.connect('toilets.db')
    c = conn.cursor()
    c.execute("INSERT INTO toilets (name, type, latitude, longitude, address) VALUES (?, ?, ?, ?, ?)",
              (name, type, latitude, longitude, address))
    conn.commit()
    conn.close()

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2*asin(sqrt(a))
    r = 6371000
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
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="🚽 很抱歉，未能找到附近的廁所。")
                )
                return

            toilet_bubbles = []
            for toilet in toilets[:5]:  # 最多5間
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
                toilet_name = toilet.get('tags', {}).get('name', '無名稱')
                map_url = f"https://www.google.com/maps/search/?api=1&query={toilet_lat},{toilet_lon}"

                bubble = BubbleContainer(
                    header=BoxComponent(
                        layout='vertical',
                        contents=[TextComponent(text=toilet_name, weight='bold', size='md', wrap=True)]
                    ),
                    hero=ImageComponent(
                        url="https://i.imgur.com/SqCh4Fj.png",
                        size="full",
                        aspectRatio="20:13",
                        aspectMode="cover"
                    ),
                    body=BoxComponent(
                        layout='vertical',
                        contents=[TextComponent(text=f"距離約 {distance:.0f} 公尺", size="sm", color="#555555", wrap=True)]
                    ),
                    footer=BoxComponent(
                        layout='vertical',
                        spacing='sm',
                        contents=[
                            ButtonComponent(
                                style='link',
                                height='sm',
                                action=URIAction(label='打開地圖導航', uri=map_url)
                            )
                        ]
                    )
                )
                toilet_bubbles.append(bubble)

            carousel = CarouselContainer(contents=toilet_bubbles)
            flex_message = FlexSendMessage(alt_text="附近的廁所資訊", contents=carousel)

            line_bot_api.reply_message(event.reply_token, flex_message)
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="📍 請先傳送您目前的位置，讓我幫您找附近的廁所！")
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

    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except LineBotApiError as e:
        print(f"❌ 回覆錯誤：{e}")

if __name__ == "__main__":
    create_db()
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
