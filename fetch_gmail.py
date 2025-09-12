from googleapiclient.errors import HttpError
import base64
import time
import socket

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


    def get_full_text(self, payload):
        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
        else:
            body_data = payload["body"].get("data")
            if body_data:
                return base64.urlsafe_b64decode(body_data).decode("utf-8")
        return "(本文なし)"


    def fetch_mail_content(self, service):
        self.app.logger.info(f"最大{self.number_to_fetch}件のメールを取得します")

        last_err = None
        for attempt in range(1, 4):
            try:
                results = service.users().messages().list(userId="me", maxResults=self.number_to_fetch).execute()
                break
            except (socket.timeout, TimeoutError) as e:
                self.app.logger.warning(f"メール取得中に接続がタイムアウトしました (try {attempt}/3):\n{e}")
                last_err = e
            except HttpError as e:
                # エラーコード 5xx は再試行, 4xx は即失敗
                if 500 <= e.resp.status < 600:
                    self.app.logger.warning(f"メールリスト 5xx エラー: (try {attempt}/3)\n{e}")
                    last_err = e
                else:
                    self.app.logger.exception(f"メールリスト HTTPエラー:\n{e}")
                    raise
            except Exception as e:
                self.app.logger.exception(f"メールリスト エラー:\n{e}")
                raise
            time.sleep(2 ** attempt)    # 2s, 4s, 8s
        else:
            # 3回ともに失敗時
            raise TimeoutError(f"メールリスト失敗, 最新エラー:\n{last_err}")

        messages = results.get("messages", [])
        results:list[dict] = []
        for message in messages:
            msg = service.users().messages().get(userId="me", id=message["id"]).execute()
            headers = msg["payload"]["headers"]
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(件名なし)")
            sender = next((h["value"] for h in headers if h["name"] == "From"), "(送信者不明)")
            full_body = self.get_full_text(msg["payload"])
            results.append({"headers":headers, "subject":subject, "sender":sender, "full_body":full_body})

        self.app.logger.info(f"{len(results)}件のメールを取得しました")
        return results
