import os
import hmac
import hashlib
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from dotenv import load_dotenv
from waitress import serve
import base64

load_dotenv()

if not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_CHANNEL_SECRET"):
    raise ValueError("❌ 環境變數未設置")

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

    secret = os.getenv("LINE_CHANNEL_SECRET")
    expected_signature = base64.b64encode(
        hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    ).decode()

    if signature != expected_signature:
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
def handle_message(event):
    user_text = event.message.text
    print(f"Received message: {user_text}")
    if user_text == "廁所":
        reply_text = "请稍等，我帮你找最近的厕所 🧻"
    else:
        reply_text = "请输入「廁所」来查询附近厕所 🚻"

    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except LineBotApiError as e:
        print(f"❌ Reply failed: {e}")

port = int(os.getenv("PORT", 10000))

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=port)




