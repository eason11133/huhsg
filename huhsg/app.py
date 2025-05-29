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

# 載入 .env 環境變數
load_dotenv()

# 驗證是否有設置 LINE Bot 環境變數
if not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_CHANNEL_SECRET"):
    raise ValueError("❌ 請確認 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET 已設置在環境變數中")

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

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

    reply_text = f"您目前的位置是：\n緯度：{lat}\n經度：{lon}\n🔍 正在搜尋附近廁所中..."
    
    # 未來可以接 Google Maps API 或資料庫這裡做查找最近廁所

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



