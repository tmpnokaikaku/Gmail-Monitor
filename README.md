# Gmail-Monitor

Gmailの未読メールを定期的に取得し、フィルタ条件に一致するメールの要点をLINEに自動転送するツール。

## 概要

大学の学務通知（manaba、CELS等）を見落とさないために作った個人用ツール。
OAuth 2.0でGmail APIと連携し、未読メールをフィルタリングした上で、要点をLINEに通知する。

メール本文からの情報抽出には、ルールベースの正規表現パーサと、Gemini APIを使ったLLMベースの抽出器を併用している。

## 主な技術要素

- **Gmail API連携**: OAuth 2.0認証フロー（初回認証リンクをLINEに送信→ブラウザで認証→コールバックでトークン保存）
- **LINE Messaging API**: Webhook受信 + Push通知送信。送信クォータ管理あり
- **AI抽出 (Gemini API)**: メール本文からJSON形式で構造化情報を抽出。複数モデル候補のフォールバック機構付き
- **フィルタ設定**: `filters.json` で送信元・件名のマッチングルールとExtractor種別を定義
- **コンテナ化**: Dockerfile + Docker Compose。環境変数で設定を注入

## 構成
