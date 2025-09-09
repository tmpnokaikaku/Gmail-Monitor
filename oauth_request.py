import os
from flask import request, redirect, abort
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
            env_key_for_domain:str ="SERVER_DOMAIN"
        ):

        self.creds_path = creds_path
        self.token_path = token_path
        self.google_creds = None
        self.push_func = push_func      # LINEへのプッシュ関数を外部から渡す
        self._expected_state = None     # LINE UIDをstateとして期待

        # GMMServer初期化は一度だけ
        if not hasattr(self, "app"):
            GMMServer.__init__(self, flask_port=flask_port, env_key_for_domain=env_key_for_domain)

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
                self.app.logger.info("token.json (valid) で認証します")
                return True
            if self.google_creds and self.google_creds.expired and self.google_creds.refresh_token:
                try:
                    self.google_creds.refresh(Request())
                    self.app.logger.info("Google credentials をリフレッシュしました")
                    return True
                except Exception as e:
                    print(f"Credentialのリフレッシュ失敗: {e}")
        else:
            print("token.jsonが存在しません")

        # 認証失敗した場合、認証リンクをLINEに送信
        if self.push_func and uid:
            if not self.webhook_domain:
                self.app.logger.error("SERVER_DOMAIN 未設定")
                return False
            encoded_uid = quote(uid)
            url = f"https://{self.webhook_domain}/oauth/start?uid={encoded_uid}"
            msg = f"Gmail連携のため、以下のリンクからGoogle認証を完了してください。\n{url}"
            self.push_func(msg)
            self.app.logger.info("OAuth認証リンクをLINEに送信")

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

        # UID検証
        if not hasattr(self, "line_uid") or uid != self.line_uid:
            self.app.logger.warning(f"/oauth/start: UIDが合致しません: {uid}")
            abort(403)

        if not self.webhook_domain:
            self.app.logger.error("/oauth/start: SERVER_DOMAIN 未設定")
            return "サーバ設定不備", 500

        try:
            flow = Flow.from_client_secrets_file(
                self.creds_path,
                scopes=self.scopes,
                redirect_uri=f"https://{self.webhook_domain}/oauth/callback"
            )
            auth_url, state = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
                state=uid   # 将来実装:ランダムトークンをstateとして使用
            )
            self._expected_state = uid
            self.app.logger.info("OAuth start を生成 Googleにリダイレクト")
            return redirect(auth_url)
        except Exception as e:
            self.app.logger.exception(f"/oauth/start エラー:\n{e}")
            return "OAuth認証失敗", 500


    def oauth_callback(self):
        self.app.logger.info(f"/oauth/callback に到達: url={request.url[:200]}")    # コールバック到達ログ
        state = request.args.get("state")
        if not state:
            return "stateがありません", 400

        # state検証
        if self._expected_state and state != self._expected_state:
            self.app.logger.warning(f"/oauth/callback: stateが合致しません: {state}")
            abort(403)

        try:
            flow = Flow.from_client_secrets_file(
                self.creds_path, scopes=self.scopes,
                redirect_uri=f"https://{self.webhook_domain}/oauth/callback"
            )
            flow.fetch_token(authorization_response=request.url)
            creds = flow.credentials
            self.google_creds = creds

            # 安全に保存(0600権限)
            fd = os.open(self.token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as token:
                token.write(creds.to_json())

            if self.push_func:
                self.push_func("Google認証完了。Gmailの自動通知を有効化しました。")
            self.app.logger.info("OAuth callback completed and token.json saved")
            return "Google認証が完了しました。LINEにも通知を送りました。"
        except Exception as e:
            self.app.logger.exception(f"/oauth/callback error: {e}")
            return "OAuthコールバック処理に失敗しました。ログを確認してください。", 500
