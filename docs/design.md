# ニュースサイト化の設計

Discord への配信をやめ、選別・要約した記事をスマホで読めるニュースサイトとして公開する。
サイトは定期的に自動で更新され、閲覧できるのは自分だけとする。

状態: 設計（2026-09-25）。未実装。

## 目的と前提

- Discord や Slack の埋め込みは幅が狭く、スマホで読みにくい。1 記事を 1 枚のカードとして読める画面にする
- Mac を閉じていても更新が止まらないよう、実行も配信も AWS 上で完結させる
- 閲覧者は自分 1 人。認証は軽いものでよいが、URL を知られただけで読める状態にはしない
- 収集・採点のロジック（`collect.py` / `curator.py` / `config/sources.yaml`）は変えない。変えるのは「結果をどこに溜め、どう見せるか」だけ

## 全体の流れ

```
EventBridge Scheduler（毎日 9:00 / 18:00 JST）
  └→ Lambda（コンテナイメージ）
       1. 情報源から記事を集める                 … collect.py（既存）
       2. 既読を DynamoDB で除外する             … store.py（置き換え）
       3. Bedrock（Nova 2 Lite）で採点・要約する … curator.py（既存）
       4. 採点結果を DynamoDB に書く
       5. 直近 30 日分を DynamoDB から読み、HTML を組み立てる … site.py（新規）
       6. HTML と JSON を S3 に置く
S3（非公開） ←OAC─ CloudFront ←HTTPS─ スマホ
                      └ CloudFront Functions で Basic 認証
```

採点（1〜4）とサイト生成（5〜6）を分けておく。
採点が一部失敗しても、DynamoDB に溜まっている分からサイトは作り直せる。

## 構成要素

### 1. 実行: Lambda（コンテナイメージ）+ EventBridge Scheduler

| 項目 | 値 | 理由 |
|---|---|---|
| ランタイム | Python 3.12 のコンテナイメージ（arm64） | `uv.lock` をそのまま使って依存を固定できる |
| メモリ | 1024 MB | 本文取得と 4 並列の Bedrock 呼び出しが主。CPU はほぼ使わない |
| タイムアウト | 15 分（上限） | 3 エージェント × 最大 12 件。Nova は 1 件 4 秒前後なので通常は 1〜2 分で終わる見込み |
| 再試行 | 0 回 | 失敗時に自動で再実行すると、Bedrock の呼び出しが二重になる。次の定期実行に任せる |
| スケジュール | `cron(0 9,18 * * ? *)`、タイムゾーン `Asia/Tokyo` | 現行 README の cron と同じ時刻 |

zip ではなくコンテナを選んだ理由: 依存の実サイズは 73 MB で、zip の上限（展開後 250 MB）にも収まる。
ただし CDK で zip を作る場合もビルドに Docker が要る。それなら `uv.lock` をそのまま使えるコンテナのほうが、ローカルと Lambda で依存がずれにくい。

### 2. データ: DynamoDB

SQLite（`data/seen.db`）は Lambda に置けないので DynamoDB に移す。
既読の記録だけでなく、採点結果の本文（見出し・要約・効き目など）もここに溜め、サイトの材料にする。

テーブル `articles`（オンデマンド課金）

| 属性 | 例 | 用途 |
|---|---|---|
| `pk`（パーティションキー） | `aws-ai` | エージェントの key |
| `sk`（ソートキー） | 記事 URL | 既読判定。同じ URL でもエージェントが違えば別扱い（現行の SQLite と同じ） |
| `feed` | `all`（固定値） | 下記 GSI 用 |
| `sort_at` | `2026-09-25T00:00:00+00:00` | 公開日。無ければ採点した日時 |
| `score` / `title_ja` / `summary` / `impact` / `reason` / `tags` | | 採点結果。`Curation` モデルと同じ |
| `title_original` / `source_label` / `published_at` | | 元記事の情報 |
| `status` | `curated` / `failed` | 採点に失敗した記事も記録し、再挑戦させない（現行と同じ扱い） |

GSI `by-date`（パーティションキー `feed`、ソートキー `sort_at`）で「全エージェントの新しい順」を 1 回の Query で取る。
記事は月に数百件の規模なので、パーティションを 1 つに寄せても負荷の問題は起きない。

ローカル開発では SQLite を使い続ける。`store.py` に共通のインターフェースを切り、SQLite 版と DynamoDB 版を差し替えられるようにする。

### 3. 配信: S3 + CloudFront

- S3 バケットは非公開。CloudFront から OAC（Origin Access Control）経由でだけ読ませる
- 置くファイルは `index.html`（直近 30 日）と `articles.json`（同じ内容のデータ）
- HTML は `Cache-Control: max-age=60`。更新は 1 日 2 回なので、キャッシュ削除（invalidation）を使わず短い TTL で済ませる
- ドメインは CloudFront の既定（`*.cloudfront.net`）。独自ドメインは今回は付けない

### 4. 認証: CloudFront Functions の Basic 認証

| 案 | 採否 | 理由 |
|---|---|---|
| CloudFront Functions で Basic 認証 | 採用 | 追加のサーバーが要らない。ブラウザがパスワードを覚えるので、2 回目以降は開くだけ |
| Cognito + Lambda@Edge | 不採用 | ログイン画面とトークン更新まで作ることになり、1 人用には重い |
| URL に秘密の文字列を付ける | 不採用 | 閲覧履歴や共有時に漏れる |

パスワードはコードにも CDK にも書かない。

- 正解の値（`ユーザー名:パスワード` の Base64）は CloudFront KeyValueStore に入れ、関数はそこから読む
- 値はデプロイ後に CLI で登録する。パスワード本体は 1Password に保管する
- CloudFront は HTTP を HTTPS にリダイレクトする設定にし、平文で認証情報が流れないようにする

未確認の点: iPhone の Safari が Basic 認証の入力をどこまで覚えてくれるか。
毎回聞かれて煩わしい場合は、初回だけ認証して長期間有効な Cookie を発行する方式に切り替える。実装後に実機で確かめる。

### 5. 画面

1 列のカードを新しい順に並べる。スマホ幅を基準に作り、PC では中央寄せにする。

```
┌──────────────────────────┐
│ AWS / LLM ニュース            │
│ 最終更新 9/25 18:02            │ ← 更新が止まったら気づけるように
│ [すべて][AWS AI][新機能][LLM]  │ ← 担当領域のタブ
├──────────────────────────┤
│ 92 要注目   9/25 AWS What's New │
│ Bedrock AgentCore に〜〜〜      │ ← 日本語の見出し（元記事へのリンク）
│ 要約 2 文                      │
│ ▸ 効き目 1 文                  │
│ #AgentCore #Strands            │
├──────────────────────────┤
│ …                            │
└──────────────────────────┘
  見送った記事（閾値未満）を表示 ▾   ← 畳んでおく。採点の理由が読める
```

- 閾値（`min_score`、現在 80）以上を「採用」として上に出す。閾値未満は畳んで残す
- スコアの色分けは既存の `dashboard.py` の 4 段階（要注目 / 実装向け / 限定的 / 参考）を流用する
- ダークモードに対応する（`prefers-color-scheme`）
- タブの切り替えは数行の JavaScript で行う。JavaScript が動かなくても全記事は読める

HTML は Lambda 側で完成させてから置く（サーバー側で組み立てる方式）。
ブラウザ側で JSON を読んで描画する方式より、スマホでの表示が速く、仕組みも単純になる。

## コードの変更点

| ファイル | 変更 |
|---|---|
| `src/awsnews/discord.py` | 削除。`--dry-run` の標準出力表示だけ `console.py` に移す |
| `src/awsnews/store.py` | インターフェースを切り、SQLite 版（ローカル用）と DynamoDB 版（Lambda 用）に分ける。採点結果の本文も保存する |
| `src/awsnews/site.py` | 新規。記事の一覧からニュースサイトの HTML を組み立てる |
| `src/awsnews/publish.py` | 新規。HTML と JSON を S3 に置く |
| `src/awsnews/handler.py` | 新規。Lambda の入口。全エージェントを回し、サイトを作り直して置く |
| `src/awsnews/cli.py` | Discord 関連の引数と処理を外す。`--site PATH` でローカルにサイトを書き出せるようにする |
| `src/awsnews/dashboard.py` | 残す。勉強会用の週次まとめとして引き続き使える |
| `infra/` | 新規。CDK（Python）のスタック一式 |
| `Dockerfile` | 新規。Lambda 用のコンテナイメージ |
| `.env.op` | `DISCORD_WEBHOOK_URL` を削除 |
| `README.md` | 構成・使い方・定期実行の節を書き換える |

CDK を Python にするのは、アプリ本体と言語を揃えるため。
代替案は TypeScript で、CDK の情報量はこちらが多いが、1 リポジトリに 2 言語の依存管理が入る。

## AWS リソース

デプロイ先は `default` プロファイルのアカウント、リージョンは `us-west-2`（現在 Bedrock を呼んでいる場所と同じ）。

| リソース | 主な設定 |
|---|---|
| DynamoDB テーブル | オンデマンド、GSI `by-date`、ポイントインタイムリカバリ有効 |
| S3 バケット | パブリックアクセス全ブロック、SSE-S3 |
| CloudFront ディストリビューション | OAC、HTTPS リダイレクト、CloudFront Functions（viewer-request） |
| CloudFront KeyValueStore | Basic 認証の正解値 |
| Lambda 関数 | コンテナイメージ、arm64、1024 MB、15 分 |
| EventBridge Scheduler | 1 日 2 回、`Asia/Tokyo` |
| IAM ロール（Lambda 用） | 下記の最小権限 |

Lambda に渡す権限

- `bedrock:InvokeModel` / `bedrock:InvokeModelWithResponseStream`: Nova 2 Lite の推論プロファイルと、その転送先リージョンの基盤モデルに限定
- `dynamodb:GetItem` / `BatchGetItem` / `PutItem` / `Query`: `articles` テーブルと GSI に限定
- `s3:PutObject`: サイト用バケットに限定

## 費用の見込み（概算・未実測）

| 項目 | 見込み |
|---|---|
| Bedrock（Nova 2 Lite） | 主な費用。1 日 2 回・最大 36 件の採点で、月に数十円〜数百円程度 |
| Lambda / EventBridge Scheduler | 無料枠に収まる |
| DynamoDB / S3 | 月に数円程度 |
| CloudFront / CloudFront Functions | 閲覧者 1 人なら無料枠に収まる |

Bedrock の実費は、ログに出しているトークン数から初回実行後に計算して確かめる。

## 進め方

1. **ローカルで作る**: `store.py` の分離、`site.py`、Discord の削除。`uv run awsnews --site data/site/index.html` で書き出し、ブラウザのスマホ表示で確かめる
2. **AWS に載せる**: CDK でデプロイし、パスワードを登録する。Lambda を手動で 1 回起動し、実機のスマホで開けることを確かめる
3. **仕上げ**: 以下は必要になってから

- ホーム画面に追加できるようにする（PWA のマニフェスト）
- 30 日より前の記事のアーカイブページ
- 実行失敗の通知（CloudWatch アラーム）。まずは画面の「最終更新」で止まったことに気づける状態にしておく
- CloudWatch Omni でエージェントのトレースを見る（`.env.omni` の送り先へ Lambda から OpenTelemetry で送る）

## 決めておきたいこと

- 更新の時刻と回数（案: 9:00 / 18:00 の 1 日 2 回）
- トップに並べる期間（案: 直近 30 日）
- 閾値未満の記事を画面に残すか（案: 畳んで残す）
