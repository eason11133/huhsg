import os
import hmac
import hashlib
import base64
import math
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

# 驗證環境變數
if not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_CHANNEL_SECRET"):
    raise ValueError("❌ 請確認 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 已設置在環境變數中")

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 預設幾個廁所資料（名稱、緯度、經度）
toilets = [
    {"name": "廁所A", "lat": 25.033964, "lon": 121.564468},  # 台北101附近
    {"name": "廁所B", "lat": 25.047675, "lon": 121.517055},  # 台北車站附近
    {"name": "廁所C", "lat": 25.037486, "lon": 121.563679},  # 信義區某地
]

def haversine(lat1, lon1, lat2, lon2):
    # 計算兩點之間的距離（公尺）
    R = 6371000  # 地球半徑，公尺
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

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
    print(f"📝 使用者訊息：{user_text}")

    if "廁所" in user_text:
        reply_text = "🚽 請傳送您目前的位置，我來幫您找最近的廁所。"
    else:
        reply_text = "請輸入「廁所」或傳送位置來查詢附近廁所 🗺️"

    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except LineBotApiError as e:
        print(f"❌ 回覆錯誤：{e}")

@handler.add(MessageEvent, message=LocationMessage)
def handle_location_message(event):
    lat = event.message.latitude
    lon = event.message.longitude
    print(f"📍 使用者位置：lat={lat}, lon={lon}")

    # 計算最近的廁所與距離
    nearest = None
    min_distance = None
    for toilet in toilets:
        dist = haversine(lat, lon, toilet["lat"], toilet["lon"])
        if min_distance is None or dist < min_distance:
            min_distance = dist
            nearest = toilet

    if nearest:
        reply_text = (f"您目前的位置是：\n緯度：{lat}\n經度：{lon}\n\n"
                      f"距離最近的廁所是：{nearest['name']}\n"
                      f"距離約 {int(min_distance)} 公尺。")
    else:
        reply_text = "抱歉，目前沒有可查詢的廁所資料。"

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



