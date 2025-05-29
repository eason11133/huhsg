import os
import hmac
import hashlib
import base64
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    LocationMessage
)
from dotenv import load_dotenv

# 載入 .env 環境變數
load_dotenv()

# 驗證是否有設置 LINE Bot 環境變數
if not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_CHANNEL_SECRET"):
    raise ValueError("❌ 請確認 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 已設置在環境變數中")

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 使用 Overpass API 查詢附近廁所
def get_nearest_toilets(lat, lon, radius=1000):
    overpass_url = "http://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:json];
    (
      node["amenity"="toilets"](around:{radius},{lat},{lon});
      way["amenity"="toilets"](around:{radius},{lat},{lon});
      relation["amenity"="toilets"](around:{radius},{lat},{lon});
    );
    out body;
    """
    
    response = requests.get(overpass_url, params={'data': overpass_query})
    
    if response.status_code == 200:
        data = response.json()
        return data['elements']
    else:
        return None

# 計算兩個坐標的距離（公里）
from math import radians, cos, sin, sqrt, atan2

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0  # 地球半徑 (公里)
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    distance = R * c
    return distance

@app.route("/")
def home():
    return "✅ LINE Bot is running!"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    # 驗證簽名
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

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text.strip()
    print(f"📝 使用者訊息：{user_text}")

    if "廁所" in user_text:
        reply_text = "🚽 正在幫您查找附近的廁所，請傳送您目前的位置。"
    else:
        reply_text = "請輸入「廁所」或傳送位置來查詢附近廁所 🗺️"

    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except LineBotApiError as e:
        print(f"❌ 回覆錯誤：{e}")

# 處理位置訊息
@handler.add(MessageEvent, message=LocationMessage)
def handle_location_message(event):
    lat = event.message.latitude
    lon = event.message.longitude
    print(f"📍 使用者位置：lat={lat}, lon={lon}")

    # 查詢附近廁所
    toilets = get_nearest_toilets(lat, lon)
    
    if not toilets:
        reply_text = "🚽 很抱歉，未能找到附近的廁所。"
    else:
        nearest_toilet = None
        min_distance = float('inf')
        
        # 找到最接近的廁所
        for toilet in toilets:
            toilet_lat = toilet.get('lat')
            toilet_lon = toilet.get('lon')
            distance = haversine(lat, lon, toilet_lat, toilet_lon)
            
            if distance < min_distance:
                nearest_toilet = toilet
                min_distance = distance
        
        if nearest_toilet:
            toilet_name = nearest_toilet.get('tags', {}).get('name', '無名稱')
            toilet_lat = nearest_toilet['lat']
            toilet_lon = nearest_toilet['lon']
            reply_text = f"🧻 最近的廁所是：\n名稱：{toilet_name}\n位置：({toilet_lat}, {toilet_lon})\n距離：{min_distance:.2f} 公里"
        else:
            reply_text = "🚽 找不到適合的廁所。"
    
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




