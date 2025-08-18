import re
import json


class ExtractGmailContent():
    def __init__(self, filter_path:str ="filters.json",):
        self.fields = {}

        with open(filter_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.filter = (data.get("subjects", []), data.get("senders", []))

    
    def clear_result(self):
        # 空の辞書で上書き
        self.fields = {}


    def filter_by_items(self, mail_content:dict):
        subject_keywords, sender_keywords = self.filter

        subject = mail_content["subject"]
        sender = mail_content["sender"]

        if (
            any(keyword in subject for keyword in subject_keywords) or
            any(keyword in sender for keyword in sender_keywords)
        ):
            return True, "manaba"   # カッコ仮
        else:
            return False, "manaba"


    def extract(self, keyword:str, body_text):
        if keyword == "manaba":
            return self.from_manaba(body_text)
        elif keyword == "cels":
            return self.from_cels(body_text)
        else:
            return None


    def from_manaba(self, body_text):
        self.clear_result()

        # 掲示された内容
        match_notice = re.search(r'に、\[(.+?)\]が.+?されました', body_text)
        if match_notice:
            self.fields['掲示内容'] = match_notice.group(1)

        # コース名
        match_course = re.search(r'\[コース名\]\s*:\s*(.+)', body_text)
        if match_course:
            self.fields['コース名'] = match_course.group(1)

        # 課題名
        match_task = re.search(r'\[課題名\]\s*:\s*(.+)', body_text)
        if match_task:
            self.fields['課題名'] = match_task.group(1)

        # タイトル
        match_title = re.search(r'\[タイトル\]\s*:\s*(.+)', body_text)
        if match_title:
            self.fields['タイトル'] = match_title.group(1)

        # 作成者
        match_author = re.search(r'\[作成者\]\s*:\s*(.+)', body_text)
        if match_author:
            self.fields['作成者'] = match_author.group(1)

        # 受付終了日時
        match_due = re.search(r'\[受付終了日時\]\s*:\s*(.+)', body_text)
        if match_due:
            self.fields['受付終了日時'] = match_due.group(1)

        # ログインURL
        match_url = re.search(r'PC\s*:\s*(https?://\S+)', body_text)
        if match_url:
            self.fields['URL'] = match_url.group(1)

        return self.fields


    def from_cels(self, body_text):
        def extract_japanese(text):
            """スラッシュがあれば左側（日本語）、無ければそのまま"""
            return text.split('/')[0].strip()
        
        self.clear_result()

        # ジャンル名称
        match_genre = re.search(r'ジャンル名称：(.+)', body_text)
        if match_genre:
            self.fields['ジャンル名称'] = extract_japanese(match_genre.group(1).strip())

        # 表題
        match_title = re.search(r'表題：(.+)', body_text)
        if match_title:
            self.fields['表題'] = extract_japanese(match_title.group(1).strip())

        # 内容（基本的に日本語のみだが念のため）
        match_content = re.search(r'内容：(.+?)(?:掲示者所属名称|URL|添付有無|詳細はCELS|$)', body_text, re.DOTALL)
        if match_content:
            self.fields['内容'] = extract_japanese(match_content.group(1).strip())

        # 掲示者所属名称
        match_affil = re.search(r'掲示者所属名称：(.+)', body_text)
        if match_affil:
            self.fields['掲示者所属名称'] = extract_japanese(match_affil.group(1).strip())

        # 掲示者
        match_author = re.search(r'掲示者：(.+)', body_text)
        if match_author:
            self.fields['掲示者'] = extract_japanese(match_author.group(1).strip())

        # URL
        match_url = re.search(r'(https?://[^\s]+)', body_text)
        if match_url:
            self.fields['URL'] = match_url.group(1)

        return self.fields
