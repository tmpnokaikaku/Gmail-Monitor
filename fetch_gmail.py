from google.auth.transport.requests import AuthorizedSession
from googleapiclient.errors import HttpError
from typing import List, Dict, Any, Optional
import base64
import time
import socket
import ssl
import httplib2
import os

from gmm_server import GMMServer


class FetchGmail(GMMServer):
    def __init__(
            self,
            number_to_fetch:int = 5,

            flask_port:int = 8080,
            env_key_for_domain:str ="SERVER_DOMAIN"
    ):

        # GMMServer初期化は一度だけ
        if not hasattr(self, "app"):
            GMMServer.__init__(self, flask_port=flask_port, env_key_for_domain=env_key_for_domain)

        self.number_to_fetch = number_to_fetch


    def _get_full_text(self, payload):
        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
        else:
            body_data = payload["body"].get("data")
            if body_data:
                return base64.urlsafe_b64decode(body_data).decode("utf-8")
        return "(本文なし)"


    """
    def fetch_mail_content(self, service):
        self.app.logger.info(f"最大{self.number_to_fetch}件のメールを取得します")

        last_err = None
        retry_max = int(os.getenv("GMM_FETCH_RETRY", 3))
        for attempt in range(1, retry_max + 1):
            try:
                # 余計なレスポンスを省いて応答を軽量化 部分レスポンス
                req = service.users().messages().list(
                    userId="me",
                    maxResults=self.number_to_fetch,
                    includeSpamTrash=False,
                    fields="messages(id),nextPageToken"  # 返却は id のみに
                )
                # googleapiclientのビルトイン再試行は 429/5xx をハンドリング
                results = req.execute(num_retries=2)   # まずはライブラリの再試行に任せる
                break

            except (socket.timeout, TimeoutError, ssl.SSLError,
                    httplib2.HttpLib2Error, socket.gaierror, OSError) as e:
                self.app.logger.warning(
                    f"メール取得中に接続がタイムアウト/ネットワーク例外 (try {attempt}/{retry_max}):\n{e}"
                )
                last_err = e

            except HttpError as e:
                # 429/5xx は明示的に追加再試行 リージョン不調, 一過性障害の吸収
                if e.resp is not None and (e.resp.status == 429 or 500 <= e.resp.status < 600):
                    self.app.logger.warning(f"メールリスト HTTP {e.resp.status} (try {attempt}/{retry_max}): {e}")
                    last_err = e
                else:
                    self.app.logger.exception(f"メールリスト HTTPエラー(再試行不可):\n{e}")
                    raise

            except Exception as e:
                self.app.logger.exception(f"メールリスト 予期せぬエラー:\n{e}")
                raise

            time.sleep(min(30, 2 ** attempt))  # 2s,4s,8s,16s,30s で頭打ち
        else:
            raise TimeoutError(f"メールリスト失敗, 最新エラー:\n{last_err}")

        messages = results.get("messages", [])
        out: list[dict] = []
        for message in messages:
            # 個別 get も軽量化,再試行
            msg = service.users().messages().get(
                userId="me",
                id=message["id"],
                format="full"
            ).execute(num_retries=2)
            headers = msg["payload"]["headers"]
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(件名なし)")
            sender  = next((h["value"] for h in headers if h["name"] == "From"), "(送信者不明)")
            full_body = self._get_full_text(msg["payload"])
            out.append({"headers": headers, "subject": subject, "sender": sender, "full_body": full_body})

        self.app.logger.info(f"{len(out)}件のメールを取得しました")
        return out
    """
    def fetch_mail_content(self, service, creds=None) -> List[Dict[str, Any]]:
        """メール一覧→個別取得。まず googleapiclient 経由で試し、失敗時に requests にフォールバック。"""

        retry_max = int(os.getenv("GMM_FETCH_RETRY", "5"))
        http_timeout = int(os.getenv("GMM_HTTP_TIMEOUT", "15"))  # 秒
        fetch_transport = os.getenv("GMM_FETCH_TRANSPORT", "auto").lower()  # auto|apiclient|requests
        gmail_base = os.getenv("GMM_GMAIL_BASE", "https://gmail.googleapis.com").rstrip("/")

        self.app.logger.info(f"最大{self.number_to_fetch}件のメールを取得します (transport={fetch_transport}, timeout={http_timeout}s)")

        messages_ids: Optional[List[Dict[str, str]]] = None
        last_err: Optional[Exception] = None

        def _list_via_apiclient():
            # 軽量化：id のみ
            req = service.users().messages().list(
                userId="me",
                maxResults=self.number_to_fetch,
                includeSpamTrash=False,
                fields="messages(id),nextPageToken",
            )
            # 429/5xx はライブラリ側で少し再試行
            return req.execute(num_retries=2)

        def _list_via_requests():
            if creds is None and getattr(self, "google_creds", None) is not None:
                s = AuthorizedSession(self.google_creds)
            elif creds is not None:
                s = AuthorizedSession(creds)
            else:
                raise RuntimeError("requests 経路に必要な creds がありません")

            url = f"{gmail_base}/gmail/v1/users/me/messages"
            params = {
                "maxResults": self.number_to_fetch,
                "includeSpamTrash": "false",
                "fields": "messages(id),nextPageToken",
            }
            # connect/read タイムアウトを明示
            r = s.get(url, params=params, timeout=(http_timeout, http_timeout))
            r.raise_for_status()
            return r.json()

        # --- メッセージ一覧 ---
        for attempt in range(1, retry_max + 1):
            try:
                if fetch_transport in ("apiclient", "auto"):
                    results = _list_via_apiclient()
                else:
                    results = _list_via_requests()
                messages_ids = results.get("messages", [])
                break
            except (socket.timeout, TimeoutError, ssl.SSLError,
                    httplib2.HttpLib2Error, socket.gaierror, OSError) as e:
                self.app.logger.warning(
                    f"メール取得中に接続がタイムアウト/ネットワーク例外 (try {attempt}/{retry_max}):\n{e}"
                )
                last_err = e
            except HttpError as e:
                if e.resp is not None and (e.resp.status == 429 or 500 <= e.resp.status < 600):
                    self.app.logger.warning(f"メールリスト HTTP {e.resp.status} (try {attempt}/{retry_max}): {e}")
                    last_err = e
                else:
                    self.app.logger.exception(f"メールリスト HTTPエラー(再試行不可):\n{e}")
                    raise
            except Exception as e:
                # apiclient が詰まる環境向けに自動フォールバック
                if fetch_transport == "auto":
                    self.app.logger.warning(f"apiclient 経路で失敗、requests 経路へ切替: {type(e).__name__}: {e}")
                    # 一回だけ requests で即再試行
                    try:
                        results = _list_via_requests()
                        messages_ids = results.get("messages", [])
                        break
                    except Exception as e2:
                        self.app.logger.warning(f"requests 経路でも失敗: {type(e2).__name__}: {e2}")
                        last_err = e2
                else:
                    self.app.logger.exception(f"メールリスト 予期せぬエラー:\n{e}")
                    raise
            time.sleep(min(30, 2 ** attempt))
        else:
            raise TimeoutError(f"メールリスト失敗, 最新エラー:\n{last_err}")

        # --- 個別メッセージ ---
        out: List[Dict[str, Any]] = []
        if not messages_ids:
            self.app.logger.info("対象メッセージがありません")
            return out

        if fetch_transport == "requests" or (fetch_transport == "auto" and 'results' in locals() and isinstance(results, dict) and 'kind' not in results):
            # requests 経路（AuthorizedSession）で取得
            if creds is None and getattr(self, "google_creds", None) is not None:
                s = AuthorizedSession(self.google_creds)
            elif creds is not None:
                s = AuthorizedSession(creds)
            else:
                raise RuntimeError("requests 経路に必要な creds がありません")

            for m in messages_ids:
                url = f"{gmail_base}/gmail/v1/users/me/messages/{m['id']}"
                r = s.get(url, params={"format": "full"}, timeout=(http_timeout, http_timeout))
                r.raise_for_status()
                msg = r.json()
                headers = msg["payload"]["headers"]
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(件名なし)")
                sender  = next((h["value"] for h in headers if h["name"] == "From"), "(送信者不明)")
                full_body = self._get_full_text(msg["payload"])
                out.append({"headers": headers, "subject": subject, "sender": sender, "full_body": full_body})
        else:
            # apiclient 経路
            for m in messages_ids:
                msg = service.users().messages().get(
                    userId="me", id=m["id"], format="full"
                ).execute(num_retries=2)
                headers = msg["payload"]["headers"]
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(件名なし)")
                sender  = next((h["value"] for h in headers if h["name"] == "From"), "(送信者不明)")
                full_body = self._get_full_text(msg["payload"])
                out.append({"headers": headers, "subject": subject, "sender": sender, "full_body": full_body})

        self.app.logger.info(f"{len(out)}件のメールを取得しました")
        return out
