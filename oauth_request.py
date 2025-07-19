
import os
import json
from flask import request, redirect
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from urllib.parse import quote

from gmm_server import GMMServer

class OAuthRequest(GMMServer):
    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

    def __init__(
            self,
            creds_path:str= "credentials.json",
            token_path:str= "token.json",
            flask_port:int= 8080,
            push_func = None,
            env_key_for_domain:str ="NGROK_STATIC_DOMAIN"
        ):
        
        GMMServer.__init__(self, flask_port=flask_port, env_key_for_domain=env_key_for_domain)
        self.creds_path = creds_path
        self.token_path = token_path
        self.google_creds = None
        self.push_func = push_func  # LINEへのプッシュ関数を外部から渡す

        # Flaskルート定義
        self.app.add_url_rule("/oauth/start", view_func=self.oauth_start)
        self.app.add_url_rule("/oauth/callback", view_func=self.oauth_callback)

    # 初回認証と通常認証を統合
    def authorize(self, uid=None):
        """
        認証を実施。token.jsonがあればそれを使用し、リフレッシュを試みる。
        失敗したらLINEに認証リンクを送る。
        """
        if os.path.exists(self.token_path):
            self.google_creds = Credentials.from_authorized_user_file(self.token_path, self.__class__.scopes)
            if self.google_creds and self.google_creds.valid:
                return True
            if self.google_creds and self.google_creds.expired and self.google_creds.refresh_token:
                try:
                    self.google_creds.refresh(Request())
                    return True
                except Exception as e:
                    print(f"Credentialのリフレッシュ失敗: {e}")
        else:
            print("token.jsonが存在しません。")

        # 認証失敗した場合、認証リンクをLINEに送信
        if self.push_func and uid:
            self.send_auth_link(uid)

        return False


    def get_gmail_service(self):
        """Gmail APIのサービスを取得"""
        if self.google_creds and self.google_creds.valid:
            return build("gmail", "v1", credentials=self.google_creds)
        else:
            raise Exception("認証されていません。")


    def oauth_start(self):
        uid = request.args.get("uid")
        if not uid:
            return "UIDが指定されていません", 400

        flow = Flow.from_client_secrets_file(
            self.creds_path,
            scopes=self.scopes,
            redirect_uri=f"https://{self.webhook_domain}/oauth/callback"
        )
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=uid
        )
        return redirect(auth_url)


    def oauth_callback(self):
        state = request.args.get("state")
        if not state:
            return "stateがありません", 400

        flow = Flow.from_client_secrets_file(
            self.creds_path,
            scopes=self.scopes,
            redirect_uri=f"https://{self.webhook_domain}/oauth/callback"
        )
        flow.fetch_token(authorization_response=request.url)

        creds = flow.credentials
        self.google_creds = creds

        # 認証情報をtoken.jsonに保存
        with open(self.token_path, "w") as token:
            token.write(creds.to_json())

        if self.push_func:
            self.push_func(state, "Google認証完了。Gmailの自動通知を有効化しました。")
        return "Google認証が完了しました。LINEにも通知を送りました。"


    def send_auth_link(self, uid):
        encoded_uid = quote(uid)
        url = f"https://{self.webhook_domain}/oauth/start?uid={encoded_uid}"
        msg = f"Gmail連携のため、以下のリンクからGoogle認証を完了してください。\n{url}"
        self.push_func(msg)
