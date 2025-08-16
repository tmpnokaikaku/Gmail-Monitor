from dataclasses import dataclass
from typing import Optional

from line_webhook import LINEWebhook
from oauth_request import OAuthRequest
from fetch_gmail import FetchGmail
from extract_gmail_content import ExtractGmailContent

import time


# --- 構成をまとめるデータクラス（引数の受け渡しをシンプルに） ---
@dataclass
class LineConfig:
    max_quota: int = 200
    quota_buff: int = 20
    flask_port: int = 8080
    token_and_secret_from_env: bool = True
    domain_from_env: bool = True
    uid_from_env: bool = True
    env_key_for_domain: str = "NGROK_STATIC_DOMAIN"
    line_access_token: str = ""
    line_channel_secret: str = ""
    webhook_domain: str = ""
    line_uid: str = ""

@dataclass
class OAuthConfig:
    creds_path: str = "credentials.json"
    token_path: str = "token.json"
    flask_port: int = 8080
    env_key_for_domain: str = "NGROK_STATIC_DOMAIN"

@dataclass
class GmailFetchConfig:
    number_to_fetch: int = 5

@dataclass
class ExtractConfig:
    filter_path: str = "filters.json"


class GmailMonitor(LINEWebhook, OAuthRequest, FetchGmail, ExtractGmailContent):
    def __init__(
        self,
        line_cfg: Optional[LineConfig] = None,
        oauth_cfg: Optional[OAuthConfig] = None,
        fetch_cfg: Optional[GmailFetchConfig] = None,
        extract_cfg: Optional[ExtractConfig] = None,
        # 旧 API 互換用（未指定なら上の dataclass 既定値が使われます）
        **legacy_kwargs,
    ) -> None:
        # dataclass の既定値を起点に、必要があれば legacy な単体引数で上書き
        line_cfg = line_cfg or LineConfig(
            max_quota=legacy_kwargs.get("max_quota", LineConfig.max_quota),
            quota_buff=legacy_kwargs.get("quota_buff", LineConfig.quota_buff),
            flask_port=legacy_kwargs.get("flask_port", LineConfig.flask_port),
            token_and_secret_from_env=legacy_kwargs.get("token_and_secret_from_env", LineConfig.token_and_secret_from_env),
            domain_from_env=legacy_kwargs.get("domain_from_env", LineConfig.domain_from_env),
            uid_from_env=legacy_kwargs.get("uid_from_env", LineConfig.uid_from_env),
            env_key_for_domain=legacy_kwargs.get("env_key_for_domain", LineConfig.env_key_for_domain),
            line_access_token=legacy_kwargs.get("line_access_token", LineConfig.line_access_token),
            line_channel_secret=legacy_kwargs.get("line_channel_secret", LineConfig.line_channel_secret),
            webhook_domain=legacy_kwargs.get("webhook_domain", LineConfig.webhook_domain),
            line_uid=legacy_kwargs.get("line_uid", LineConfig.line_uid),
        )

        oauth_cfg = oauth_cfg or OAuthConfig(
            creds_path=legacy_kwargs.get("creds_path", OAuthConfig.creds_path),
            token_path=legacy_kwargs.get("token_path", OAuthConfig.token_path),
            flask_port=line_cfg.flask_port,  # LINE と同一ポートを共有
            env_key_for_domain=line_cfg.env_key_for_domain,
        )

        fetch_cfg = fetch_cfg or GmailFetchConfig(
            number_to_fetch=legacy_kwargs.get("number_to_fetch", GmailFetchConfig.number_to_fetch)
        )

        extract_cfg = extract_cfg or ExtractConfig(
            filter_path=legacy_kwargs.get("filter_path", ExtractConfig.filter_path)
        )

        # 親クラスの初期化
        LINEWebhook.__init__(
            self,
            line_cfg.max_quota,
            line_cfg.quota_buff,
            line_cfg.flask_port,
            line_cfg.token_and_secret_from_env,
            line_cfg.domain_from_env,
            line_cfg.uid_from_env,
            line_cfg.env_key_for_domain,
            line_cfg.line_access_token,
            line_cfg.line_channel_secret,
            line_cfg.webhook_domain,
            line_cfg.line_uid,
        )

        OAuthRequest.__init__(
            self,
            oauth_cfg.creds_path,
            oauth_cfg.token_path,
            oauth_cfg.flask_port,
            self.push_to_line,
            oauth_cfg.env_key_for_domain,
        )

        FetchGmail.__init__(self, fetch_cfg.number_to_fetch)
        ExtractGmailContent.__init__(self, extract_cfg.filter_path)

    # main から使うユーティリティもこのクラスに温存


def main() -> None:
    # 構成の意図が読みやすくなる
    line_cfg = LineConfig(flask_port=8080)
    oauth_cfg = OAuthConfig(flask_port=8080)
    fetch_cfg = GmailFetchConfig(number_to_fetch=10)
    extract_cfg = ExtractConfig(filter_path="filters.json")

    gmm_app = GmailMonitor(
        line_cfg=line_cfg,
        oauth_cfg=oauth_cfg,
        fetch_cfg=fetch_cfg,
        extract_cfg=extract_cfg,
    )

    gmm_app.run_and_expose_server()
    print(f"ngrok public url: {gmm_app.public_url}")

    try:
        service = gmm_app.get_gmail_service()
    except Exception:
        is_authorized = gmm_app.authorize(gmm_app.line_uid)
        while not is_authorized:
            time.sleep(10)
            print("認証待機中")
        service = gmm_app.get_gmail_service()

    mail_contents = gmm_app.fetch_mail_content(service)
    print(f"{len(mail_contents)}件のメールを受信")

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

    gmm_app.close_ngrok_tunnel()


if __name__ == "__main__":
    main()
