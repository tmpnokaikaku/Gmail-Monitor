# Product Overview

Gmail Monitor は、未読 Gmail を確認し、指定した送信者や件名に合うメールだけから有用な情報を抽出して、個人の LINE アカウントへ簡潔に通知する個人向け通知サービスです。常時稼働する公開 Web アプリではなく、定期実行される one-shot 自動化として設計されています。

## Core Capabilities

- Google OAuth と Gmail read-only scope による未読メール取得。
- 設定可能な送信者・件名グループによる対象メールの絞り込み。
- 形式が安定しているメールは決定的なルールで、揺れがあるメールは Gemini ベースの JSON 抽出で構造化。
- LINE の送信クォータを確認したうえで、フィルタ済み要約を push 通知。
- OAuth と LINE Webhook に必要な callback endpoint だけを Flask で提供。

## Target Use Cases

- 大学、授業、事務連絡などの個人向け通知の監視。
- 受信箱を直接確認する頻度を減らし、実用的なメール要約だけを LINE に流す。
- サーバー上の timer から定期起動し、処理完了後に終了する運用。
- 送信者ごとの通知ルールを単純なフィルタ設定として保守する運用。

## Value Proposition

このシステムは汎用メールクライアントではなく、小さく監査しやすい自動化パイプラインを重視します。中心となる振る舞いは次の流れです。

`timer start -> Flask callback readiness -> Gmail fetch -> filter -> extract -> LINE push -> process exit`

単一ユーザー運用では、マルチユーザー機能よりも信頼性、運用負荷の低さ、外部サービス境界の明確さを優先します。

## Operational Context

本番運用では、次のような HTTPS reverse proxy 経路の背後で動く前提です。

`Cloudflare -> nginx -> Flask on 127.0.0.1:8080`

Cloudflare、nginx、OAuth redirect 設定、LINE Webhook 設定、環境変数、token ファイルは運用環境の一部です。仕様で明示的に変更しない限り、プロダクト変更はこのデプロイ形態と整合させます。

---
_目的とパターンを記録し、機能一覧を網羅しない。_
