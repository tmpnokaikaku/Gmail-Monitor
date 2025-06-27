
from flask import Flask, request, abort

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

from dotenv import load_dotenv
from pyngrok import ngrok
import threading
import os
import requests

from gmm_server import GMMServer

class LINEWebhook(GMMServer):
    def __init__(
            self,
            max_quota:int =200,
            quota_buff:int =20,

            flask_port:int =8080,   #3000?

            token_and_secret_from_env:bool =True,
            domain_from_env:bool = True,
            uid_from_env:bool = True,

            env_key_for_domain:str ="NGROK_STATIC_DOMAIN",

            line_access_token:str ="",
            line_channel_secret:str ="",
            webhook_domain:str ="",
            line_uid:str =""
    ):
        GMMServer.__init__(self, flask_port=flask_port, env_key_for_domain=env_key_for_domain)

        # 設定読み込み
        if token_and_secret_from_env:
            load_dotenv()
            self.line_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
            self.line_channel_secret = os.getenv("LINE_CHANNEL_SECRET")
        else:
            self.line_access_token = line_access_token
            self.line_channel_secret = line_channel_secret

        if domain_from_env:
            load_dotenv()
            self.webhook_domain = os.getenv("NGROK_STATIC_DOMAIN")
        else:
            self.webhook_domain = webhook_domain

        if uid_from_env:
            load_dotenv()
            self.line_uid = os.getenv("MY_LINE_UID")
        else:
            self.line_uid = line_uid

        # APIクライアント初期化
        self.configuration = Configuration(access_token=self.line_access_token)
        # Webhookハンドラ初期化
        self.handler = WebhookHandler(self.line_channel_secret)

        # LINEメッセージ送信数管理
        self.max_quota = max_quota
        self.quota_buff = quota_buff

        # Flaskコールバックのルーティング
        self.app.add_url_rule("/callback", view_func=self.callback, methods=["POST"])

        # LINEイベントハンドラのデコレータを作成
        # 友達追加された
        decorator_follow = self.handler.add(FollowEvent)
        decorator_follow(self.handle_follow)
        # テキストメッセージを受信
        decorator_message = self.handler.add(MessageEvent, message=TextMessageContent)
        decorator_message(self.handle_message)


    def check_quota(self) -> int|None:
        headers = {
        "Authorization": f"Bearer {self.line_access_token}"
        }
        url = "https://api.line.me/v2/bot/message/quota/consumption"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            return data.get("totalUsage", 0)  # 今月の送信通数
        else:
            print(f"Quota取得失敗: {response.status_code}")
            return None
        

    # コールバック
    def callback(self):
        # LINEプラットフォームから送信されるX-Line-Signatureヘッダーを取得
        signature = request.headers["X-Line-Signature"]

        # リクエストボディを取得
        body = request.get_data(as_text=True)
        self.app.logger.info("Request body: " + body)
        try:
            self.handler.handle(body, signature)
        except InvalidSignatureError:
            abort(400)

        return "OK"


    # イベントハンドラ 友達追加された
    def handle_follow(self, event):
        if event.source.user_id != self.line_uid:
            print(f"不正ユーザー {event.source.user_id} からのアクセスを拒否")
            return
        else:
            # APIインスタンス化
            with ApiClient(self.configuration) as api_client:
                line_bot_api = MessagingApi(api_client)

            # 返信
            line_bot_api.reply_message(ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text="このアカウントは非公開運用です")]
            ))


    # イベントハンドラ メッセージを受信
    def handle_message(self, event):
        # ユーザー認証
        if event.source.user_id != self.line_uid:
            print(f"不正ユーザー {event.source.user_id} からのアクセスを拒否")
            return  # 無視して終了
        else:
            # APIインスタンス化
            with ApiClient(self.configuration) as api_client:
                messaging_api = MessagingApi(api_client)
                # v3スタイルのリクエストオブジェクト
                messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        # オウム返し
                        messages=[TextMessage(text=event.message.text)]
                    )
                )


    # LINEにテキストメッセージを送信
    def push_to_line(self, message_text: str):
        quota_consumption = self.check_quota()
        if quota_consumption is None:
            print("使用量の確認に失敗 送信を停止")
            return
        if quota_consumption >= self.max_quota - self.quota_buff:
            print("メッセージの上限超過を確認 送信を停止")
            return
        with ApiClient(self.configuration) as api_client:
            messaging_api = MessagingApi(api_client)
            messaging_api.push_message(
                PushMessageRequest(
                    to=self.line_uid,
                    messages=[TextMessage(text=message_text)]
                )
            )
