from flask import Flask, request, abort, redirect, url_for

from linebot.v3.messaging import(
    MessagingApi,
    Configuration,
    ApiClient,
    TextMessage,
    ReplyMessageRequest,
    PushMessageRequest
)
from linebot.v3.webhook import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import(
    MessageEvent,
    TextMessageContent,
    FollowEvent
)

from google_auth_oauthlib.flow import Flow

from dotenv import load_dotenv
from sys import exc_info
from pyngrok import ngrok
from urllib.parse import quote, unquote
import threading
import os
import base64
import signal
import requests

from gmfetch import fetch_and_filter_emails, load_filters_from_json, SCOPES


# Flaskアプリケーション
app = Flask(__name__)

# 環境変数から設定を読み込む
load_dotenv()
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
DOMAIN = os.getenv("NGROK_STATIC_DOMAIN")
LINE_UID = os.getenv("MY_LINE_UID")

# ユーザーホワイトリスト
AUTHORIZED_USERS = [LINE_UID]

# LINE送信メッセージ数の上限
MAX_QUOTA = 200
BUFF = 190

# LINE Messaging APIクライアントとWebhookハンドラを初期化
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


# コールバック
@app.route("/callback", methods=["POST"])
def callback():
    # LINEプラットフォームから送信されるX-Line-Signatureヘッダーを取得
    signature = request.headers["X-Line-Signature"]

    # リクエストボディを取得
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


# Google OAuth認証開始エンドポイント
@app.route("/oauth/start")
def oauth_start():
    uid = request.args.get("uid")
    if not uid:
        return "UIDが指定されていません", 400

    flow = Flow.from_client_secrets_file(
        "credentials.json",
        scopes=SCOPES,
        redirect_uri=f"https://{DOMAIN}/oauth/callback"
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=uid  # LINE UIDをstateに埋め込む
    )
    return redirect(auth_url)


# Google OAuth認証完了コールバック
@app.route("/oauth/callback")
def oauth_callback():
    state = request.args.get("state")  # LINE UID
    if not state:
        return "stateがありません", 400

    flow = Flow.from_client_secrets_file(
        "credentials.json",
        scopes=SCOPES,
        redirect_uri=f"https://{DOMAIN}/oauth/callback"
    )
    flow.fetch_token(authorization_response=request.url)

    creds = flow.credentials
    os.environ["GOOGLE_CREDS"] = base64.b64encode(creds.to_json())

    push_to_line(state, "Google認証完了 Gmailの自動通知を有効化")
    return "Google認証が完了 LINEに通知を送信済"


# イベントハンドラ メッセージを受信
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    # ユーザー認証
    if not is_authorized_user(event):
        print(f"不正ユーザー {event.source.user_id} からのアクセスを拒否。")
        return  # 無視して終了
    else:
        # APIインスタンス化
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            # v3スタイルのリクエストオブジェクト
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    # オウム返し
                    messages=[TextMessage(text=event.message.text)]
                )
            )

# イベントハンドラ 友達追加された
@handler.add(FollowEvent)
def handle_follow(event):
    if not is_authorized_user(event):
        print(f"不正ユーザー {event.source.user_id} からのアクセスを拒否。")
        return
    else:
        # APIインスタンス化
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)

        # 返信
        line_bot_api.reply_message(ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text="このアカウントは非公開運用です")]
        ))


# ユーザー認証関数
def is_authorized_user(event):
    user_id = event.source.user_id
    return user_id in AUTHORIZED_USERS


# 無料枠超過を確認
def check_line_quota():
    access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    url = "https://api.line.me/v2/bot/message/quota/consumption"
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        return data.get("totalUsage", 0)  # 今月の送信通数
    else:
        print(f"Quota取得失敗: {response.status_code}")
        return None


# LINEにテキストメッセージを送信
def push_to_line(message_text: str):
    usage = check_line_quota()
    if usage is None:
        print("使用量の確認に失敗 送信を停止")
        return
    if usage >= MAX_QUOTA-BUFF:
        print("メッセージの上限超過を確認 送信を停止")
        return
    with ApiClient(configuration) as api_client:
        messaging_api = MessagingApi(api_client)
        messaging_api.push_message(
            PushMessageRequest(
                to=LINE_UID,
                messages=[TextMessage(text=message_text)]
            )
        )


# ローカルFlaskサーバー
def run_flask():
    app.run(host="0.0.0.0", port=3000)


# メールを取得して送信
def push_gmail():
    subjects, senders = load_filters_from_json("filters.json")
    results = fetch_and_filter_emails(subject_keywords=subjects, sender_keywords=senders)
    for result in results:
        if result is not None:
            push_to_line(result)
        else:
            print("該当なしメッセージをスキップ")
    print("プロセス終了")


# Googleの認証リンクをLINEに送信
def send_auth_link():
    encoded_uid = quote(LINE_UID)
    url = f"https://{DOMAIN}/oauth/start?uid={encoded_uid}"
    msg = f"Gmail連携のため、以下のリンクからGoogle認証を完了してください。\n{url}"
    push_to_line(msg)


if __name__ == "__main__":
    # Flaskサーバーを別スレッドで起動
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # ngrokトンネル開始
    public_url = ngrok.connect(3000, bind_tls=True, domain=DOMAIN)
    print(f"ngrok public URL: {public_url}")

    try:
        push_gmail()

        # 終了処理
        print("処理完了 サーバーとトンネルを停止")

        push_to_line("サーバー終了（自動送信）")
    except Exception as e:
        exception_type, exception_object, exception_traceback = exc_info()
        filename = exception_traceback.tb_frame.f_code.co_filename
        line_no = exception_traceback.tb_lineno
        print(f"{filename}の{line_no}行目でエラーが発生しました 詳細：{e}")
    finally:
        ngrok.kill()
        os.kill(os.getpid(), signal.SIGINT)
