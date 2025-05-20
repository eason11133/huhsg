from flask import Flask, jsonify, request, abort
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# 建立 Flask 應用
app = Flask(__name__)

# 用你自己的 Channel Access Token 和 Channel Secret 替換下方內容
line_bot_api = LineBotApi('6mNMYqtC//NR51MllA+n5nq6sV/g1mt+qHR86TnimUOC1R/YNyfS/W0rur6ezPyU+dBFN/O1319yU/y5xSWBSmS7FtPIB2J8ECo3IZWYedK0yo0di8iPxTb7iua4D3qDtLLBf+mM0IRZHS8BTcyhPAdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('59e6845917d74f19060b56592198e8c3')

# 建立 callback 路由，LINE 會將訊息傳到這裡
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

# 訊息事件處理
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text

    # 根據使用者輸入回應內容
    if user_text == "廁所":
        reply = "請稍等，我幫你找最近的廁所 🧻"
    else:
        reply = "請輸入「廁所」來查詢附近廁所 🚻"

    # 回覆訊息
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

# 啟動 Flask 應用
if __name__ == "__main__":
    app.run(debug=True)
