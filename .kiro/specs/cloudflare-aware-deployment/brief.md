# Brief: cloudflare-aware-deployment

## Problem
開発者兼運用者が、Cloudflare 配下の公開ドメインを導入した後に、従来の `SyncNow` による SSH/rsync 同期が不安定または接続不能になる問題を抱えている。Cloudflare の proxied DNS は HTTP/HTTPS 公開経路には適しているが、通常の SSH/rsync の接続先としてそのまま使うと Cloudflare の anycast IP に向かい、OCI origin の port 22 へ直接到達できない。

## Current State
既存の `app-containerization` 仕様により、Gmail Monitor は Docker image として build/check/run できる土台を持つ。現行の `SyncNow` は WSL 上の rsync で source tree を OCI の `/opt/gmm_project/Gmail-Monitor/` へ同期する形だが、Cloudflare を噛ませた公開ドメインと SSH 接続先の責務が混ざっている。

OCI 側では `ss -tulpn | grep :22` により sshd が `0.0.0.0:22` と `[::]:22` で listen していることが確認されている。ただしこれは OS 内の待受確認であり、外部到達性は OCI Security List / NSG、DNS レコード種別、Cloudflare proxy 状態に依存する。

## Desired Outcome
Cloudflare の HTTP/HTTPS 公開経路を維持しながら、Gmail Monitor のデプロイを source file 同期中心から Docker image artifact 中心へ移行できる。ローカルまたは CI で build された image を registry に push し、OCI 側はその image を pull して検証・起動・rollback できる。

## Approach
選択した方針は Docker image registry 経由のデプロイである。ローカルまたは GitHub Actions などで `Dockerfile` から image を build し、GHCR 等の container registry に tag 付きで push する。OCI 側では source tree の rsync を本線にせず、`docker pull`、`docker compose run --rm check` 相当の検証、systemd one-shot 実行対象 image の更新を行う。

SSH はデプロイ制御のために残る可能性があるが、Cloudflare proxied Web ドメインとは分離する。必要な場合は DNS-only の SSH 専用サブドメイン、または Cloudflare Tunnel / Access 経由の管理経路を別途選択できるようにする。

## Scope
- **In**: Docker image tag/push/pull の運用設計、registry 選定、OCI pull 手順、preflight/check 手順、systemd one-shot の image 更新方針、rollback 方針、Cloudflare proxied Web ドメインと SSH/deploy 経路の分離方針。
- **Out**: Gmail Monitor のアプリ機能変更、Cloudflare/nginx の全面再設計、OAuth/LINE webhook URL の変更、Secrets 管理 SaaS 導入、DB 化、マルチユーザー化、完全な CI/CD パイプラインの強制導入。

## Boundary Candidates
- Image artifact boundary: source tree ではなく image tag を本番反映単位にする。
- Runtime configuration boundary: `.env`, `credentials.json`, `token.json`, `filters.json`, `log/` は image 外の OCI runtime input として維持する。
- Network boundary: Cloudflare proxied Web 公開経路と SSH/deploy 管理経路を分離する。
- Operations boundary: pull、check、activate、rollback を手順化し、systemd timer の schedule 変更とは分ける。

## Out of Boundary
- Cloudflare の公開 Web 設定をこの仕様で大きく作り替えない。
- SSH port 22 の公開可否をこの仕様だけで決めない。OCI Security List / NSG と管理経路の選択として扱う。
- registry に secret や token を入れない。
- `SyncNow` は移行中の補助手段として残せるが、長期的な本線とはしない。

## Upstream / Downstream
- **Upstream**: `app-containerization` 仕様の Dockerfile、compose、check script、runtime mount contract。
- **Downstream**: GitHub Actions 等による CI/CD 自動化、Secrets 管理 SaaS 導入、OCI 以外への移設、rollback/monitoring 強化。

## Existing Spec Touchpoints
- **Extends**: `app-containerization` の後続運用仕様。特に Docker image build、runtime mount、OCI one-shot 互換性、manual validation 手順を前提にする。
- **Adjacent**: Cloudflare/nginx 公開経路、Google OAuth Console、LINE Developers Console、systemd timer schedule は隣接領域だが、原則としてこの仕様の主所有範囲にしない。

## Constraints
Markdown content は日本語で記録する。secret、token、実ドメイン名、registry token、OCI public IP は spec に記録しない。Cloudflare proxied DNS は HTTP/HTTPS 公開用として扱い、SSH/rsync の通常接続先にはしない。OCI 側で sshd が listen していても、外部到達性は別途 Security List / NSG / DNS-only / Tunnel 設定で検証する。
