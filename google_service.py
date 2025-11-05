from flask import request, redirect, abort, Response
from google.auth.transport.requests import Request as GRequest, AuthorizedSession
from requests.exceptions import Timeout, RequestException
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from urllib.parse import quote
import requests
import os
import base64

from gmm_server import GMMServer


class GoogleService(GMMServer):
    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]

    def __init__(
            self,
            creds_path:str = "credentials.json",
            token_path:str = "token.json",
            flask_port:int = 8080,
            push_func = None,
            env_key_for_domain:str = "SERVER_DOMAIN",
            number_to_fetch:int = 5
        ):

        self.creds_path = creds_path
        self.token_path = token_path
        self.google_creds = None
        self.push_func = push_func      # LINEへのプッシュ関数を外部から渡す
        self._expected_state = None     # LINE UIDをstateとして期待
        self.http_timeout = int(os.getenv("GMM_HTTP_TIMEOUT", "60"))
        self.number_to_fetch = number_to_fetch
        self.gmail_session: AuthorizedSession|None = None
        self.gmail_base = os.getenv("GMM_GMAIL_BASE", "https://gmail.googleapis.com").rstrip("/")

        # GMMServer初期化は一度だけ
        if not hasattr(self, "app"):
            GMMServer.__init__(self, flask_port=flask_port, env_key_for_domain=env_key_for_domain)

        # Flaskルート定義
        self.app.add_url_rule("/oauth/start", view_func=self.oauth_start)
        self.app.add_url_rule("/oauth/callback", view_func=self.oauth_callback)


    # timeoutをデフォルト適用する requests.Session を用意
    def _session_with_default_timeout(self, timeout:int) -> requests.Session:
        s = requests.Session()
        orig_request = s.request

        def _request(method, url, **kwargs):
            kwargs.setdefault("timeout", timeout)
            return orig_request(method, url, **kwargs)

        s.request = _request
        return s


    # 初回認証と通常認証を統合
    def authorize(self, uid=None) -> bool:
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
                    #self.google_creds.refresh(Request())
                    # requests セッションに統一
                    s = self._session_with_default_timeout(self.http_timeout)
                    self.google_creds.refresh(GRequest(session=s))
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


    def get_gmail_session(self) -> AuthorizedSession:
        """Gmail API 呼び出し用の AuthorizedSession (requests) を取得"""
        if self.google_creds and self.google_creds.valid:
            # requests 統一
            self.gmail_session = AuthorizedSession(self.google_creds)
            self.app.logger.info("Gmail AuthorizedSession を生成しました")
            return self.gmail_session
        else:
            raise Exception("認証されていません。")


    def oauth_start(self) -> Response:
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


    def oauth_callback(self) -> tuple[str,int]:
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
            # flow (内部 requests) にも timeout 指定
            flow.fetch_token(authorization_response=request.url, timeout=self.http_timeout)
            creds = flow.credentials
            self.google_creds = creds

            # 安全に保存(0600権限)
            fd = os.open(self.token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as token:
                token.write(creds.to_json())

            if self.push_func:
                self.push_func("Google認証完了。Gmailの自動通知を有効化しました。")
            self.app.logger.info("OAuth callback completed and token.json saved")
            return "Google認証が完了しました。LINEにも通知を送りました。", 200
        except Timeout as e:
            self.app.logger.error(f"Google token API timeout (> {self.http_timeout}s): {e}")
            return f"Google token API timeout (> {self.http_timeout}s)", 504
        except RequestException as e:
            self.app.logger.exception(f"Google token API request error: {e}")
            return "Google token API request error", 502
        except Exception as e:
            self.app.logger.exception(f"/oauth/callback error: {e}")
            return "OAuthコールバック処理に失敗しました。ログを確認してください。", 500


    def fetch_mail_content(self) -> list[dict]:
        """
        メールを取得。requests（AuthorizedSession）で REST を直接叩く。
        """
        def _get_full_text(payload):
            if "parts" in payload:
                for part in payload["parts"]:
                    if part["mimeType"] == "text/plain":
                        return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
            else:
                body_data = payload["body"].get("data")
                if body_data:
                    return base64.urlsafe_b64decode(body_data).decode("utf-8")
            return "(本文なし)"

        # セッション準備
        if not self.gmail_session:
            self.get_gmail_session()
        sess = self.gmail_session
        assert sess is not None

        self.app.logger.info(f"最大{self.number_to_fetch}件のメールを取得します")
        try:
            # 軽量化のため id のみ取得
            url = f"{self.gmail_base}/gmail/v1/users/me/messages"
            params = {
                "maxResults": self.number_to_fetch,
                "includeSpamTrash": "false",
                # 未読のみ
                "labelIds": ["INBOX", "UNREAD"],
                "fields": "messages(id),nextPageToken",
            }
            #r = sess.get(url, params=params, timeout=self.http_timeout)
            r = sess.get(
                msg_url,
                params={
                    "format": "full",
                    "fields": "id,payload/headers(name,value),payload/body/data,payload/parts(mimeType,body/data)"
                },
                timeout=self.http_timeout
            )
            r.raise_for_status()
            data = r.json()
            messages = data.get("messages", [])
            self.app.logger.info(f"{len(messages)}件のメールを受信しました")
        except Timeout as e:
            self.app.logger.warning(f"メール取得中に接続がタイムアウト: {e}")
            raise
        except RequestException as e:
            self.app.logger.exception(f"メールリスト HTTPエラー: {e}")
            raise

        results:list[dict] = []
        for m in messages:
            try:
                msg_url = f"{self.gmail_base}/gmail/v1/users/me/messages/{m['id']}"
                r2 = sess.get(msg_url, params={"format": "full"}, timeout=self.http_timeout)
                r2.raise_for_status()
                msg = r2.json()
                headers = msg.get("payload", {}).get("headers", [])
                subject = next((h["value"] for h in headers if h.get("name") == "Subject"), "(件名なし)")
                sender = next((h["value"] for h in headers if h.get("name") == "From"), "(送信者不明)")
                full_body = _get_full_text(msg.get("payload", {}))
                results.append({"headers": headers, "subject": subject, "sender": sender, "full_body": full_body})
            except Timeout as e:
                self.app.logger.warning(f"個別メッセージ取得のタイムアウト(id={m.get('id')}): {e}")
                continue
            except RequestException as e:
                self.app.logger.warning(f"個別メッセージ取得のHTTPエラー(id={m.get('id')}): {e}")
                continue

        return results
