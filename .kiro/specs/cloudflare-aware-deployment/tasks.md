# Implementation Plan

- [x] 1. Registry deploy の基礎 contract を整える
- [x] 1.1 build context と image metadata の保護を追加する
  - `.dockerignore` に deploy workflow と OCI helper 用の運用ファイルを追加し、image layer に入らないことを明示する。
  - `Dockerfile` に repository source label を追加し、registry 上で source/build 対応を追いやすくする。
  - 完了時点で、image build context に runtime secret、deploy helper、workflow metadata が含まれないことを確認できる。
  - _Requirements: 1.2, 2.1, 6.5_
  - _Boundary: BuildContextGuard, ImagePublishWorkflow_

- [x] 1.2 deploy 用の非 secret 設定テンプレートを追加する
  - registry image 名、runtime directory、state file、systemd 連携先などの変数名だけを示す example を追加する。
  - token、実ドメイン、OCI public IP、実 registry credential を記録しない。
  - 完了時点で、運用者が secret を書かずに必要な設定項目を把握できる。
  - _Requirements: 2.3, 6.1, 6.2_
  - _Boundary: RegistryAuthBoundary, DeploymentRunbook_

- [x] 2. Image publish workflow を追加する
- [x] 2.1 registry へ image tag を publish する workflow を作る (P)
  - 手動実行できる workflow として、既存 Dockerfile から image を build して registry へ push する。
  - tag には手動指定値と source revision を反映できるようにし、OCI activate は行わない。
  - 完了時点で、workflow の出力から publish した image tag と source revision を確認できる。
  - _Requirements: 1.1, 1.2, 6.3_
  - _Boundary: ImagePublishWorkflow_
  - _Depends: 1.1_

- [x] 2.2 registry 認証と digest 記録の扱いを workflow に反映する (P)
  - publish 側は repository に紐づく workflow credential を使う前提にし、secret 値を workflow log に出さない。
  - push 後に digest を出力または summary に残し、OCI 側 deploy state と照合できるようにする。
  - 完了時点で、運用者が tag と digest の両方を publish 結果として確認できる。
  - _Requirements: 1.2, 2.3, 6.3_
  - _Boundary: ImagePublishWorkflow, RegistryAuthBoundary_
  - _Depends: 1.1_

- [x] 3. OCI deploy helper を追加する
- [x] 3.1 image reference と deploy state を扱う helper の骨格を作る (P)
  - tag 形式と digest 形式の image reference を受け取り、active/previous/last checked の state を読み書きできるようにする。
  - state には registry token、OCI public IP、OAuth/LINE secret を保存しない。
  - 完了時点で、status 操作により active image、previous image、last check status が表示される。
  - _Requirements: 1.2, 1.3, 5.3, 6.5_
  - _Boundary: OciDeployController, DeployStateManifest_
  - _Depends: 1.2_

- [x] 3.2 candidate image の pull と digest 解決を実装する (P)
  - OCI 側で指定 image を pull し、取得失敗時は active state を変更しない。
  - pull 成功後に inspect 可能な digest または image id を state に記録できるようにする。
  - 完了時点で、pull 成功時だけ candidate が記録され、失敗時には本番実行対象が変わらない。
  - _Requirements: 3.1, 1.3, 6.4_
  - _Boundary: OciDeployController_
  - _Depends: 1.2_

- [x] 3.3 pulled image に対する preflight check を実装する
  - candidate image で既存 no-external-API check を実行し、runtime mount と環境変数を既存 contract に合わせて渡す。
  - preflight 失敗時は activate を許可せず、失敗 stage と diagnostics を表示する。
  - 完了時点で、runtime file 不足や権限不備が本番切替前に判別できる。
  - _Requirements: 2.2, 2.4, 3.2, 3.3, 3.4, 6.3, 6.4_
  - _Boundary: OciPreflightCheck, RuntimeContractReuse_
  - _Depends: 3.1, 3.2_

- [x] 3.4 activate と rollback 操作を実装する
  - preflight 成功済み candidate だけを active image として記録し、previous image を rollback target として保持する。
  - rollback 操作で previous image へ戻せるようにし、Python 直起動への手動 rollback 判断材料も表示する。
  - 完了時点で、activate 後に active/previous が更新され、rollback 後に service 手動実行へ進める状態が分かる。
  - _Requirements: 3.3, 3.5, 5.1, 5.3, 5.4, 6.2, 6.4_
  - _Boundary: OciDeployController, DeployStateManifest_
  - _Depends: 3.3_

- [x] 4. Cloudflare-aware deploy runbook を追加する
- [x] 4.1 registry deploy の手動手順を文書化する (P)
  - build、push、pull、preflight、activate、rollback の段階を分け、各段階の成功条件と失敗時の停止位置を記載する。
  - registry credential は値ではなく必要な権限と入力方法だけを記載する。
  - 完了時点で、完全な CI/CD がなくても運用者が同じ判断基準で手動 deploy できる。
  - _Requirements: 1.4, 2.3, 3.4, 3.5, 5.2, 5.4, 5.5, 6.1, 6.2, 6.4, 6.5_
  - _Boundary: DeploymentRunbook_
  - _Depends: 1.2_

- [x] 4.2 Web 公開経路と管理経路の分離 checklist を文書化する (P)
  - Cloudflare proxied Web hostname を通常 SSH/rsync の必須接続先にしないことを明記する。
  - DNS-only SSH hostname と Cloudflare Tunnel / Access の確認手順を分けて記載する。
  - 完了時点で、proxied address を返す hostname が SSH/rsync 用として不適切かどうかを運用者が判別できる。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Boundary: NetworkPathChecklist, DeploymentRunbook_
  - _Depends: 1.2_

- [x] 4.3 既存 Docker 化メモから registry deploy runbook へ導線を追加する
  - source sync して OCI build する手順は第一段階の手順として残し、registry deploy へ移る場合の参照先を追記する。
  - SyncNow を長期的な本番反映の必須手段としない方針を明記する。
  - 完了時点で、既存メモを読んだ運用者が新しい registry deploy 手順へ迷わず移れる。
  - _Requirements: 1.4, 6.1, 6.2_
  - _Boundary: DeploymentRunbook_
  - _Depends: 4.1_

- [x] 5. 検証と失敗時の切り分けを追加する
- [x] 5.1 deploy helper の state と image reference 処理をテストする
  - tag/digest 形式、active/previous 更新、失敗時に active が変わらないことを検証する。
  - secret 値や実 IP を state に含めないことを確認する。
  - 完了時点で、state 更新と rollback target の扱いが自動テストで確認できる。
  - _Requirements: 1.2, 1.3, 3.1, 5.3, 6.5_
  - _Boundary: OciDeployController, DeployStateManifest_
  - _Depends: 3.4_

- [x] 5.2 preflight と activation gate をテストする
  - runtime file 不足や権限不備で preflight が失敗し、activate がブロックされることを検証する。
  - valid runtime inputs では external API を呼ばずに check が成功することを検証する。
  - 完了時点で、壊れた image/runtime が timer 実行対象へ接続されないことをテストで確認できる。
  - _Requirements: 2.4, 3.2, 3.3, 3.4, 6.3_
  - _Boundary: OciPreflightCheck, RuntimeContractReuse_
  - _Depends: 3.3_

- [x] 5.3 publish workflow と build context の安全性を検証する
  - workflow が image tag/digest を確認可能な形で残すことを検証する。
  - build context に `.env`、token、runtime files、workflow/deploy helper が入らないことを確認する。
  - 完了時点で、registry 配布 artifact と runtime secret が分離されていることを検証できる。
  - _Requirements: 1.1, 1.2, 2.1, 2.3, 6.3_
  - _Boundary: ImagePublishWorkflow, BuildContextGuard, RegistryAuthBoundary_
  - _Depends: 2.2_

- [x] 5.4 runbook の手順を dry-run 観点で検証する
  - 手動手順が build、registry、OCI pull、preflight、activate、runtime、rollback の段階に分かれていることを確認する。
  - DNS-only SSH と Tunnel の管理経路 checklist が Web 公開経路を変更しない内容になっていることを確認する。
  - 完了時点で、運用者が失敗段階を切り分け、rollback 後の確認まで辿れる runbook になっている。
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.4, 5.5, 6.1, 6.2, 6.4_
  - _Boundary: DeploymentRunbook, NetworkPathChecklist_
  - _Depends: 4.1, 4.2, 4.3_

- [x] 6. 統合確認と spec 整合性を仕上げる
- [x] 6.1 registry deploy 成果物の相互整合性を確認する
  - publish workflow、OCI helper、runbook、Dockerfile、`.dockerignore` の名前・変数・image reference の表記を揃える。
  - docs と helper の例が secret 値や実環境固有値を含まないことを確認する。
  - 完了時点で、手動 deploy の入口から rollback まで同じ語彙と変数名で追跡できる。
  - _Requirements: 2.3, 3.4, 3.5, 6.1, 6.2, 6.4, 6.5_
  - _Boundary: ImagePublishWorkflow, OciDeployController, DeploymentRunbook_
  - _Depends: 5.1, 5.2, 5.3, 5.4_

- [x] 6.2 existing app behavior が範囲外のまま維持されていることを確認する
  - Gmail fetch、LINE push、Gemini extraction、OAuth/LINE endpoint、systemd timer schedule を変更していないことを差分で確認する。
  - container check と既存テストを実行し、Docker 化成果物の contract が壊れていないことを確認する。
  - 完了時点で、この仕様の変更が deploy 運用境界に閉じていることを検証結果として説明できる。
  - _Requirements: 2.2, 5.1, 5.2, 6.5_
  - _Boundary: RuntimeContractReuse, DeploymentRunbook_
  - _Depends: 6.1_
