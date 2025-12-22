from __future__ import annotations
import re
import json
from typing import Dict, List, Tuple, Optional


class ExtractGmailContent:
    """メール本文の抽出とフィルタ定義の読み込み。

    filters.json（新仕様）
    {
        "groups": {
            "manaba": {
            "subjects": ["manaba", "【manaba】", "manabaからの通知"],
            "senders": ["@manaba", "no-reply@manaba.jp"],
            "extractor": "manaba"
            }
        }
    }
    """

    def __init__(self, filter_path: str = "filters.json") -> None:
        self.fields: Dict[str, str] = {}
        with open(filter_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "groups" not in data or not isinstance(data["groups"], dict):
            raise ValueError("filters.json がgroups配下ではありません")
        self.groups: Dict[str, Dict[str, List[str]]] = data["groups"]


    def _match_any(self, haystack: str, needles: List[str]) -> bool:
        s = haystack or ""
        s_lower = s.lower()
        for n in needles:
            if not n:
                continue
            if n.lower() in s_lower:
                return True
        return False


    def filter_by_items(self, mail_content: Dict[str, str]) -> Tuple[bool, Optional[str], Optional[str]]:
        """件名・送信者に基づいてグループを決定\n
        戻り値: (is_match, extractor, sender_label)
        - extractor: 抽出器ID（例: "manaba", "cels"）
        - sender_label: グループ名（例: "manaba", "CELS"）
        """
        subject = mail_content.get("subject", "")
        sender = mail_content.get("sender", "")

        for group_name, cfg in self.groups.items():
            subjects = cfg.get("subjects", [])
            senders = cfg.get("senders", [])
            extractor = cfg.get("extractor", group_name)

            if self._match_any(subject, subjects) or self._match_any(sender, senders):
                return True, extractor, group_name

        return False, None, None


    def extract(self, keyword: str, body_text: str) -> Optional[Dict[str, str]]:
        if keyword == "manaba":
            return self.from_manaba(body_text)
        elif keyword == "cels":
            return self.from_cels(body_text)
        else:
            return None


    def _clear_field(self) -> None:
            self.fields = {}


    def from_manaba(self, body_text: str) -> Dict[str, str]:
        self._clear_field()

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

    def from_cels(self, body_text: str) -> Dict[str, str]:
        def extract_japanese(text: str) -> str:
            """スラッシュがあれば左側（日本語）、無ければそのまま"""
            return text.split('/')[0].strip()

        self._clear_field()

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
