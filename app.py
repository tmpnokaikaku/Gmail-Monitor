import time

from line_webhook import LINEWebhook
from oauth_request import OAuthRequest
from fetch_gmail import FetchGmail
from extract_gmail_content import ExtractGmailContent


def main():
    gmm_app = GmailMonitor(flask_port=8080)

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
        valid, keyword = gmm_app.filter_by_items(content)   # 将来実装：keywordを戻り値に追加
        if valid:
            info = gmm_app.extract(keyword, content["full_body"])

            if info:
                text =""
                for key, value in info.items():
                        text += f"{key}: {value}\n"
                if text:
                    gmm_app.push_to_line(text)

    gmm_app.close_ngrok_tunnel()



class GmailMonitor(LINEWebhook, OAuthRequest, FetchGmail, ExtractGmailContent):
    def __init__(
            self,
            max_quota:int =200,
            quota_buff:int =20,

            flask_port:int =8080,

            number_to_fetch:int = 5,

            filter_path:str ="filters.json",
            creds_path:str ="credentials.json",
            token_path:str ="token.json",

            token_and_secret_from_env:bool =True,
            domain_from_env:bool = True,
            uid_from_env:bool = True,

            env_key_for_domain:str = "NGROK_STATIC_DOMAIN",

            line_access_token:str ="",
            line_channel_secret:str ="",
            webhook_domain:str ="",
            line_uid:str ="",
    ):
        
        # 親クラスのコンストラクタ
        LINEWebhook.__init__(
            self,
            max_quota,
            quota_buff,

            flask_port,

            token_and_secret_from_env,
            domain_from_env,
            uid_from_env,

            env_key_for_domain,

            line_access_token,
            line_channel_secret,
            webhook_domain,
            line_uid
        )

        OAuthRequest.__init__(
            self,
            creds_path,
            token_path,
            flask_port,
            self.push_to_line,
            env_key_for_domain
        )

        FetchGmail.__init__(
            self,
            number_to_fetch,
        )

        ExtractGmailContent.__init__(
            self,
            filter_path
        )


if __name__ == "__main__":
    main()
