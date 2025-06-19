from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

import os
import json
import base64
from dotenv import load_dotenv

from get_info import extract_manaba, extract_cels


# 読み取り専用のスコープ
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# google credentials 読み込み
load_dotenv()
GOOGLE_CREDS_RAW = os.getenv("GOOGLE_CREDS")
GOOGLE_CREDS_JSON = base64.b64decode(GOOGLE_CREDS_RAW).decode("utf-8")
GOOGLE_CREDS = Credentials.from_authorized_user_info(json.loads(GOOGLE_CREDS_JSON))

# 設定
FETCH_MAX = 5


def get_gmail_service():
    creds = GOOGLE_CREDS
    if creds is None:
        # 初回認証
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        #save_google_credentials(user_id, creds.to_json())
        os.environ["GOOGLE_CREDS"] = base64.b64encode(creds.to_json())
    elif not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Credentialのリフレッシュ失敗: {e}")
                # 再認証を実施
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                creds = flow.run_local_server(port=0)
                os.environ["GOOGLE_CREDS"] = base64.b64encode(creds.to_json())
        else:
            # refresh_token すらない場合：認証フロー強制
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
            os.environ["GOOGLE_CREDS"] = base64.b64encode(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def get_full_text(payload):
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
    else:
        body_data = payload["body"].get("data")
        if body_data:
            return base64.urlsafe_b64decode(body_data).decode("utf-8")
    return "(本文なし)"


def load_filters_from_json(file_path="filters.json"):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("subjects", []), data.get("senders", [])


def fetch_and_filter_emails(subject_keywords="", sender_keywords="")->list[str]:
    service = get_gmail_service()
    results = service.users().messages().list(userId="me", maxResults=FETCH_MAX).execute()
    messages = results.get("messages", [])

    print(f"受信メール件数: {len(messages)}")
    results = []
    for message in messages:
        msg = service.users().messages().get(userId="me", id=message["id"]).execute()
        headers = msg["payload"]["headers"]
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(件名なし)")
        sender = next((h["value"] for h in headers if h["name"] == "From"), "(送信者不明)")
        full_body = get_full_text(msg["payload"])


        # フィルター条件にマッチしたら表示
        if (
            any(keyword in subject for keyword in subject_keywords) or
            any(keyword in sender for keyword in sender_keywords)
        ):
            """
            print("==== マッチしたメール ====")
            #print(f"件名: {subject}")
            #print(f"送信者: {sender}")
            #print(f"本文: {full_body}\n")
            if "manaba" in sender:
                info = extract_manaba(full_body)
                for key, value in info.items():
                    print(f"{key}: {value}")
            elif "cels" in sender:
                print(f"本文: {full_body}\n")
            """
            text = ""
            if "manaba" in sender:
                info = extract_manaba(full_body)
                for key, value in info.items():
                    text += f"{key}: {value}\n"
            elif "cels" in sender:
                info = extract_cels(full_body)
                for key, value in info.items():
                    text += f"{key}: {value}\n"
            else:
                text = None
            results.append(text)

    return results
