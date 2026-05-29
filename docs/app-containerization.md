# Gmail Monitor コンテナ化運用メモ

## 目的

このメモは、Gmail Monitor を Docker image として build し、ローカル検証と OCI 上の既存 one-shot 運用へ接続するための最小手順をまとめる。Cloudflare、nginx、Google OAuth Console、LINE Developers Console、systemd timer のスケジュールはこの段階では変更しない。

## Runtime ファイル

コンテナ image には secret、token、filters、log を含めない。ホスト側に runtime directory を用意し、次のファイルを配置する。

```text
runtime/
├── credentials.json
├── token.json
├── filters.json
└── log/
```

`credentials.json` と `filters.json` は read-only mount、`token.json` と `log/` は writable mount として扱う。`token.json` は OAuth refresh により更新されるため、コンテナ終了後もホスト側に残る必要がある。

## ローカル検証

```bash
docker compose build
docker compose run --rm check
```

`check` は app modules の import、runtime file の存在と権限、Flask route 登録を確認する。Gmail fetch、LINE push/quota、Gemini API call は実行しない。

runtime directory が repository root 以外にある場合は、`GMM_RUNTIME_DIR` を指定する。

```bash
GMM_RUNTIME_DIR=/path/to/runtime docker compose run --rm check
```

Windows PowerShell では次の形で指定する。

```powershell
$env:GMM_RUNTIME_DIR="C:\path\to\runtime"
docker compose run --rm check
```

## ローカル実行

```bash
docker compose run --rm --service-ports gmail-monitor
```

Flask は container 内で `0.0.0.0:8080` に bind し、Docker が host `127.0.0.1:8080` に publish する。host 側では次の確認ができる。

```bash
curl http://127.0.0.1:8080/health
```

## OCI 手動実行の形

OCI では既存 project directory に source を同期した後、同じ image を build する。

```bash
docker build -t gmail-monitor:local .
docker run --rm \
  --env-file .env \
  -e GMM_FLASK_HOST=0.0.0.0 \
  -e GMM_FLASK_PORT=8080 \
  -e GMM_CREDS_PATH=/runtime/credentials.json \
  -e GMM_TOKEN_PATH=/runtime/token.json \
  -e GMM_FILTER_PATH=/runtime/filters.json \
  -e GMM_LOG_FILE=/runtime/log/gmm_app.log \
  -p 127.0.0.1:8080:8080 \
  --mount type=bind,src=/opt/gmm_runtime/credentials.json,dst=/runtime/credentials.json,readonly \
  --mount type=bind,src=/opt/gmm_runtime/token.json,dst=/runtime/token.json \
  --mount type=bind,src=/opt/gmm_runtime/filters.json,dst=/runtime/filters.json,readonly \
  --mount type=bind,src=/opt/gmm_runtime/log,dst=/runtime/log \
  gmail-monitor:local
```

systemd service では既存 timer は維持し、Python 直起動の `ExecStart` だけを上記 `docker run` 形へ置き換える。`docker run` の exit status が systemd に伝播するため、失敗時は `systemctl status` と `journalctl` で確認できる。

## 移行前 preflight

- `docker compose run --rm check` または OCI 上の `python scripts/container_check.py` が成功する。
- host `127.0.0.1:8080` が空いている。
- `curl http://127.0.0.1:8080/health` が `ok` を返す。
- nginx から `/oauth/callback` と `/callback` が既存どおり Flask へ到達する。
- `token.json` が writable で、`log/` にログを書ける。
- `.env`, `credentials.json`, `token.json`, `filters.json`, `log/` が image に入っていない。

## rollback

container start、mount、port bind、callback 到達性に問題がある場合は、systemd service の `ExecStart` を従来の Python 直起動へ戻す。

```bash
/opt/gmm_project/GmmEnv/bin/python -u app.py
```

rollback 後は `systemctl daemon-reload`、service の手動実行、次回 timer run の journal を確認する。

## registry deploy へ移る場合

Cloudflare proxied Web domain を使う環境では、公開 Web hostname と SSH/rsync の管理経路を分ける必要がある。source 同期ではなく registry image を OCI 側で pull して反映する運用へ移る場合は、`docs/cloudflare-aware-deployment.md` を参照する。

`SyncNow` は移行中の補助として残せるが、長期的な本番反映の必須手段にはしない。

## 範囲外

この段階では Secrets 管理 SaaS、`filters.json` の DB 化、マルチユーザー化、CI/CD または自動デプロイ基盤の導入は行わない。これらは container baseline が安定した後の別仕様で扱う。
