# Implementation Plan

- [ ] 1. コンテナ実行の基盤を整える
- [x] 1.1 Docker image の build contract を追加する
  - Python 3.9 系の official image を基準に、既存アプリを `/app` で実行できる image を作る。
  - `requirements.txt` の依存関係を build 中に install し、依存解決失敗が build 失敗として表面化するようにする。
  - default command は既存の one-shot 実行に合わせて `python -u app.py` 相当にする。
  - 完了時点で、空でない build context から Gmail Monitor image を生成でき、依存関係の install 失敗時には build が non-zero で終了する。
  - _Requirements: 1.1, 1.2, 1.4, 4.1, 4.2_

- [x] 1.2 build context から機密ファイルと生成物を除外する
  - `.env`, `credentials.json`, `token.json`, `log/`, local venv, cache, user notes, screenshots を image context から除外する。
  - `filters.json` は runtime mount 前提として扱い、image 内に固定しない。
  - 完了時点で、Docker build context に secret/token/log が含まれず、image layer に取り込まれないことを確認できる。
  - _Requirements: 1.3, 2.5, 6.1, 6.2_

- [x] 1.3 ローカル/OCI 共通の compose 実行 contract を追加する
  - env file、runtime file mount、log mount、host `127.0.0.1:8080` から container `8080` への port publish を定義する。
  - `credentials.json` と `filters.json` は read-only、`token.json` と `log/` は writable として扱う。
  - 完了時点で、compose 経由で build/check/run の形が分かり、runtime file の mount 権限が設計どおりに表現されている。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 4.3, 5.1_

- [ ] 2. アプリ runtime 設定をコンテナ対応にする
- [x] 2.1 app の runtime path と実行パラメータを環境変数で切り替える
  - 既存 default を維持したまま、credential、token、filter、fetch count、Flask port の runtime override を受け取れるようにする。
  - 不正な数値設定は、外部 API 呼び出し前に分かる失敗として扱う。
  - 完了時点で、環境変数なしでは現行 default が使われ、環境変数ありでは `/runtime` 配下の file path が設定に反映される。
  - _Requirements: 2.1, 2.2, 3.4, 5.2, 5.3_

- [x] 2.2 Flask bind host と log 出力を container runtime に合わせる
  - non-container の default は `127.0.0.1` のまま維持する。
  - container 実行時は `GMM_FLASK_HOST=0.0.0.0` と `GMM_FLASK_PORT` で待ち受け先を切り替えられるようにする。
  - file log が有効な場合、mounted log directory へ出力できる状態を維持する。
  - 完了時点で、`/health`, `/`, `/oauth/start`, `/oauth/callback`, `/callback` の endpoint path は変わらず、host loopback publish 経由で到達できる bind 設定を取れる。
  - _Requirements: 2.4, 3.3, 4.3, 5.2, 5.3_

- [x] 2.3 token と filter の外部 file 利用を one-shot 実行へ接続する
  - OAuth token の読み書き先が runtime override を通して外部配置を参照することを確認する。
  - filter rules の読み込み先が runtime override を通して外部配置を参照することを確認する。
  - 完了時点で、container 終了後も更新済み `token.json` が host 側に残り、`filters.json` の schema や DB 化は変更されない。
  - _Requirements: 2.2, 2.3, 4.1, 4.2, 6.2_

- [ ] 3. 外部 API なしの検証入口を実装する
- [x] 3.1 import と runtime file preflight を行う検証 command を追加する
  - app modules の import 可否を検査する。
  - credential、token、filter、log directory の存在、読み取り、token 書き込み可能性を検査する。
  - 不足や権限エラーは file label と env variable 名が分かる non-zero 終了として返す。
  - 完了時点で、外部 API credential が実在しない場合でも、不足項目が明示された検証失敗として観測できる。
  - _Requirements: 3.1, 3.2, 3.4_

- [x] 3.2 Flask route の no-API smoke check を追加する
  - Gmail fetch、LINE push/quota、Gemini call を実行せずに route 登録と基本応答を確認する。
  - 検証 command は production one-shot command と分離し、通常運用の挙動を変えない。
  - 完了時点で、container 内から smoke check を実行すると expected endpoint の登録または basic health response を確認して終了する。
  - _Requirements: 3.1, 3.2, 3.3, 5.2, 5.3_

- [x] 3.3 検証 command を compose と Docker image から実行できるようにする
  - build 後の image に検証 script を含める。
  - compose または Docker command から production run とは別 command として検証を呼び出せるようにする。
  - 完了時点で、同じ image を使って local check と production one-shot run を選択できる。
  - _Requirements: 1.1, 3.1, 3.2, 3.3, 3.4_

- [ ] 4. OCI 既存運用への接続材料を追加する
- [x] 4.1 systemd one-shot 置き換え用の Docker run 形を確定する
  - host `127.0.0.1:8080` publish、runtime mount、env file、container cleanup、exit status 伝播を含む実行形にする。
  - Docker run 失敗時に systemd から non-zero 終了として確認できる形にする。
  - 完了時点で、既存 timer の schedule を変えずに `ExecStart` の Python 直起動部分だけを置き換える材料がある。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1_

- [x] 4.2 callback 経路と rollback の preflight checklist を追加する
  - nginx `/oauth/callback` と `/callback` の到達性を移行前リスクとして確認する項目を含める。
  - Python 直起動へ戻す判断条件と復旧 command の形を明示する。
  - Secrets 管理 SaaS、DB 化、マルチユーザー化、CI/CD をこの段階の必須作業にしないことを明示する。
  - 完了時点で、運用者が container run 継続か rollback かをログ、exit status、callback 到達性から判断できる。
  - _Requirements: 4.4, 4.5, 5.4, 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 4.3 同期対象と除外対象を container 化成果物に合わせる
  - Dockerfile、compose、scripts、docs が OCI 同期対象として必要か確認し、secret/token/log 除外は維持する。
  - 既存の一方向同期運用で image build に必要な成果物が欠けないようにする。
  - 完了時点で、ローカルから OCI project directory へ同期した後に container build/check/run に必要な source artifact が揃う。
  - _Requirements: 1.1, 1.3, 2.5, 5.1, 6.5_

- [ ] 5. コンテナ化の検証を追加する
- [x] 5.1 build と build context 除外の検証を追加する
  - image build が依存 install まで到達することを確認する。
  - `.dockerignore` が secret/token/log/local generated files を除外することを検証する。
  - 完了時点で、build 成功と secret 除外をローカルから再確認できる。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.5_

- [x] 5.2 runtime 設定 override の focused test を追加する
  - env が未設定のときに既存 default が維持されることを検証する。
  - env override により `/runtime` path、fetch count、Flask host/port が反映されることを検証する。
  - 完了時点で、app runtime 設定変更が one-shot flow や endpoint path を壊していないことを test で確認できる。
  - _Requirements: 2.1, 2.2, 3.4, 4.1, 5.2, 5.3_

- [x] 5.3 container check と mount 権限の integration check を追加する
  - container 内で検証 command を実行し、API 呼び出しなしで import、file preflight、route check を確認する。
  - token path の writable 性と log directory の writable 性を確認する。
  - 完了時点で、runtime mount が不足または read-only 誤設定のときに明確な失敗を返し、正常設定では check が成功する。
  - _Requirements: 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4_

- [x] 5.4 OCI 互換性の手動検証手順を実行可能にする
  - host `127.0.0.1:8080` publish 経由の `/health` 到達確認を含める。
  - `docker logs`、exit status、mounted log file の確認手順を含める。
  - 完了時点で、OCI 上で manual container run から timer 置き換え前の可否判断まで進められる。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.4_

- [ ] 6. 境界維持と最終統合を行う
- [x] 6.1 実装成果物を設計境界に照らして統合確認する
  - Docker image、runtime mount、network publish、validation entrypoint、one-shot flow が相互に矛盾していないことを確認する。
  - app runtime 変更が provider-specific logic、filter schema、external console 設定へ広がっていないことを確認する。
  - 完了時点で、Secrets 管理 SaaS、DB 化、マルチユーザー化、CI/CD を導入せずに第一段階の container 化成果物が成立している。
  - _Requirements: 5.1, 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 6.2 end-to-end の local container workflow を通す
  - build、no-API check、host loopback route check、production command の dry execution boundary を順に確認する。
  - 失敗時に build error、validation error、port bind error、runtime log のどこで止まったか判別できることを確認する。
  - 完了時点で、ローカルから OCI 反映前に最低限の破損を検出できる workflow が再現できる。
  - _Requirements: 1.1, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 4.3, 4.4, 6.5_
