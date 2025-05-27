import os
import hmac
import hashlib
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv

load_dotenv()  # 載入.env檔案

# 確保環境變數已正確設定
if not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_CHANNEL_SECRET"):
    raise ValueError("❌ LINE_CHANNEL_ACCESS_TOKEN 或 LINE_CHANNEL_SECRET 環境變數未設置")

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

    # 計算簽名
    secret = os.getenv("LINE_CHANNEL_SECRET")
    calculated_signature = hmac.new(
        secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()

    print(f"Calculated Signature: {calculated_signature}")
    print(f"Received Signature: {signature}")

    # 比較簽名，若不相同則返回 400 錯誤
    if calculated_signature != signature:
        print("❌ Invalid signature")
        abort(400)

    try:
        # 使用 handle 方法來處理 Webhook 事件
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ Invalid signature")
        abort(400)  # 如果簽名無效，返回 400 錯誤
    except LineBotApiError as e:
        print(f"❌ LineBot API error: {e}")
        abort(500)  # 其他錯誤，返回 500 錯誤

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    print(f"Received message: {user_text}")  # 輸出收到的訊息
    if user_text == "廁所":
        reply_text = "请稍等，我帮你找最近的厕所 🧻"
    else:
        reply_text = "请输入「廁所」来查询附近厕所 🚻"

    try:
        # 回复用户消息
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except LineBotApiError as e:
        print(f"❌ Reply failed: {e}")

# 確保 Flask 應用監聽正確端口
port = int(os.getenv("PORT", 10000))  # 使用 10000 作為預設端口
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port, debug=True)  # 設置 debug=True 以便於排查問題

