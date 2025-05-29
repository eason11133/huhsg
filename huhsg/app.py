import os
import hmac
import hashlib
import base64
from math import radians, cos, sin, asin, sqrt
import requests
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, LocationMessage
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_CHANNEL_SECRET"):
    raise ValueError("❌ 請確認 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 已設置在環境變數中")

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 儲存用戶位置的字典
user_locations = {}

def haversine(lat1, lon1, lat2, lon2):
    # 計算兩點間距離（公里）
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2*asin(sqrt(a))
    r = 6371  # 地球半徑(km)
    return c * r

def get_nearest_toilets(lat, lon, radius=500):
    # 使用Overpass API取得附近radius公尺內廁所資料
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
            else:
                nearest_toilet = None
                min_distance = float('inf')

                for toilet in toilets:
                    # 有些可能是way或relation，用 center 作位置
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

@handler.add(MessageEvent, message=LocationMessage)
def handle_location_message(event):
    user_id = event.source.user_id
    lat = event.message.latitude
    lon = event.message.longitude

    user_locations[user_id] = (lat, lon)  # 儲存用戶位置

    reply_text = f"📍 位置已更新！您現在位於：\n緯度：{lat}\n經度：{lon}\n請輸入「廁所」查詢附近廁所。"

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
