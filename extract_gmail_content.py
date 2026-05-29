from __future__ import annotations
import re
import json
from typing import Dict, List, Tuple, Optional

from ai_extractor import AIExtractor


class ExtractGmailContent(AIExtractor):
    def __init__(
        self,
        filter_path: str = "filters.json",
        ai_api_key_env: str = "GEMINI_API_KEY",
        ai_models: Optional[list[str]] = None,
        ai_timeout: int = 30,
        ai_endpoint_base: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        AIExtractor.__init__(
            self,
            api_key_env=ai_api_key_env,
            models=ai_models,                 # 変更あり
            timeout=ai_timeout,
            endpoint_base=ai_endpoint_base,
        )
        self.fields: Dict[str, str] = {}
        with open(filter_path, "r", encoding="utf-8-sig") as f:
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
        subject = mail_content.get("subject", "")
        sender = mail_content.get("sender", "")

        for group_name, cfg in self.groups.items():
            subjects = cfg.get("subjects", [])
            senders = cfg.get("senders", [])
            extractor = cfg.get("extractor", group_name)

            if self._match_any(subject, subjects) or self._match_any(sender, senders):
                return True, extractor, group_name

        return False, None, None


    def extract(self, keyword: str, body_text: str, subject: str = "") -> Optional[Dict[str, str]]:
        if keyword == "manaba":
            return self._from_manaba(body_text)
        elif keyword == "cels":
            return self._from_cels(body_text, subject=subject)
        else:
            return None


    def _clear_field(self) -> None:
        self.fields = {}


    def _from_manaba(self, body_text: str) -> Dict[str, str]:
        self._clear_field()
        match_notice = re.search(r'に、\[(.+?)\]が.+?されました', body_text)
        if match_notice:
            self.fields['掲示内容'] = match_notice.group(1)

        match_course = re.search(r'\[コース名\]\s*:\s*(.+)', body_text)
        if match_course:
            self.fields['コース名'] = match_course.group(1)

        match_task = re.search(r'\[課題名\]\s*:\s*(.+)', body_text)
        if match_task:
            self.fields['課題名'] = match_task.group(1)

        match_title = re.search(r'\[タイトル\]\s*:\s*(.+)', body_text)
        if match_title:
            self.fields['タイトル'] = match_title.group(1)

        match_author = re.search(r'\[作成者\]\s*:\s*(.+)', body_text)
        if match_author:
            self.fields['作成者'] = match_author.group(1)

        match_due = re.search(r'\[受付終了日時\]\s*:\s*(.+)', body_text)
        if match_due:
            self.fields['受付終了日時'] = match_due.group(1)

        match_url = re.search(r'PC\s*:\s*(https?://\S+)', body_text)
        if match_url:
            self.fields['URL'] = match_url.group(1)

        return self.fields


    def _from_cels(self, body_text: str, subject: str = "") -> Dict[str, str]:
        self._clear_field()

        # LLMに渡すコンテキスト（件名が本文に無いケースを補う）
        context = body_text
        if subject:
            context = f"件名: {subject}\n\n{body_text}"

        schema = {
            "title": "通知の見出し。本文の「表題：」があればそれを優先。無ければ件名の日本語から簡潔に抽出。",
            "genre": "本文に「ジャンル名称：」があればそのままそれを用いる。無ければ短いカテゴリ名で推定。",
            "summary": "要点を日本語で1〜2文。挨拶/自動送信/注意書きは除外。イベントなら日時・場所・登録期限を優先。",
            "url": "最重要URLを1本だけ。公式ページを優先。無ければ空文字。",
        }
        instructions = (
            "Ignore greetings, auto-send notices, signatures, and legal disclaimers.\n"
            "Prefer lines starting with '表題：' and 'ジャンル名称：' when available.\n"
            "If multiple URLs exist, choose the most informative official page (not the general portal).\n"
            "Do NOT include multiple URLs; output only one.\n"
            "Keep the summary fact-based and concise.\n"
        )
        ai_result = self.extract_json(
            context,
            schema,
            instructions=instructions,
            temperature=0.2,
            max_output_tokens=384,
        )

        if ai_result:
            self.fields["title"] = ai_result.get("title", "")
            self.fields["genre"] = ai_result.get("genre", "")
            self.fields["summary"] = ai_result.get("summary", "")
            self.fields["url"] = ai_result.get("url", "")
        else:
            # 最低限のフォールバック
            self.fields["title"] = subject or ""
            self.fields["genre"] = ""
            self.fields["summary"] = (body_text or "")[:120]
            self.fields["url"] = ""

        return self.fields


    def format_for_line(
        self,
        extractor: str,
        sender_label: str,
        info: Dict[str, str],
        index: Optional[int] = None,
        total: Optional[int] = None,
    ) -> str:
        """
        Extract側で送信者依存の整形を吸収する。
        app.py はこの戻り値をまとめて送るだけにする。
        """
        def header() -> str:
            if index is not None and total is not None:
                return f"[{sender_label}]"
            return f"[{sender_label}]"

        if extractor == "cels":
            lines = [
                header(),
                (info.get("title") or "").strip(),
                f"ジャンル名称：{(info.get('genre') or '').strip()}".rstrip("："),
                (info.get("summary") or "").strip(),
                (info.get("url") or "").strip(),
            ]
            # 空行削除（genreが空なら「ジャンル名称：」だけ残さない）
            cleaned = []
            for ln in lines:
                if not ln:
                    continue
                if ln == "ジャンル名称：" or ln == "ジャンル名称：".rstrip("："):
                    continue
                cleaned.append(ln)
            return "\n".join(cleaned)

        # デフォルト（k: v）
        lines = [header()]
        for k, v in info.items():
            v = (v or "").strip()
            if not v:
                continue
            lines.append(f"{k}: {v}")
        return "\n".join(lines)
