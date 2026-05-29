# Requirements Document

## Introduction

Gmail Monitor のアプリ本体を Docker コンテナ化し、ローカル開発環境と OCI 実行環境の差分を減らす。現行の Cloudflare、nginx、現行ドメイン、systemd timer による one-shot 運用は第一段階では維持し、Python 直起動部分をコンテナ実行へ置き換えられる状態を目指す。

この仕様は、コンテナイメージとしての再現性、機密情報と永続ファイルの安全な扱い、ローカルでの最低限の検証、OCI 上での既存運用互換性を対象とする。Secrets 管理 SaaS、DB 化、マルチユーザー化、CI/CD の本格導入は後続の別仕様として扱う。

## Boundary Context

- **In scope**: アプリ本体のコンテナビルド、コンテナ起動確認、ローカル smoke test、OCI 上で既存 one-shot 運用に接続できる実行要件、機密ファイルと永続ファイルをイメージ外で扱う運用要件。
- **Out of scope**: Cloudflare/nginx の全面再設計、systemd timer のスケジュール変更、Secrets 管理 SaaS 導入、DB 導入、`filters.json` の永続層移行、マルチユーザー化、CI/CD 本格導入。
- **Adjacent expectations**: 既存 nginx が `127.0.0.1:8080` のアプリへ到達できること、既存 OAuth/LINE 設定が引き続き利用できること、既知の `/callback` 経路不整合は移行前リスクとして検証対象に含めるが、この仕様の修正責務には含めない。

## Requirements

### Requirement 1: コンテナイメージとしての再現性

**Objective:** As a 開発者, I want Gmail Monitor を再現可能なコンテナイメージとして扱える, so that ローカルと OCI の実行環境差分を減らせる

#### Acceptance Criteria

1. When 開発者がコンテナビルドを実行する, the Gmail Monitor コンテナ化成果物 shall アプリ本体を実行可能なイメージとして生成できる。
2. When コンテナイメージが生成される, the Gmail Monitor コンテナ化成果物 shall アプリ起動に必要な Python 依存関係をイメージ内に含める。
3. When コンテナイメージが生成される, the Gmail Monitor コンテナ化成果物 shall `.env`, `credentials.json`, `token.json`, `log/` をイメージ内に含めない。
4. If 必須依存関係の解決に失敗する, the Gmail Monitor コンテナ化成果物 shall ビルド失敗として検出できる。

### Requirement 2: 機密情報と永続ファイルの外部注入

**Objective:** As a 運用者, I want secret と実行時に更新されるファイルをイメージ外で扱える, so that 認証情報を保護しつつ既存運用を継続できる

#### Acceptance Criteria

1. When コンテナを起動する, the Gmail Monitor コンテナ化成果物 shall 環境変数または env file から運用設定を受け取れる。
2. When コンテナを起動する, the Gmail Monitor コンテナ化成果物 shall `credentials.json`, `token.json`, `filters.json` を外部配置から利用できる。
3. When Gmail OAuth token が更新される, the Gmail Monitor コンテナ化成果物 shall 更新後の `token.json` をコンテナ終了後も保持できる外部配置に保存できる。
4. When ログ出力が有効化される, the Gmail Monitor コンテナ化成果物 shall コンテナ外から確認可能なログ出力を提供する。
5. If secret または token がビルド対象に含まれそうになる, the Gmail Monitor コンテナ化成果物 shall それらをイメージ成果物から除外する。

### Requirement 3: ローカル検証性

**Objective:** As a 開発者, I want 外部 API に依存しない最低限のローカル検証を実行できる, so that OCI 反映前に起動環境と基本的な破損を検出できる

#### Acceptance Criteria

1. When 開発者がローカルで検証コマンドを実行する, the Gmail Monitor コンテナ化成果物 shall アプリモジュールの import 可否を確認できる。
2. When 開発者がローカルで smoke test を実行する, the Gmail Monitor コンテナ化成果物 shall 実 Gmail 取得、LINE push、Gemini API 呼び出しを行わずに検証を完了できる。
3. When 開発者がローカルで Flask 起動確認を行う, the Gmail Monitor コンテナ化成果物 shall callback endpoint を待ち受け可能な状態にできる。
4. If ローカル検証に必要な外部配置ファイルが不足している, the Gmail Monitor コンテナ化成果物 shall 不足内容を識別できる失敗として扱う。

### Requirement 4: OCI 既存運用との互換性

**Objective:** As a 運用者, I want OCI 上の既存 one-shot 運用を大きく変えずにコンテナ実行へ置き換えられる, so that 本番運用リスクを抑えて移行できる

#### Acceptance Criteria

1. When OCI 上でコンテナを起動する, the Gmail Monitor コンテナ化成果物 shall 既存の one-shot 実行フローを維持できる。
2. When systemd timer から実行される, the Gmail Monitor コンテナ化成果物 shall 実行完了後にプロセスを終了できる。
3. While OCI 上で実行されている, the Gmail Monitor コンテナ化成果物 shall 既存 nginx が期待するローカル到達先で Flask endpoint を提供できる。
4. If コンテナ実行が失敗する, the Gmail Monitor コンテナ化成果物 shall 運用者が失敗理由をログまたは終了状態から確認できる。
5. When 移行手順を確認する, the Gmail Monitor コンテナ化成果物 shall Python 直起動へ戻すための判断材料を提供する。

### Requirement 5: 既存公開経路と外部サービス設定の維持

**Objective:** As a 運用者, I want 既存の公開経路と外部サービス設定を第一段階で維持できる, so that OAuth や通知経路を壊さずに実行環境だけを差し替えられる

#### Acceptance Criteria

1. While 第一段階のコンテナ化を行う, the Gmail Monitor コンテナ化成果物 shall Cloudflare、nginx、現行ドメイン、Google OAuth Console、LINE Developers Console の設定変更を必須にしない。
2. When コンテナ版アプリが起動する, the Gmail Monitor コンテナ化成果物 shall 既存の OAuth callback endpoint を維持する。
3. When コンテナ版アプリが起動する, the Gmail Monitor コンテナ化成果物 shall 既存の LINE webhook endpoint を維持する。
4. If 既存 nginx 設定と webhook endpoint に不整合がある, the Gmail Monitor コンテナ化成果物 shall それをコンテナ移行前の検証リスクとして明示できる。

### Requirement 6: 範囲外変更の抑制

**Objective:** As a 開発者, I want コンテナ化の範囲を明確に保てる, so that 後続の Secrets 管理や DB 化と混線せずに第一段階を完了できる

#### Acceptance Criteria

1. While この仕様を実装する, the Gmail Monitor コンテナ化成果物 shall Secrets 管理 SaaS の導入を必須にしない。
2. While この仕様を実装する, the Gmail Monitor コンテナ化成果物 shall `filters.json` の DB 移行を必須にしない。
3. While この仕様を実装する, the Gmail Monitor コンテナ化成果物 shall マルチユーザー対応を必須にしない。
4. While この仕様を実装する, the Gmail Monitor コンテナ化成果物 shall CI/CD または自動デプロイ基盤の導入を必須にしない。
5. When 後続作業を検討する, the Gmail Monitor コンテナ化成果物 shall ローカル/リモート開発ワークフロー改善、Secrets 管理移行、DB 化の前提として参照できる成果を残す。
