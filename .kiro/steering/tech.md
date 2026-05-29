# Technology Stack

## Architecture

アプリケーションは、mixin 的なクラス合成で構成された小さな Python サービスです。

- `GMMServer` は Flask app、proxy 対応、logging、server lifecycle を担当する。
- `LINEWebhook` は LINE credentials、webhook handling、quota check、push messaging を担当する。
- `GoogleService` は Google OAuth、Gmail session、Gmail REST access を担当する。
- `AIExtractor` は送信者固有ロジックを持たない汎用 Gemini JSON 抽出を担当する。
- `ExtractGmailContent` は filter matching、送信者別 extraction、LINE message formatting を担当する。
- `GmailMonitor` は `AppConfig` dataclass により各レイヤーを結合する。

外部サービスごとの責務分離を維持してください。新しい provider integration は `app.py` に直接埋め込まず、明確な境界を持つ module に分けます。

## Core Technologies

- **Language**: Python
- **Framework**: Flask for callback endpoints and lightweight health responses
- **Runtime**: Python virtual environment。本番メモでは OCI 上の Python 3.9、ローカルではより新しい Python が参照されている
- **External APIs**: Gmail REST API, Google OAuth, LINE Messaging API, Google Gemini API

## Key Libraries

- `Flask`: HTTP endpoint。
- `google-auth-oauthlib`, `google-auth`, `google-api-python-client` 系: OAuth credential。
- `line-bot-sdk` v3: LINE Webhook と Messaging API。
- `requests`: REST call と明示的 timeout。
- `python-dotenv`: local/deployment environment configuration。

## Development Standards

### Configuration

secret、deployment domain、log behavior、API key は環境変数で扱います。secret 値を commit したり steering/spec に記録したりしないでください。`.env`、`credentials.json`、`token.json` は運用入力であり、プロジェクト知識として本文化しません。

`filters.json` は現在の sender/subject group rule source です。ユーザー所有の設定として扱い、schema 変更は仕様で明示します。

### Error Handling

network call には明示的な timeout を設定します。Gmail と Gemini の処理は可能な範囲で fail soft にします。壊れた個別メールは skip し、AI provider が使えない場合は抽出なしとして扱い、誤解を招く通知を送らないことを優先します。

### Security

- Gmail access は、仕様で明示されない限り read-only を維持する。
- OAuth callback state と LINE user ID check は access boundary の一部として扱う。
- app が token file を書く場合、platform が許す範囲で restrictive permission を使う。
- reverse proxy で公開する path は callback に必要なものへ限定する。

### Code Quality

`app.py` の責務は orchestration に留めます。provider behavior、extraction rule、formatting はそれぞれの module に置きます。parsing、fallback、formatting は typed signature と小さな helper method を優先します。

### Testing

現状の test coverage は最小限です。filter、extractor、OAuth behavior、notification formatting を変える場合は、deployment behavior を変える前に pure function または mock した service boundary の focused test を追加します。

## Development Environment

### Required Tools

- Python virtual environment
- `requirements.txt` の依存関係
- LINE、Google OAuth、server domain、必要に応じて Gemini extraction 用の環境変数

### Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the one-shot monitor locally
python app.py

# Run the existing sample/test entrypoint
python test/app.py
```

## Key Technical Decisions

- Gmail retrieval は高水準 wrapper ではなく authorized session による REST call を使い、request fields、timeout、partial failure を明示する。
- AI extraction は schema-driven かつ generic に保つ。sender-specific behavior は Gmail content extraction layer に置く。
- LINE delivery は monthly message limit を使い切らないよう quota check で守る。
- process は timer-oriented で、run 後に終了しうる。long-lived background behavior は spec-level design change なしに追加しない。

---
_標準とパターンを記録し、依存関係を網羅しない。_
