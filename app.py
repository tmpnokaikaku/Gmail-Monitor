from dataclasses import dataclass
from typing import Optional

from line_webhook import LINEWebhook
from oauth_request import OAuthRequest
from fetch_gmail import FetchGmail
from extract_gmail_content import ExtractGmailContent

import time


# --- 構成をまとめるデータクラス（引数の受け渡しをシンプルに） ---
@dataclass
class AppConfig:
    # LINE / Webhook
    max_quota: int = 200
    quota_buff: int = 20
    flask_port: int = 8080
    token_and_secret_from_env: bool = True
    domain_from_env: bool = True
    uid_from_env: bool = True
    env_key_for_domain: str = "SERVER_DOMAIN"
    line_access_token: str = ""
    line_channel_secret: str = ""
    webhook_domain: str = ""
    line_uid: str = ""

    # OAuth / Gmail
    creds_path: str = "credentials.json"
    token_path: str = "token.json"

    # Fetch / Extract
    number_to_fetch: int = 5
    filter_path: str = "filters.json"


class GmailMonitor(LINEWebhook, OAuthRequest, FetchGmail, ExtractGmailContent):
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        # 親クラスの初期化
        LINEWebhook.__init__(
            self,
            cfg.max_quota,
            cfg.quota_buff,
            cfg.flask_port,
            cfg.token_and_secret_from_env,
            cfg.domain_from_env,
            cfg.uid_from_env,
            cfg.env_key_for_domain,
            cfg.line_access_token,
            cfg.line_channel_secret,
            cfg.webhook_domain,
            cfg.line_uid,
        )

        OAuthRequest.__init__(
            self,
            cfg.creds_path,
            cfg.token_path,
            cfg.flask_port,
            self.push_to_line,
            cfg.env_key_for_domain,
        )

        FetchGmail.__init__(
            self,
            cfg.number_to_fetch
        )

        ExtractGmailContent.__init__(
            self,
            cfg.filter_path
        )

    # main から使うユーティリティもこのクラスに温存


def main() -> None:
    # 構成の意図が読みやすくなる
    cfg = AppConfig(
        flask_port=8080,
        number_to_fetch=10,
        filter_path="filters.json",
    )

    gmm_app = GmailMonitor(cfg)

    gmm_app.run_and_expose_server()
    gmm_app.app.logger.info(f"Public URL: {gmm_app.public_url}")

    try:
        service = gmm_app.get_gmail_service()
    except Exception:
        # 認証リンクをLINEに送る（tokenが無い/失効時）
        foo = gmm_app.authorize(gmm_app.line_uid)

        # token.jsonができて有効になるまで最大10分ポーリング
        service = None
        for i in range(60):
            try:
                service = gmm_app.get_gmail_service()
                gmm_app.app.logger.info("Gmail service 取得完了")
                break
            except Exception:
                time.sleep(10)
                gmm_app.app.logger.info(f"認証待機中... ({i+1}/60)")
        if service is None:
            gmm_app.app.logger.error("OAuthが完了しませんでした")
            raise RuntimeError("OAuthが完了しませんでした")

    mail_contents = gmm_app.fetch_mail_content(service)

    for content in mail_contents:
        # 返り値に extractor(抽出器) と sender_label(送信者ラベル) を含める
        valid, extractor, sender_label = gmm_app.filter_by_items(content)
        if not valid:
            continue

        info = gmm_app.extract(extractor, content["full_body"])  # 例: extractor="manaba"
        if not info:
            continue

        # 送信者ラベルを先頭に付与（必要に応じて整形）
        text_lines = [f"[{sender_label}]" ] + [f"{k}: {v}" for k, v in info.items()]
        gmm_app.push_to_line("\n".join(text_lines))

    gmm_app.stop_server()


if __name__ == "__main__":
    main()
