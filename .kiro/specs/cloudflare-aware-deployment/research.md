# Research & Design Decisions

## Summary
- **Feature**: `cloudflare-aware-deployment`
- **Discovery Scope**: Extension / Complex Integration
- **Key Findings**:
  - 既存 `app-containerization` は Docker image、runtime mount、`scripts/container_check.py`、host loopback publish、rollback 手順の土台を提供している。
  - GHCR は Docker/OCI image を扱え、GitHub Actions からの publish は `GITHUB_TOKEN`、OCI 側の private image pull は `read:packages` 相当の認証が必要になる。
  - Docker image は tag だけでなく digest で固定できるため、本番反映は human-readable tag と immutable digest の両方を記録する設計にする。
  - Cloudflare proxied Web ドメインは HTTP/HTTPS 入口として維持し、SSH/deploy 管理経路は DNS-only hostname または Cloudflare Tunnel / Access として分離する。

## Research Log

### 既存 Docker 化成果物
- **Context**: この仕様は Docker 化の後続運用であり、既存成果物を前提にする必要がある。
- **Sources Consulted**:
  - `.kiro/specs/app-containerization/design.md`
  - `Dockerfile`
  - `compose.yaml`
  - `scripts/container_check.py`
  - `docs/app-containerization.md`
- **Findings**:
  - `Dockerfile` は `python:3.9-slim` を使い、アプリ module と `scripts/` を image に入れる。
  - `compose.yaml` は `gmail-monitor` と `check` service を定義し、runtime files を `/runtime` に bind mount する。
  - `scripts/container_check.py` は import、runtime file、Flask route、`/health` を検証し、Gmail fetch、LINE push、Gemini API call は行わない。
  - 既存 docs は OCI 側で source を同期して build する前提を含む。
- **Implications**:
  - 新仕様は source build を本線にせず、registry image を pull して同じ runtime mount contract で check/run する。
  - 既存 check script を OCI preflight の中心に据え、アプリ本体の追加変更を避ける。

### Registry と image 固定
- **Context**: 本番反映単位を source tree から image artifact に変えるため、registry と image identifier の扱いを確認した。
- **Sources Consulted**:
  - [GitHub Docs: Working with the Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
  - [Docker Docs: docker image pull](https://docs.docker.com/reference/cli/docker/image/pull/)
- **Findings**:
  - GHCR は Docker Image Manifest V2 と OCI image をサポートする。
  - GitHub Actions workflow から repository に紐づく package を publish する場合は `GITHUB_TOKEN` を使える。
  - private/internal package を別環境から install/pull する場合は適切な package read 権限を持つ credential が必要になる。
  - Docker は tag pull に加え、digest pull で特定 image version を固定できる。
  - Docker は pull/push 時に digest を表示し、registry credentials は `docker login` で管理される。
- **Implications**:
  - workflow は `ghcr.io/<owner>/<image>:<tag>` を publish し、OCI 側は tag と digest を deploy manifest に記録する。
  - systemd 実行対象は最終的に digest 付き参照へ固定できる設計にする。
  - credential 値は docs/spec に書かず、OCI host 上の Docker credential store または環境入力として扱う。

### Cloudflare 管理経路
- **Context**: Cloudflare proxied DNS 配下で SSH/rsync が不安定になる問題を設計境界として扱う。
- **Sources Consulted**:
  - [Cloudflare Docs: Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/)
  - [Cloudflare One Docs: Connect to SSH with client-side cloudflared](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/use-cases/ssh/ssh-cloudflared-authentication/)
- **Findings**:
  - Cloudflare Tunnel は origin から Cloudflare への outbound connection を使い、inbound port を公開せずに HTTP、TCP、SSH などを公開できる。
  - client-side `cloudflared` による SSH 接続では server/client の両方に `cloudflared` が必要で、Access credentials による認証を組み合わせられる。
  - Cloudflare Tunnel は Web 公開経路と管理経路を分ける選択肢になるが、初期導入負荷は DNS-only SSH hostname より高い。
- **Implications**:
  - 本仕様は管理経路として DNS-only SSH hostname と Cloudflare Tunnel の両方を許容する。
  - 実装の本線は registry pull なので、管理経路は deploy control plane の選択肢として docs と preflight に留める。

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| SyncNow 継続 | rsync で source tree を OCI へ同期し、OCI で build する | 小変更で現行に近い | Cloudflare/DNS 変更に弱く、同期漏れや secret 誤同期のリスクが残る | 不採用。本線から外す |
| Registry pull manual deploy | image を GHCR に push し、OCI で pull/check/activate する | Docker 化成果物を活かせる。手動でも再現可能 | registry auth と tag/digest 管理が必要 | 採用 |
| Full CI/CD deploy | CI が SSH/Tunnel 経由で OCI activate まで行う | 自動化が進む | 初期スコープが広く、credential 管理が重い | 後続候補 |
| Cloudflare Tunnel first | SSH 管理経路を Tunnel 化して deploy もそこへ寄せる | inbound SSH を閉じられる | cloudflared と Access 設定が増える | 管理経路の選択肢として扱う |

## Design Decisions

### Decision: Registry pull manual deploy を第一段階にする
- **Context**: 完全な CI/CD は要件外だが、source 同期から image artifact 中心へ移す必要がある。
- **Alternatives Considered**:
  1. SyncNow 継続
  2. GHCR publish + OCI manual pull
  3. GitHub Actions から OCI へ直接 deploy
- **Selected Approach**: GHCR publish workflow と OCI deploy script を分け、OCI 側で pull、check、activate、rollback を行う。
- **Rationale**: 手動でも CI でも同じ image を使える。既存 `container_check.py` と runtime mount contract を再利用できる。
- **Trade-offs**: registry auth と digest 記録の手順が増える。
- **Follow-up**: OCI host で Docker login と package read 権限を検証する。

### Decision: tag と digest の両方を記録する
- **Context**: tag は読みやすいが mutable であり、本番再現性には immutable identifier が必要。
- **Alternatives Considered**:
  1. tag のみ
  2. digest のみ
  3. tag と digest の両方
- **Selected Approach**: publish は tag を使い、OCI deploy manifest には resolved digest を保存する。
- **Rationale**: 運用者が release を識別しやすく、rollback 時は正確な image を再取得できる。
- **Trade-offs**: digest 解決と manifest 保存の処理が必要。
- **Follow-up**: deploy script で local image inspect により digest を取得できることを検証する。

### Decision: 管理経路は Web 公開経路から独立させる
- **Context**: Cloudflare proxied Web domain を SSH/rsync 接続先として使うと origin へ直接到達できない。
- **Alternatives Considered**:
  1. Web domain を DNS-only に戻す
  2. SSH 専用 DNS-only hostname を使う
  3. Cloudflare Tunnel / Access を使う
- **Selected Approach**: Web domain は proxied のまま維持し、管理経路は DNS-only hostname または Tunnel として独立させる。
- **Rationale**: Web 公開経路を壊さず、デプロイ制御の選択肢を残せる。
- **Trade-offs**: 管理経路ごとに preflight が異なる。
- **Follow-up**: 実運用で選ぶ管理経路を docs の checklist で明示する。

## Risks & Mitigations
- GHCR private package pull が OCI で失敗する — Docker login 手順と read 権限確認を preflight に入れる。
- tag が後から上書きされる — deploy manifest に digest を記録し、activate は digest 参照を優先できるようにする。
- secret が image または workflow log に漏れる — `.dockerignore` を更新し、workflow/docs に secret 値を出力しない方針を明記する。
- new image の check は通るが本番 callback が壊れる — activate 前後に host loopback と nginx callback の確認を入れる。
- Cloudflare 管理経路の選択が未確定 — DNS-only SSH と Tunnel の preflight を docs に分けて記載する。

## References
- [GitHub Docs: Working with the Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry) — GHCR auth、push、pull、digest pull。
- [Docker Docs: docker image pull](https://docs.docker.com/reference/cli/docker/image/pull/) — tag/digest pull と registry credential の前提。
- [Cloudflare Docs: Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/) — outbound tunnel と SSH/TCP 対応。
- [Cloudflare One Docs: Connect to SSH with client-side cloudflared](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/use-cases/ssh/ssh-cloudflared-authentication/) — SSH 管理経路の Tunnel 構成。
