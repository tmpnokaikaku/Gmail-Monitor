# Gap Analysis: app-containerization

作成日時: 2026-05-12T10:58:17+09:00

## Summary

`app-containerization` は既存アプリ構造に対して実現可能であり、主な不足は Docker 関連成果物、ローカル検証入口、OCI 実行手順、外部注入する永続ファイルの整理である。アプリ本体は `app.py` を実行入口とする flat な Python/Flask 構成で、既存の `127.0.0.1:8080` 待受と one-shot 実行の前提は Docker 化に利用できる。

一方で、現状の `app.py` は起動後に Gmail 認証、Gmail 取得、LINE 送信へ進むため、外部 API を叩かないローカル smoke test にはそのまま使いにくい。`test/app.py` は nginx/proxy 経路確認用の簡易 Flask アプリであり、本番アプリの import/check や dry-run を保証するものではない。

既存調査メモでは OCI 側 Python は 3.9.21、ローカルは Python 3.13.3、OCI の `GmmEnv` には `requirements.txt` より多い依存が存在する可能性が示されている。Docker 化では Python バージョンと依存定義を設計時に確定する必要がある。

## Current State Investigation

### Existing Assets

- `app.py`: 本番 one-shot 実行入口。`AppConfig` と `GmailMonitor` を定義し、Flask 起動、Gmail 認証、Gmail 取得、抽出、LINE push までを実行する。
- `gmm_server.py`: Flask app、ProxyFix、共通 logger、`/health` と `/` の軽量 endpoint、`127.0.0.1:{port}` での Flask 起動を担当する。
- `google_service.py`: OAuth endpoint (`/oauth/start`, `/oauth/callback`)、`token.json` 読み書き、Gmail REST 取得を担当する。
- `line_webhook.py`: `.env` 読み込み、LINE token/secret/user id、`/callback`、LINE quota check、push/reply を担当する。
- `extract_gmail_content.py`: `filters.json` 読み込み、メールフィルタ、抽出、LINE 向け整形を担当する。
- `ai_extractor.py`: Gemini API 呼び出しと JSON 正規化を担当する。
- `test/app.py`: nginx/proxy と callback 経路を確認するための簡易 Flask アプリ。本番アプリの smoke test ではない。
- `requirements.txt`: 直接依存のみが記録されている。
- `.gitignore`: `.env`, `credentials.json`, `token.json` は除外済み。
- `.syncignore`: `token.json`, `log/`, `user_notes/`, `.venv/` などは同期除外済み。ただし `credentials.json` と `filters.json` は現状同期対象になり得る。

### Runtime and Operation Notes

既存メモによる現行運用:

- OCI 作業ディレクトリ: `/opt/gmm_project/Gmail-Monitor`
- 既存実行コマンド: `/opt/gmm_project/GmmEnv/bin/python -u app.py`
- 公開経路: `Cloudflare -> nginx -> Flask(127.0.0.1:8080)`
- systemd timer から one-shot 実行
- `.env`, `credentials.json`, `token.json`, `filters.json`, `log/` が運用上重要
- `token.json` は実行中に更新されるため read-only mount にはできない
- LINE Developers Console は `/callback` を向いているが、既存 nginx 側に `/callback` location がない可能性がある

### Existing Conventions

- Flat root module layout。package 化はされていない。
- sibling import を直接使う。
- 設定は環境変数、`.env`、root 直下 JSON ファイルで扱う。
- logger は stdout と任意の `GMM_LOG_FILE` の両方へ出せる。
- provider-specific logic は `line_webhook.py`, `google_service.py`, `ai_extractor.py` に分離されている。

## Requirement-to-Asset Map

### Requirement 1: コンテナイメージとしての再現性

- Existing assets: `requirements.txt`, root Python modules, `.gitignore`
- Gaps:
  - Missing: `Dockerfile`
  - Missing: `.dockerignore`
  - Missing: コンテナ内 Python バージョン方針
  - Unknown: OCI 実 venv の依存差分をどこまで `requirements.txt` に反映するか
  - Constraint: 現状ローカル Python 3.13.3 と OCI Python 3.9.21 に差がある

### Requirement 2: 機密情報と永続ファイルの外部注入

- Existing assets: `.gitignore`, `.syncignore`, `line_webhook.py`, `google_service.py`, `gmm_server.py`
- Gaps:
  - Missing: Docker 実行時の env file / bind mount 仕様
  - Missing: `credentials.json`, `token.json`, `filters.json`, `log/` の container path と host path の対応表
  - Missing: `token.json` 書き込み権限の確認手順
  - Constraint: `.syncignore` は `token.json` を除外するが `credentials.json` は除外していない
  - Constraint: `google_service.py` は `token.json` を `0o600` で作成/更新する

### Requirement 3: ローカル検証性

- Existing assets: `test/app.py`, AST parse で対象 runtime modules は構文上 OK
- Gaps:
  - Missing: 本番 app modules の import check コマンド
  - Missing: 外部 API を叩かない dry-run/smoke test entrypoint
  - Missing: Docker 経由の Flask 起動確認手順
  - Constraint: `app.py main()` は実行すると Gmail/LINE/OAuth に進む
  - Constraint: `line_webhook.py` import/construct 時に LINE SDK 設定が必要になるため、空 env での挙動確認が必要

### Requirement 4: OCI 既存運用との互換性

- Existing assets: `gmm_server.py` は `127.0.0.1:8080` で Flask を起動する。既存メモに systemd unit/timer と `ExecStart` 情報あり。
- Gaps:
  - Missing: Docker run を systemd one-shot として呼ぶ運用手順
  - Missing: container lifecycle と終了コードの整理
  - Missing: rollback 手順
  - Unknown: OCI に Docker Engine / compose plugin が導入済みか
  - Constraint: Flask は container 内で `127.0.0.1` bind だと host nginx から直接到達できない可能性がある。設計で host network または bind host を検討する必要がある。

### Requirement 5: 既存公開経路と外部サービス設定の維持

- Existing assets: `google_service.py` は `/oauth/start`, `/oauth/callback` を維持。`line_webhook.py` は `/callback` を維持。
- Gaps:
  - Missing: コンテナ起動後に host/nginx から OAuth callback と LINE callback の到達性を確認する手順
  - Unknown: nginx の `/callback` 不整合を Docker 移行前に修正するか、既知リスクとして切り分けるか
  - Constraint: `credentials.json` には古い ngrok redirect URI が残っているが、コードは `SERVER_DOMAIN` から redirect URI を生成している

### Requirement 6: 範囲外変更の抑制

- Existing assets: brief/requirements で scope は分離済み
- Gaps:
  - Missing: design/tasks で Secrets 管理、DB 化、CI/CD を実装対象に含めない明示的な境界
  - Constraint: Docker 化の過程で `.env`/secret 整理に踏み込みすぎるリスクがある

## Implementation Approach Options

### Option A: Dockerfile だけを追加する最小構成

`Dockerfile` と `.dockerignore` を追加し、既存 `app.py` をそのまま `python -u app.py` で実行する。OCI 側 systemd は `docker run` を呼ぶ形に置き換える。

Pros:
- 変更範囲が最小
- 既存アプリコードをほぼ触らない
- rollback が比較的容易

Cons:
- ローカル smoke test は弱いまま
- `app.py` 起動で外部 API へ進むため、検証が本番寄りになる
- host nginx から container 内 Flask への到達方式を慎重に決める必要がある

Effort: S-M  
Risk: Medium

### Option B: コンテナ化と dry-run/check entrypoint を追加する

`Dockerfile`, `.dockerignore` に加え、外部 API を叩かない import check / config check / Flask 起動確認用の小さな entrypoint または script を追加する。本番 `app.py` の one-shot 動作は維持する。

Pros:
- Requirement 3 を満たしやすい
- ローカルと OCI の両方で同じイメージを検証しやすい
- 本番実行と検証実行を分けられる

Cons:
- 追加 script の責務設計が必要
- 既存コードの import/初期化副作用を整理する可能性がある
- テスト用 entrypoint と本番 entrypoint の乖離に注意が必要

Effort: M  
Risk: Medium-Low

### Option C: コンテナ化に合わせて設定/永続ファイルの構造も整理する

コンテナ化と同時に、設定ファイルの配置ディレクトリ、token/log/filter の path 設定、mount 前提のディレクトリ構造を明確化し、必要に応じて `AppConfig` の path を環境変数化する。

Pros:
- 永続ファイルの扱いが明確になる
- 将来の Secrets 管理や DB 化の前提を作りやすい
- root 直下ファイル依存を緩和できる

Cons:
- 第一段階としては変更範囲が広い
- 現行 OCI 運用との差分が増える
- OAuth token 更新や filters 読み込みの既存動作に影響しやすい

Effort: M-L  
Risk: Medium

## Preferred Direction for Design Phase

推奨は Option B をベースにし、永続ファイルの mount 方針だけ Option C から最小限取り込む hybrid approach である。

理由:

- Docker 化だけでは requirements のローカル検証性を満たしにくい。
- 既存 `app.py` を大きく変えずに本番 one-shot は維持できる。
- import check / smoke test / Flask 起動確認を script 化すれば、リモート開発環境改善に直接効く。
- `.env`, `credentials.json`, `token.json`, `filters.json`, `log/` の mount 方針は design で決めないと、本番移行時に手戻りが出る。

## Research Needed for Design

- OCI に Docker Engine または compose plugin が導入済みか。
- systemd から `docker run --rm ...` を呼ぶか、compose を使うか。
- container 内 Flask bind address をどうするか。現状コードは `127.0.0.1` 固定で、Docker bridge network では host nginx から到達できない可能性がある。
- Python base image を 3.9 系に寄せるか、より新しいバージョンに上げるか。
- OCI 実 venv の `pip freeze` を `requirements.txt` にどこまで反映するか。
- `/callback` nginx 不整合を Docker 移行前に別対応するか、移行手順内の検証リスクとして扱うか。
- Windows ローカルで Docker Desktop を使う前提か、WSL/Docker Engine を使う前提か。

## Complexity and Risk

Overall effort: M  
理由: Dockerfile 追加だけなら小さいが、外部ファイル mount、OCI systemd 連携、smoke test、host/container network の設計が必要。

Overall risk: Medium  
理由: アプリ自体は小さいが、OAuth token 永続化、host nginx から container への到達、既存 `/callback` 不整合、依存関係差分が移行リスクになる。

## Notes from Validation

- `python --version` on local returned `Python 3.13.3`.
- AST parse for `app.py`, `gmm_server.py`, `google_service.py`, `line_webhook.py`, `extract_gmail_content.py`, `ai_extractor.py` passed.
- `python -m py_compile` could not complete because Windows denied writes/renames in `__pycache__` and later in a temporary pycache prefix. This appears to be a local filesystem permission issue, not a syntax error.
- Cleanup of the temporary `tmp/pycache-check` directory also failed due to Windows access denial and may require manual cleanup or permission adjustment.

---

# Design Discovery Update

作成日時: 2026-05-12T11:17:47+09:00

## Summary

- **Feature**: `app-containerization`
- **Discovery Scope**: Extension / Complex Integration
- **Key Findings**:
  - Docker 化は既存アプリ構造の延長で実装できるが、network bind と永続ファイル mount は設計で明示する必要がある。
  - host network は Linux 上の Docker Engine では有効だが、Docker Desktop では制約があり、ローカル検証との一貫性を下げる。
  - bind mount はホスト上の既存ファイルを直接扱えるため、現行の `.env`, `credentials.json`, `token.json`, `filters.json`, `log/` を段階移行する第一段階に適している。

## Research Log

### Docker network mode

- **Context**: 現行 Flask は `127.0.0.1:8080` に bind し、nginx は host の `127.0.0.1:8080` へ proxy している。コンテナ内の `127.0.0.1` は host と別 namespace になるため、network 設計が必要。
- **Sources Consulted**:
  - Docker Docs: Network drivers
  - Docker Docs: Host network driver
- **Findings**:
  - Docker の default bridge では container と host は別 network namespace になる。
  - host network は container が host networking namespace を共有する方式で、Linux Docker Engine では使える。
  - host network では port publishing が効かず、Docker Desktop では version/setting 依存の制約がある。
- **Implications**:
  - 第一候補は host network ではなく、コンテナ内 Flask を `0.0.0.0:8080` に bind し、host 側 `127.0.0.1:8080` へ publish する方式にする。
  - `gmm_server.py` は bind host を環境変数で変更できる必要がある。

### Persistent files and mounts

- **Context**: `.env`, `credentials.json`, `token.json`, `filters.json`, `log/` はイメージに含めず、特に `token.json` は実行中に更新される。
- **Sources Consulted**:
  - Docker Docs: Bind mounts
  - Docker Docs: Volumes
- **Findings**:
  - bind mount は host path を container path に直接 mount できる。
  - bind mount は既存 host ファイルを扱いやすいが host directory 構造に依存する。
  - volume は Docker 管理の永続領域で backup/migration しやすいが、host から直接ファイルを扱う現行運用とは距離がある。
- **Implications**:
  - 第一段階では bind mount を採用する。
  - `credentials.json` と `filters.json` は read-only mount、`token.json` と `log/` は writable mount に分ける。
  - 後続の Secrets 管理/DB 化で volume や secret provider への移行を再検討する。

### Python base image and dependency strategy

- **Context**: OCI は Python 3.9.21、ローカルは Python 3.13.3。依存関係は OCI 実 venv と `requirements.txt` に差分がある可能性がある。
- **Sources Consulted**:
  - Docker Hub: Python Official Image
- **Findings**:
  - Python official image は `requirements.txt` を install して app を実行する標準的な Dockerfile パターンを提供している。
  - `python:<version>-slim` は軽量だが、source build が必要な package では追加 OS package が必要になる場合がある。
- **Implications**:
  - 第一段階では OCI 実行環境に寄せて Python 3.9 系を選ぶ。
  - build 失敗が出た場合は slim image へ OS package を足すか、non-slim image へ戻す判断を design/task で扱う。

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Minimal Docker wrapper | 既存 `app.py` をそのまま container command にする | 変更が少ない | smoke test と network 問題が残る | 単体では requirements 不足 |
| Docker plus validation entrypoint | 本番 entrypoint と検証 entrypoint を分ける | ローカル/OCI 検証性が上がる | 小さな script 追加が必要 | 採用候補 |
| Runtime configuration refactor | path, host, port を環境変数化して container 前提を明確化 | mount と network の制御が明確 | 変更範囲がやや広がる | 最小範囲で採用 |

## Design Decisions

### Decision: bridge network with loopback port publishing

- **Context**: nginx は host loopback の `127.0.0.1:8080` を期待する一方、container 内 `127.0.0.1` は host から直接見えない。
- **Alternatives Considered**:
  1. host network を使う。
  2. container を `0.0.0.0` に bind し、host `127.0.0.1:8080` に publish する。
- **Selected Approach**: `GMM_FLASK_HOST=0.0.0.0` を container で指定し、host 側は `127.0.0.1:8080:8080` として publish する。
- **Rationale**: OCI Linux とローカル Docker Desktop の両方で検証しやすく、host network の platform 差を避けられる。
- **Trade-offs**: `gmm_server.py` に bind host の設定追加が必要。
- **Follow-up**: OCI 上で `curl http://127.0.0.1:8080/health` と nginx 経由の callback 到達性を確認する。

### Decision: bind mounts for first-stage persistence

- **Context**: 現行運用は root 直下の JSON/token/log ファイルを前提にしている。
- **Alternatives Considered**:
  1. Docker volume に移す。
  2. bind mount で現行 host files を container path に接続する。
- **Selected Approach**: 第一段階では bind mount を採用する。
- **Rationale**: 既存ファイル配置を保ち、rollback しやすい。
- **Trade-offs**: host path 依存が残る。
- **Follow-up**: 後続 Secrets 管理/DB 化 spec で再評価する。

### Decision: validation script instead of altering one-shot runtime

- **Context**: 本番 `app.py` は起動後に外部 API へ進むため、ローカル検証に向かない。
- **Alternatives Considered**:
  1. `app.py` に dry-run mode を埋め込む。
  2. `scripts/container_check.py` を追加し、import/config/flask route の軽量確認を担わせる。
- **Selected Approach**: 小さな validation script を追加する。
- **Rationale**: 本番 one-shot runtime への影響を避けつつ、requirements のローカル検証性を満たせる。
- **Trade-offs**: 本番 entrypoint と検証 entrypoint の乖離をテストで監視する必要がある。
- **Follow-up**: script は本番 `GmailMonitor` の初期化または route 登録を外部 API なしで確認できる範囲に限定する。

## Risks & Mitigations

- Host nginx から container に到達できないリスク: `GMM_FLASK_HOST=0.0.0.0` と host loopback publish を採用し、OCI で `curl` 検証する。
- `token.json` 書き込み失敗リスク: writable bind mount と file permission check を smoke test に含める。
- 依存関係差分リスク: Python 3.9 系 base image と OCI `pip freeze` 差分確認を task 化する。
- `/callback` 不整合リスク: Docker 移行前 validation checklist に明記し、この spec では nginx 修正を所有しない。

## References

- [Docker network drivers](https://docs.docker.com/engine/network/drivers/) - bridge/host network の基本整理
- [Docker host network driver](https://docs.docker.com/engine/network/tutorials/host/) - host network の platform support と制約
- [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/) - host files を container へ mount する方式
- [Docker volumes](https://docs.docker.com/engine/storage/volumes/) - Docker 管理永続領域との比較
- [Python Official Image](https://hub.docker.com/_/python/) - Python Dockerfile パターンと slim image 注意点
