import base64

from gmm_server import GMMServer


class FetchGmail(GMMServer):
    def __init__(
            self,
            number_to_fetch:int = 5,

            flask_port:int = 8080,
            env_key_for_domain:str ="NGROK_STATIC_DOMAIN"
    ):
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
        results = service.users().messages().list(userId="me", maxResults=self.number_to_fetch).execute()
        messages = results.get("messages", [])

        #print(f"受信メール件数: {len(messages)}")
        results:list[dict] = []
        for message in messages:
            msg = service.users().messages().get(userId="me", id=message["id"]).execute()
            headers = msg["payload"]["headers"]
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(件名なし)")
            sender = next((h["value"] for h in headers if h["name"] == "From"), "(送信者不明)")
            full_body = self.get_full_text(msg["payload"])
            results.append({"headers":headers, "subject":subject, "sender":sender, "full_body":full_body})
        
        return results
