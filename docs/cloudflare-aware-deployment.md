# Cloudflare-aware registry deployment

この runbook は、Gmail Monitor を source file 同期ではなく Docker image artifact として OCI に反映するための手順をまとめる。Web 公開経路は既存どおり `Cloudflare proxied -> nginx -> 127.0.0.1:8080` を維持し、SSH や deploy 管理経路とは分離する。

実ドメイン、OCI public IP、registry token、OAuth credential、LINE credential はこの文書へ記録しない。

## 1. 成果物の境界

- Build input: repository source と `Dockerfile`
- Deploy input: registry image tag または digest
- Runtime input: OCI host 上の `.env`, `credentials.json`, `token.json`, `filters.json`, `log/`
- 管理経路: DNS-only SSH hostname または Cloudflare Tunnel / Access
- Web 公開経路: Cloudflare proxied hostname

`SyncNow` は移行中の補助には使えるが、長期的な本番反映の必須手段にはしない。

## 2. Publish

GitHub Actions の `Publish Gmail Monitor image` workflow を手動実行する。

入力:

- `tag`: 任意。空なら短い commit SHA が使われる。

出力:

- `ghcr.io/<owner>/<repo>/gmail-monitor:<tag>`
- source revision
- digest

OCI へ反映するときは tag だけでなく digest も記録する。tag は読みやすいが mutable なので、rollback や再現性が必要な場面では digest を優先する。

## 3. OCI host の準備

OCI host 側で `ops/oci/deploy.env.example` を参考に、host 側だけに deploy 設定を置く。

```bash
export GMM_IMAGE="ghcr.io/OWNER/REPOSITORY/gmail-monitor:TAG"
export GMM_ENV_FILE="/opt/gmm_project/Gmail-Monitor/.env"
export GMM_RUNTIME_DIR="/opt/gmm_runtime"
export GMM_DEPLOY_STATE="/opt/gmm_deploy/deploy-state.env"
export GMM_SYSTEMD_ENV="/etc/gmm/deploy-image.env"
```

private package を使う場合は、OCI host の Docker CLI で registry login を行う。必要な権限は image pull に必要な read 権限であり、token 値は shell history や documentation に残さない。

## 4. Pull

```bash
ops/oci/deploy-image.sh pull "$GMM_IMAGE"
ops/oci/deploy-image.sh status
```

成功条件:

- image pull が成功する
- state file に `LAST_CHECKED_IMAGE` が記録される
- active image はまだ変更されない

失敗した場合:

- registry login、package visibility、image name/tag を確認する
- active image は変更しない

## 5. Preflight

```bash
ops/oci/deploy-image.sh check "$GMM_IMAGE"
```

この check は candidate image 内の `scripts/container_check.py` を実行する。Gmail fetch、LINE push、Gemini API call は行わない。

成功条件:

- runtime file が存在し、必要な read/write 権限がある
- import と Flask route check が成功する
- state file に `LAST_CHECK_STATUS=OK` が記録される

失敗した場合:

- `.env`, `credentials.json`, `token.json`, `filters.json`, `log/` の配置と権限を確認する
- active image は変更しない

## 6. Activate

```bash
ops/oci/deploy-image.sh activate "$GMM_IMAGE"
ops/oci/deploy-image.sh status
```

成功条件:

- `ACTIVE_IMAGE` が candidate image に変わる
- `PREVIOUS_IMAGE` に直前の active image が残る
- systemd が参照できる env file に active image が書かれる

activate 後は、timer を待つ前に service を手動実行し、journal を確認する。

```bash
sudo systemctl daemon-reload
sudo systemctl start gmm.service
sudo journalctl -u gmm.service -n 100 --no-pager
```

## 7. Runtime validation

container 実行中に host loopback と nginx 経路を確認する。

```bash
curl http://127.0.0.1:8080/health
```

既存 nginx callback 経路は、現行運用で使っている Web hostname に対して確認する。ここでも secret や実 URL を文書化しない。

## 8. Rollback

直前 image に戻す場合:

```bash
ops/oci/deploy-image.sh rollback
sudo systemctl daemon-reload
sudo systemctl start gmm.service
sudo journalctl -u gmm.service -n 100 --no-pager
```

container start、mount、port bind、callback 到達性に問題があり image rollback でも復旧しない場合は、既存 Python 直起動への rollback を検討する。

```bash
/opt/gmm_project/GmmEnv/bin/python -u app.py
```

## 9. Cloudflare management path checklist

### Web 公開 hostname

Web 公開用 hostname は Cloudflare proxied のままでよい。これは HTTP/HTTPS の入口であり、通常の SSH/rsync 接続先として必須にしない。

### DNS-only SSH hostname

DNS-only SSH hostname を使う場合:

```bash
getent ahosts SSH_MANAGEMENT_HOSTNAME
ssh -4 -o ConnectTimeout=10 opc@SSH_MANAGEMENT_HOSTNAME 'hostname'
```

確認観点:

- Cloudflare proxied address ではなく origin 管理の address を返す
- OCI Security List または NSG が意図した source から TCP 22 を許可している
- OCI 内で sshd が listen していても、それだけでは外部到達性の証明にならない

### Cloudflare Tunnel / Access

Cloudflare Tunnel を使う場合:

- server 側と client 側で `cloudflared` が使える
- SSH service が tunnel route で公開されている
- Cloudflare Access の認証が通る
- Web 公開 hostname を変更せずに management connection が成立する

Tunnel を選ぶ場合も、registry deploy の本線は image pull と OCI preflight であり、Tunnel は deploy control plane の到達手段として扱う。

## 10. Failure stage map

| Stage | 代表的な失敗 | 次に見る場所 |
|-------|--------------|--------------|
| build | Docker build failure | workflow log |
| registry | login, push, pull failure | package visibility, Docker login |
| OCI pull | image not found | image name, tag, digest |
| preflight | missing runtime file | `/opt/gmm_runtime`, env file |
| activate | state or systemd env update failure | deploy state file, file permissions |
| runtime | container start, port bind, callback | `journalctl`, Docker logs, nginx |
| rollback | previous image missing | deploy state, Python direct rollback |
