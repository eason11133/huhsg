import os
import hmac
import hashlib
import base64
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    LocationMessage
)
from dotenv import load_dotenv
import requests
from math import radians

# 載入 .env 環境變數
load_dotenv()

# 驗證是否有設置 LINE Bot 環境變數
if not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_CHANNEL_SECRET"):
    raise ValueError("❌ 請確認 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 已設置在環境變數中")

# 用戶位置存儲
user_locations = {}

# Flask 設置
app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

@app.route("/")
def home():
    return "✅ LINE Bot is running!"

# Haversine 計算兩個經緯度之間的距離
def haversine(lat1, lon1, lat2, lon2):
    # 地球半徑（單位：公里）
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (pow((pow((math.sin(dlat / 2)), 2) + math.cos(lat1) * math.cos(lat2) * pow(math.sin(dlon / 2), 2)), 1)))

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c  # 距離（單位：公里）
    return distance

# 設置 OpenStreetMap (Overpass API) 查找廁所
def get_nearest_toilets(lat, lon):
    url = 'http://overpass-api.de/api/interpreter'
    query = f"""
    [out:json];
    node["amenity"="toilets"](around:10000,{lat},{lon});
    out;
    """
    response = requests.get(url, params={'data': query})
    data = response.json()
    
    toilets = []
    for element in data['elements']:
        toilet = {
            'lat': element.get('lat'),
            'lon': element.get('lon'),
            'tags': element.get('tags', {})
        }
        toilets.append(toilet)
    
    return toilets

# 處理位置訊息，並儲存用戶位置
@handler.add(MessageEvent, message=LocationMessage)
def handle_location_message(event):
    user_id = event.source.user_id
    lat = event.message.latitude
    lon = event.message.longitude
    user_locations[user_id] = (lat, lon)

    reply_text = "已儲存您的位置，請傳送「廁所」來查找附近的廁所 🧻"
    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except LineBotApiError as e:
        print(f"❌ 回覆錯誤：{e}")

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text.strip()
    user_id = event.source.user_id

    if "廁所" in user_text:
        # 檢查用戶是否已經提供位置
        if user_id in user_locations:
            lat, lon = user_locations[user_id]
            toilets = get_nearest_toilets(lat, lon)

            if not toilets:
                reply_text = "🚽 很抱歉，未能找到附近的廁所。"
            else:
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
                    # 位置取node或center
                    if nearest_toilet.get('type') == 'node':
                        toilet_lat = nearest_toilet['lat']
                        toilet_lon = nearest_toilet['lon']
                    else:
                        toilet_lat = nearest_toilet.get('center', {}).get('lat')
                        toilet_lon = nearest_toilet.get('center', {}).get('lon')

                    reply_text = (f"🧻 最近的廁所是：\n名稱：{toilet_name}\n"
                                  f"位置：({toilet_lat}, {toilet_lon})\n"
                                  f"距離：{min_distance:.2f} 公里\n"
                                  f"點擊地圖導航: https://www.google.com/maps/search/?api=1&query={toilet_lat},{toilet_lon}")
                else:
                    reply_text = "🚽 找不到適合的廁所。"
        else:
            reply_text = "請先傳送您目前的位置，讓我幫您找附近的廁所喔！"
    else:
        reply_text = "請輸入「廁所」來查詢附近廁所，或先傳送您目前的位置。"

    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except LineBotApiError as e:
        print(f"❌ 回覆錯誤：{e}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

