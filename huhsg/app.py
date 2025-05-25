import os
from flask import Flask, request, abort
from linebot.v3.messaging import Configuration, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import WebhookParser, MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError

# 本地開發用：自動載入 .env（部署時 Render 不會用到）
from dotenv import load_dotenv
load_dotenv()

# 環境變數檢查
if not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_CHANNEL_SECRET"):
    raise RuntimeError("❌ LINE_CHANNEL_ACCESS_TOKEN 或 LINE_CHANNEL_SECRET 環境變數未設定")

app = Flask(__name__)

# 初始化 LINE Messaging API 與 WebhookParser
configuration = Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])
messaging_api = MessagingApi(configuration=configuration)
parser = WebhookParser(channel_secret=os.environ["LINE_CHANNEL_SECRET"])

@app.route("/")
def home():
    return "✅ LINE Bot is running!"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        abort(400)

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
            user_text = event.message.text

            if user_text == "廁所":
                reply_text = "請稍等，我幫你找最近的廁所 🧻"
            else:
                reply_text = "請輸入「廁所」來查詢附近廁所 🚻"

            try:
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply_text)]
                    )
                )
            except Exception as e:
                print(f"❌ 回覆訊息失敗：{e}")

    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

