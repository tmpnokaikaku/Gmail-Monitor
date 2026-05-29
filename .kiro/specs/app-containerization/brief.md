# Brief: app-containerization

## Problem
開発者はローカルで Gmail Monitor を編集し、OCI 上のプロジェクトディレクトリへ一方向同期して擬似的なリモート開発をしている。現状ではローカル Python と OCI Python、`requirements.txt` と OCI の実 venv、ファイル配置、secret/token の扱いが揃っておらず、ローカルで確認できることが限られている。そのため、変更後の検証が OCI 側に寄り、反映後に初めて依存関係や起動環境の差分に気づくリスクがある。

## Current State
Gmail Monitor は OCI 上で `systemd timer` から one-shot 実行される Python / Flask アプリである。公開経路は `Cloudflare -> nginx -> Flask(127.0.0.1:8080)` で、現在の実行コマンドは概ね `/opt/gmm_project/GmmEnv/bin/python -u app.py` である。アプリ本体は `app.py` を中心に、`gmm_server.py`, `google_service.py`, `line_webhook.py`, `extract_gmail_content.py`, `ai_extractor.py` へ責務が分かれている。

OCI 側 Python は 3.9 系、ローカル側はより新しい Python が使われており、OCI 実 venv には `requirements.txt` より多い依存が入っている可能性がある。`.env`, `credentials.json`, `token.json`, `filters.json`, `log/` は運用上重要だが、特に secret/token はイメージに含めず外部注入または volume/bind mount として扱う必要がある。

## Desired Outcome
アプリ本体を Docker イメージとしてビルドでき、ローカルと OCI で同じ実行環境を使って起動確認できる。ローカルでは外部 API を実際に叩かない範囲の smoke test / import check / 起動確認を行いやすくし、OCI では既存の Cloudflare, nginx, domain, systemd timer を大きく変えずに、Python 直起動部分だけをコンテナ実行へ置き換えられる。

この結果、リモート開発環境は「ローカルで同じコンテナを作って確認し、OCI では同じイメージまたは同じ Dockerfile から起動する」形に近づく。将来の Secrets 管理、DB 化、CI/CD、自動デプロイの土台にもなる。

## Approach
採用アプローチは「アプリ本体のみを最小変更でコンテナ化する」。Dockerfile と必要に応じた compose / run script を追加し、Python runtime、依存関係、作業ディレクトリ、実行コマンドを明示する。Cloudflare, nginx, 現行ドメイン, systemd timer は第一段階では維持し、`gmm.service` の `ExecStart` だけを Docker 実行へ置き換える設計を目指す。

secret/token/config はイメージに含めない。`.env` は env file として注入し、`credentials.json`, `token.json`, `filters.json`, `log/` は bind mount または volume で扱う。`token.json` は実行中に更新されるため、読み取り専用ではなく永続化可能な配置にする。

この方式を選ぶ理由は、現行の公開経路や OAuth 設定を壊さず、実行環境差分を先に潰せるためである。nginx まで含む全面コンテナ化や Secrets 管理 SaaS 導入は、効果はあるが変更範囲が広く、今回の「リモート開発環境を改善する」第一段階としては過剰である。

## Scope
- **In**: アプリ本体用 Dockerfile の追加
- **In**: `.dockerignore` の追加
- **In**: コンテナ内 Python バージョンと依存関係の決定
- **In**: `requirements.txt` と OCI 実環境依存の差分整理
- **In**: ローカル用の build/run/smoke test 手順
- **In**: OCI 上で既存 nginx/systemd timer と接続する実行方式の設計
- **In**: `.env`, `credentials.json`, `token.json`, `filters.json`, `log/` の mount 方針
- **In**: `127.0.0.1:8080` で現行 Flask callback endpoint を維持できることの確認
- **Out**: Cloudflare / nginx の全面的な再設計
- **Out**: systemd timer のスケジュール変更
- **Out**: Secrets 管理 SaaS の導入
- **Out**: DB 導入や `filters.json` の永続層移行
- **Out**: マルチユーザー化
- **Out**: CI/CD や自動デプロイ基盤の本格導入

## Boundary Candidates
- コンテナビルド境界: Dockerfile, `.dockerignore`, dependency install, runtime user/workdir
- ローカル検証境界: import check, smoke test, Flask 起動確認、外部 API を叩かない dry run
- OCI 実行境界: systemd から Docker コンテナを one-shot 起動する方式
- 永続ファイル境界: `.env`, OAuth credentials/token, filters, logs をイメージ外に置く方式
- ネットワーク境界: 既存 nginx が期待する `127.0.0.1:8080` への到達性

## Out of Boundary
- nginx の `/callback` 不整合修正そのもの。ただし Docker 移行前の既知リスクとして記録し、検証項目には含める。
- Google OAuth Console や LINE Developers Console の設定変更。
- `credentials.json` / `token.json` を secret manager に移すこと。
- `filters.json` を DB 化すること。
- アプリを常駐サービスへ変更すること。
- 複数ユーザー対応のためのアプリ設計変更。

## Upstream / Downstream
- **Upstream**: 現行 OCI 配置 `/opt/gmm_project/Gmail-Monitor`
- **Upstream**: 現行 venv `/opt/gmm_project/GmmEnv`
- **Upstream**: `requirements.txt`
- **Upstream**: `.syncignore`
- **Upstream**: `app.py` と runtime modules
- **Upstream**: systemd unit / timer と nginx の既存設定
- **Downstream**: ローカル/リモート開発ワークフロー改善
- **Downstream**: Secrets 管理移行
- **Downstream**: CI/CD または自動デプロイ
- **Downstream**: DB 化とマルチユーザー化
- **Downstream**: OCI 以外の環境への移行

## Existing Spec Touchpoints
- **Extends**: なし。既存の有効 spec はまだ存在しない。
- **Adjacent**: `local-remote-dev-workflow` は一度破棄済みで、Docker 化後に再検討する。Secrets 管理、DB 化、マルチユーザー化は将来の別 spec として扱う。

## Constraints
現行運用を壊さないことを最優先する。第一段階では Cloudflare, nginx, 現行ドメイン, systemd timer を維持し、Python 直起動部分だけをコンテナに置き換える。secret, OAuth token, credentials, log は Docker image に含めない。`token.json` は実行中に更新されるため永続化可能にする。ローカル開発環境は Windows / PowerShell 前提だが、OCI 上では Linux / Docker 実行になるため、手順とファイルパスは両環境の差分を明示する。
