import os
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from dotenv import load_dotenv
load_dotenv()

# 確保環境變數已正確設定
if not os.getenv("LINE_CHANNEL_ACCESS_TOKEN") or not os.getenv("LINE_CHANNEL_SECRET"):
    raise RuntimeError("❌ LINE_CHANNEL_ACCESS_TOKEN 或 LINE_CHANNEL_SECRET 環境變數未設定")

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
        # 使用 handle 方法來處理 Webhook 事件
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ Invalid signature")
        abort(400)  # 如果簽名無效，返回 400 錯誤

    return "OK"

# 設定 Webhook 事件處理函數
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text
    # 簡單回應邏輯，可以根據用戶輸入回應不同的訊息
    if user_text == "廁所":
        reply = "請稍等，我幫你找最近的廁所 🧻"
    else:
        reply = "請輸入「廁所」來查詢附近廁所 🚻"
    
    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )
    except LineBotApiError as e:
        print(f"❌ 回覆訊息失敗：{e}")
        # 打印更詳細的錯誤信息
        print(f"詳細錯誤: {e.response.status_code}, {e.response.text}")

# 確保 Flask 應用監聽正確端口
port = int(os.getenv("PORT", 10000))  # 使用 10000 作為預設端口
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port, debug=True)  # 設置 debug=True 以便於排查問題

