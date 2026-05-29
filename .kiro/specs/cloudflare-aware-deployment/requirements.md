# Requirements Document

## Introduction

Gmail Monitor のデプロイを、従来の `SyncNow` による source file 同期中心の運用から、Docker image artifact を registry 経由で OCI に反映する運用へ移行する。Cloudflare 配下の公開 Web ドメインは HTTP/HTTPS の入口として維持し、SSH/rsync などの管理経路とは分離する。

この仕様は、既存の `app-containerization` 仕様で作成された Docker image、runtime mount、検証 entrypoint、one-shot 実行互換性を前提にする。目的は、Cloudflare proxied DNS の影響を受けにくいデプロイ手順、OCI 側での pull/check/activate、失敗時の rollback 判断を運用者が再現できる状態にすることである。

## Boundary Context

- **In scope**: Docker image の tag/push/pull を本番反映単位にする運用要件、OCI 上での image 取得後検証、systemd one-shot 実行対象 image の更新判断、rollback 判断、Cloudflare 公開 Web 経路と管理経路の分離要件。
- **Out of scope**: Gmail Monitor のアプリ機能変更、Cloudflare/nginx の全面再設計、OAuth/LINE webhook URL の変更、Secrets 管理 SaaS 導入、DB 化、マルチユーザー化、完全な CI/CD パイプラインの強制導入。
- **Adjacent expectations**: `app-containerization` は Docker image の build/check/run と runtime file mount を提供する。Cloudflare、nginx、Google OAuth Console、LINE Developers Console、systemd timer schedule は、明示的に変更しない限り既存運用を維持する。

## Requirements

### Requirement 1: Image Artifact を本番反映単位にする
**Objective:** As a 開発者兼運用者, I want source tree 同期ではなく Docker image tag を反映単位として扱える, so that Cloudflare 配下の DNS 変更に左右されにくいデプロイ運用にできる

#### Acceptance Criteria
1. When 開発者兼運用者が新しいリリース候補を作成する, the Gmail Monitor デプロイ運用 shall source file の個別同期ではなく一意に識別できる image tag をリリース候補として扱える。
2. When image tag が本番反映候補として選ばれる, the Gmail Monitor デプロイ運用 shall その tag がどの source revision または build に対応するかを運用者が確認できる情報を残せる。
3. If image tag の取得または識別に失敗する, then the Gmail Monitor デプロイ運用 shall 本番実行対象を変更せず、失敗理由を運用者が確認できる状態にする。
4. The Gmail Monitor デプロイ運用 shall `SyncNow` を長期的な本番反映の必須手段として扱わない。

### Requirement 2: Registry 配布と機密情報の分離
**Objective:** As a 運用者, I want registry に配布する artifact と runtime 機密情報を分離できる, so that image 配布によって secret や token が漏えいしない

#### Acceptance Criteria
1. When Docker image が registry へ登録される, the Gmail Monitor デプロイ運用 shall `.env`, `credentials.json`, `token.json`, `filters.json`, `log/` を image artifact に含めない。
2. While OCI 上で image を実行する, the Gmail Monitor デプロイ運用 shall runtime file を image 外の既存運用入力として扱える。
3. If registry 認証情報が必要になる, then the Gmail Monitor デプロイ運用 shall registry 認証情報を source、spec、documented command の固定値として記録しない。
4. When runtime file が不足または不適切な権限で配置されている, the Gmail Monitor デプロイ運用 shall 本番切替前の検証で不足内容を運用者が判別できるようにする。

### Requirement 3: OCI Pull 後の検証と有効化
**Objective:** As a 運用者, I want OCI 側で image を取得してから本番実行対象へ切り替える前に検証できる, so that 壊れた image を timer 実行へ接続するリスクを下げられる

#### Acceptance Criteria
1. When OCI 側で新しい image tag を取得する, the Gmail Monitor デプロイ運用 shall 本番実行対象へ切り替える前に image の取得成功を確認できる。
2. When 新しい image tag が取得済みである, the Gmail Monitor デプロイ運用 shall Gmail fetch、LINE push、Gemini API call を実行しない検証を本番切替前に実行できる。
3. If preflight 検証が失敗する, then the Gmail Monitor デプロイ運用 shall systemd one-shot の実行対象を新しい image tag に切り替えない。
4. While preflight 検証を行う, the Gmail Monitor デプロイ運用 shall runtime mount、環境変数、host loopback 到達性、callback 経路の確認項目を運用者が追跡できるようにする。
5. When preflight 検証が成功する, the Gmail Monitor デプロイ運用 shall 運用者が本番実行対象 image を切り替えたことを確認できる手順を提供する。

### Requirement 4: Cloudflare 公開経路と管理経路の分離
**Objective:** As a 運用者, I want Web 公開ドメインと SSH/deploy 管理経路を区別できる, so that Cloudflare proxied DNS による SSH/rsync 接続失敗を避けられる

#### Acceptance Criteria
1. While Cloudflare proxied Web ドメインを使用している, the Gmail Monitor デプロイ運用 shall そのドメインを通常の SSH/rsync 接続先として必須にしない。
2. When 管理経路を設定する, the Gmail Monitor デプロイ運用 shall Web 公開用 hostname と管理用 hostname または tunnel 経路を区別して記録できる。
3. If 管理用 hostname が Cloudflare の proxied address を返す, then the Gmail Monitor デプロイ運用 shall SSH/rsync 用の接続先として不適切であることを運用者が判別できる確認手順を提供する。
4. Where SSH 管理経路を使用する, the Gmail Monitor デプロイ運用 shall OCI 側 sshd の listen 状態だけでなく、外部到達性が Security List、NSG、DNS、または tunnel 設定に依存することを確認対象に含める。
5. Where Cloudflare Tunnel または Access を使用する, the Gmail Monitor デプロイ運用 shall Web 公開経路を変更せずに管理経路の到達性を確認できる。

### Requirement 5: One-shot 運用互換性と rollback
**Objective:** As a 運用者, I want image 更新後も既存 one-shot timer 運用と rollback 判断を維持できる, so that 本番運用リスクを抑えて段階的に移行できる

#### Acceptance Criteria
1. When 本番実行対象 image が更新される, the Gmail Monitor デプロイ運用 shall 既存の one-shot 実行フローを維持できる。
2. While systemd timer が既存スケジュールで実行される, the Gmail Monitor デプロイ運用 shall timer schedule の変更を必須にしない。
3. If container start、runtime mount、port bind、callback 到達性、または process exit status に問題がある, then the Gmail Monitor デプロイ運用 shall 直前の実行可能な状態へ戻す判断材料を運用者に提供する。
4. When rollback が必要になる, the Gmail Monitor デプロイ運用 shall 直前の image tag または既存 Python 直起動へ戻す選択肢を運用者が判断できるようにする。
5. The Gmail Monitor デプロイ運用 shall rollback 後に service の手動実行結果と次回 timer run の journal を確認できる手順を提供する。

### Requirement 6: 手順の再現性と段階的自動化
**Objective:** As a 開発者兼運用者, I want 手動でも CI からでも同じ判断基準でデプロイできる, so that 完全な CI/CD 導入前でも安全に運用改善を進められる

#### Acceptance Criteria
1. When デプロイ手順が文書化される, the Gmail Monitor デプロイ運用 shall build、push、pull、preflight、activate、rollback の各段階を運用者が区別できるようにする。
2. While 完全な CI/CD パイプラインが未導入である, the Gmail Monitor デプロイ運用 shall 手動実行でも再現できる最小手順を提供する。
3. Where CI による build/push が含まれる, the Gmail Monitor デプロイ運用 shall OCI 側の pull/check/activate と同じ合格条件を使える。
4. If 途中段階で失敗する, then the Gmail Monitor デプロイ運用 shall 失敗が build、registry、OCI pull、preflight、activate、runtime のどの段階で起きたかを運用者が切り分けられるようにする。
5. The Gmail Monitor デプロイ運用 shall 後続の CI/CD 自動化、Secrets 管理 SaaS、OCI 以外への移設を妨げない成果物を残す。
