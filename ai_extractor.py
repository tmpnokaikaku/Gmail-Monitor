import json
import os
from typing import Dict, Optional, List, Tuple, Any

import requests


class AIExtractor:
    """Gemini-based generic extractor that returns JSON dicts from text.

    - Caller provides `schema` (keys -> description).
    - Caller may provide `instructions` and optional few-shot `examples`.
    - This module contains NO sender-specific logic.
    - Supports multiple model candidates with fallback on quota/rate/unavailable errors.
    """

    def __init__(
        self,
        api_key_env: str = "GEMINI_API_KEY",
        models: Optional[List[str]] = None,
        timeout: int = 30,
        endpoint_base: str = "https://generativelanguage.googleapis.com/v1beta",
        models_env: str = "GEMINI_MODELS",
    ) -> None:
        self.api_key = os.getenv(api_key_env, "")
        self.timeout = timeout
        self.endpoint_base = endpoint_base.rstrip("/")

        # 優先順位付きモデル候補：
        # 1) 引数 models
        # 2) 環境変数 GEMINI_MODELS (カンマ区切り)
        # 3) デフォルト
        if models:
            self.models = models
        else:
            env = (os.getenv(models_env, "") or "").strip()
            if env:
                self.models = [m.strip() for m in env.split(",") if m.strip()]
            else:
                self.models = ["models/gemini-1.5-flash"]

    @staticmethod
    def _normalize_model_name(model: str) -> str:
        """Accept both 'gemini-1.5-flash' and 'models/gemini-1.5-flash'."""
        m = (model or "").strip()
        if not m:
            return ""
        return m if "/" in m else f"models/{m}"

    def _build_prompt(
        self,
        body_text: str,
        schema: Dict[str, str],
        instructions: Optional[str] = None,
        examples: Optional[List[Tuple[str, Dict[str, str]]]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        schema_lines = "\n".join(f"- {k}: {v}" for k, v in schema.items())

        parts: List[str] = []
        if system_prompt:
            parts.append(system_prompt.strip())

        # 汎用の出力制約（用途非依存）
        parts.append(
            "You are an extraction engine.\n"
            "Return ONLY a valid JSON object.\n"
            "Do not use markdown, code fences, or any extra commentary.\n"
            "Use exactly the keys in the schema; no extra keys.\n"
            "If a field is missing, return an empty string for that key.\n"
            "All values must be strings.\n"
        )

        if instructions:
            parts.append("Additional instructions:\n" + instructions.strip() + "\n")

        if examples:
            ex_blocks: List[str] = []
            for i, (ex_in, ex_out) in enumerate(examples, start=1):
                ex_blocks.append(
                    f"Example {i} Input:\n-----BEGIN EXAMPLE INPUT-----\n{ex_in}\n-----END EXAMPLE INPUT-----\n"
                    f"Example {i} Output (JSON):\n{json.dumps(ex_out, ensure_ascii=False)}\n"
                )
            parts.append("\n".join(ex_blocks))

        parts.append("Schema:\n" + schema_lines + "\n")
        parts.append(
            "Text to extract from (between the markers):\n"
            "-----BEGIN TEXT-----\n"
            f"{body_text}\n"
            "-----END TEXT-----"
        )

        return "\n".join(parts)

    @staticmethod
    def _normalize_string_dict(obj: Any, schema: Dict[str, str]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if not isinstance(obj, dict):
            obj = {}
        for k in schema.keys():
            v = obj.get(k, "")
            if v is None:
                v = ""
            if isinstance(v, (list, tuple, dict)):
                v = json.dumps(v, ensure_ascii=False)
            out[k] = str(v)
        return out

    @staticmethod
    def _safe_json_parse(text: str) -> Optional[dict]:
        if not text:
            return None
        text = text.strip()
        try:
            return json.loads(text)
        except Exception:
            pass
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and start < end:
                return json.loads(text[start : end + 1])
        except Exception:
            return None
        return None

    @staticmethod
    def _extract_api_error(resp: requests.Response) -> Tuple[Optional[str], str]:
        """Return (status, message) from Google-style error body if present."""
        try:
            data = resp.json()
            err = data.get("error", {}) if isinstance(data, dict) else {}
            status = err.get("status")
            msg = err.get("message") or ""
            return status, msg
        except Exception:
            return None, ""

    @classmethod
    def _should_fallback(cls, resp: Optional[requests.Response], exc: Optional[Exception]) -> bool:
        """Fallback only on quota/rate/unavailable-like failures."""
        if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
            return True

        if resp is None:
            return False

        # HTTPレベル
        if resp.status_code in (429, 500, 502, 503, 504):
            return True

        # JSONエラーの status を見てフォールバック（403でも quota の場合がある）
        status, _ = cls._extract_api_error(resp)
        if status in ("RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE_EXCEEDED"):
            return True

        return False

    def _call_model_once(
        self,
        model: str,
        prompt: str,
        schema: Dict[str, str],
        temperature: float,
        max_output_tokens: int,
    ) -> Optional[Dict[str, str]]:
        url = f"{self.endpoint_base}/{model}:generateContent"
        params = {"key": self.api_key}

        keys = list(schema.keys())
        response_schema = {
            "type": "OBJECT",
            "properties": {k: {"type": "STRING", "description": schema[k]} for k in keys},
            "required": keys,
        }

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
                "maxOutputTokens": max_output_tokens,
                "temperature": temperature,
            },
        }

        resp: Optional[requests.Response] = None
        try:
            resp = requests.post(url, params=params, json=payload, timeout=self.timeout)
            if not resp.ok:
                # フォールバック可否判定は呼び出し元で
                return {"__http_status__": str(resp.status_code), "__body__": (resp.text or "")[:300]}
            data = resp.json()
        except Exception:
            return None

        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts).strip()
        except Exception:
            return None

        obj = self._safe_json_parse(text)
        if obj is None:
            return None
        return self._normalize_string_dict(obj, schema)

    def extract_json(
        self,
        body_text: str,
        schema: Dict[str, str],
        instructions: Optional[str] = None,
        examples: Optional[List[Tuple[str, Dict[str, str]]]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.2,
        max_output_tokens: int = 512,
    ) -> Optional[Dict[str, str]]:
        if not self.api_key:
            return None

        prompt = self._build_prompt(
            body_text=body_text,
            schema=schema,
            instructions=instructions,
            examples=examples,
            system_prompt=system_prompt,
        )

        # 優先順位順に試す
        last_debug = None
        for raw_model in self.models:
            model = self._normalize_model_name(raw_model)
            if not model:
                continue

            try:
                result = self._call_model_once(
                    model=model,
                    prompt=prompt,
                    schema=schema,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                )
            except Exception as e:
                # ここには通常来ないが念のため
                last_debug = str(e)
                continue

            # 正常な抽出結果
            if isinstance(result, dict) and "__http_status__" not in result:
                return result

            # HTTPエラー風の戻り（_call_model_onceで詰めた）
            if isinstance(result, dict) and "__http_status__" in result:
                # respオブジェクトが無いので、ステータスコードだけで判定（429/5xx想定）
                status = int(result.get("__http_status__", "0") or "0")
                if status in (429, 500, 502, 503, 504):
                    last_debug = f"{model}: http {status}"
                    continue
                # フォールバックしないエラーは打ち切り
                last_debug = f"{model}: http {status} (stop)"
                return None

            # パース失敗などは「モデル違いで改善する可能性」もあるので次へ
            last_debug = f"{model}: parse/other failed"
            continue

        # すべて失敗
        _ = last_debug  # 将来loggerに出す用（今は汎用モジュールにloggerを持たせない）
        return None
