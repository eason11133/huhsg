import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from dotenv import load_dotenv
load_dotenv()

# 确保环境变量已正确设置
if not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_CHANNEL_SECRET"):
    raise RuntimeError("❌ LINE_CHANNEL_ACCESS_TOKEN 或 LINE_CHANNEL_SECRET 环境变量未设置")

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

    try:
        # 使用 handle 方法来处理 Webhook 事件
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ Invalid signature")
        abort(400)  # 如果签名无效，返回 400 错误
    except LineBotApiError as e:
        print(f"❌ LineBot API error: {e}")
        abort(500)  # 其他错误，返回 500 错误

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    # 获取用户消息
    user_text = event.message.text
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

# 确保 Flask 应用监听正确端口
port = int(os.getenv("PORT", 10000))  # 使用 10000 作为默认端口
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port, debug=True)  # 设置 debug=True 以便于排查问题



