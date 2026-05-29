# Project Structure

## Organization Philosophy

このリポジトリは、flat で service-layered な Python layout を採用しています。各 top-level module が integration または pipeline 上の責務を1つ持ち、`app.py` が runnable monitor として結合します。新機能が package 化に値する複雑さを生むまでは、この単純な構造を維持します。

## Directory Patterns

### Runtime Modules
**Location**: repository root  
**Purpose**: application orchestration、service integration、extraction、configuration default。  
**Example**: 新しい notification provider は独立 module に置き、`app.py` または composition class へ狭い interface を公開する。

### User Configuration
**Location**: repository root  
**Purpose**: mail filter などの local operational configuration。  
**Example**: `filters.json` は message を extractor name へ対応付ける sender/subject group を定義する。

### User Notes
**Location**: `user_notes/`  
**Purpose**: 調査メモ、deployment findings、migration planning。  
**Example**: ここは文脈として読み、永続的な decision になったものだけ `.kiro/steering/` へ昇格する。

### User Screenshots
**Location**: `user_screenshots/`  
**Purpose**: Google Cloud や LINE Developers など外部 console 設定の手動証跡。  
**Example**: screenshot は troubleshooting に使えるが、steering には安定した設定原則だけを記録する。

### Tests
**Location**: `test/`  
**Purpose**: 軽量な test または experimental entrypoint。  
**Example**: parsing、filtering、formatting、provider boundary behavior を変えるときは focused test を追加する。

## Naming Conventions

- **Files**: Python module は lower snake_case。
- **Classes**: PascalCase。通常は service responsibility と対応させる（`GoogleService`, `LINEWebhook`, `AIExtractor`）。
- **Functions and methods**: lower snake_case。
- **Configuration keys**: environment variable は upper snake case、dataclass field は lower snake_case。
- **Extractor names**: `filters.json` の group behavior と一致する lower-case または安定した config string。

## Import Organization

flat root layout では sibling module を直接 import します。

```python
from line_webhook import LINEWebhook
from google_service import GoogleService
from extract_gmail_content import ExtractGmailContent
```

third-party import は、その integration を所有する module 内で明示します。provider dependency を広い utility module に隠さないでください。

## Code Organization Principles

- `app.py` は startup、authorization、fetch、extract、send の orchestration を担当する。provider-specific parsing や API request detail を蓄積しない。
- provider module は external API client、credential loading、request timeout、API-specific error handling を所有する。
- extraction module は matching、extraction、formatting を分離し、新しい message group を Gmail retrieval 変更なしに追加できるようにする。
- generic AI extraction は sender-agnostic に保つ。sender-specific prompt、schema choice、fallback は `ExtractGmailContent` に置く。
- operational deployment detail は design decision に影響する永続的な原則だけを記録する。steering を server configuration のコピーにしない。

## Sensitive and Generated Files

以下は source pattern として docs や specs に写さないでください。

- `.env`
- `credentials.json`
- `token.json`
- log files
- local virtual environments

persistence や deployment を変えるときも、secret と token は source control 外から注入または mount される前提を保ちます。

---
_パターンを記録し、file tree を網羅しない。新規ファイルが既存パターンに従うなら steering 更新は不要であるべき。_
