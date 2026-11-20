# aws-news

AWS の新機能アナウンス（What's New）と AWS の AI ブログを、担当ごとのエージェントが要約し、
スマホと PC で読めるニュースサイト（1 枚の HTML）にする。

記事ごとに日本語の見出し・要約・「何が変わるか」、主題の AWS サービス名（タグ）、
カテゴリ（18 分類）、注目度（★1〜3）、日本のリージョンで使えるかを付ける。
全部を一覧に出し、選んだサービスの選んだ種類の新着だけを Slack に通知する。
お気に入りのカテゴリ・保存した記事・保存した絞り込み条件は「マイライブラリ」に残り、端末をまたいで揃う。

```
情報源(RSS) ─→ 収集 ─→ 既読を除外 ─→ エージェントが要約 ─→ 保管 ─┬→ サイトを生成
                                        (Bedrock / Strands Agents)   └→ 通知対象を Slack へ
```

AWS 上では東京リージョン（ap-northeast-1）で 1 日 2 回（9:00 / 18:00 JST）動き、
re:Invent の前後（2026 年は 11/16〜12/6）だけは 3 時間おきに動く。
CloudFront の Basic 認証の内側でサイトを配信する。設計は `docs/design.md`、CDK は `infra/` にある。

## エージェント構成

| key | 担当 | 情報源 |
|---|---|---|
| `aws-ai` | AWS の生成 AI 領域 | AWS AI Blog (旧 Machine Learning Blog) |
| `aws-whatsnew` | AWS の新機能アナウンス | AWS What's New（全サービス） |

各エージェントは「担当領域の説明（charter）」を持ち、それが system prompt になる。
同じコードが設定だけを差し替えて 2 体分動く。

What's New は平日 1 日 10〜20 件ほど出る（2026-11-14 に RSS で数えた）。
1 回の上限は 60 件にしてあり、re:Invent の時期にあふれた分は次の回に回る。

## セットアップ

```bash
uv sync
```

AWS の認証は通常のプロファイル解決に従う（`aws sts get-caller-identity` が通ればよい）。

## 使い方

```bash
# 集めて要約し、既読と記事を保管してサイトを書き出す
uv run awsnews --site data/site.html

# 保管せずに試す（同じ記事で繰り返し要約したいとき）
uv run awsnews --no-store --days 7 --site data/site.html

# 特定のエージェントだけ、件数を絞って試す
uv run awsnews --agent aws-whatsnew --limit 3 --no-store

# 要約し直さず、保管済みの記事だけでサイトを作り直す（画面の調整用）
uv run awsnews --site-only --site data/site.html

# 既読 DB の統計
uv run awsnews --stats
```

要約の結果は毎回標準出力にも出る。`--site-only` は保管済みの記事しか使わないため、
`--no-store` で試した分は載らない。

### サイトの作り

- 上から、検索・期間（今週 / 先週 / 今月 / 先月 / すべて。日本時間で月曜はじまり）・カテゴリのタブ・並び順（日付順 / 注目度順）
- 一覧は日付ごとにまとまる。記事を選ぶと、PC（横幅 1024px 以上）は右の欄に、スマホは全画面で詳細が出る
- 「絞り込み」では注目度・情報源・種類・東京リージョンで使えるか・カテゴリとサービスで絞れる。
  カテゴリとサービスの ♡ でお気に入りにすると、カテゴリのタブの先頭に並ぶ
- 「新着」は前回ページを閉じた後に出た記事。初めて開いたときは更新の 24 時間前より後
- キーボードで操作できる（`j` / `k` で移動、`o` で原文、`s` で保存、`/` で検索、`f` で絞り込み、`l` でライブラリ、`?` で一覧）
- 直近 `site.days`（60）日の記事を載せる
- 通知設定と、ライブラリの端末間の同期は AWS 上のサイトでだけ使える
  （受け口の `/api/*` が CloudFront の裏にしか無いため）。ローカルで書き出したページでは、ライブラリはブラウザの中にだけ残る
- 注目度・カテゴリ・国内リージョンは要約のときにモデルが付ける。これらを持たない古い記事は、
  カテゴリだけタグから当てて出す（注目度は空）。埋め戻しは下の「古い記事を要約し直す」

### AWS に載せる

```
EventBridge Scheduler（9:00 / 18:00 JST）→ Lambda（コンテナ, arm64）→ DynamoDB / Bedrock（jp. Nova 2 Lite）
                                                      ├→ Slack（Incoming Webhook。URL は Secrets Manager）
                                                      └→ S3 ←OAC─ CloudFront（CloudFront Functions で Basic 認証）
                                       /api/* ─→ Lambda（Function URL, IAM 認証 + OAC）→ DynamoDB
```

Docker が要る。CDK は `infra/` の中で動かす。

```bash
cd infra
uv sync
npx -y aws-cdk@2.1145.0 deploy
```

CLI の版を固定しているのは、`aws-cdk-lib` 2.273.0 が読めるクラウドアセンブリの版に合わせるため。
`aws-cdk-lib` を上げるときは、CLI も合わせて上げる。

イメージの push が `Waiting` のまま進まないときは、回線より先に Mac を疑う。
2026-11-03 には、Docker Desktop を再起動しても、Docker を通さず crane や aws s3 cp で送っても止まり、
Mac を再起動したら通った（AWS 向けの TCP 接続が送信キューを積んだまま止まっていた）。

サイトの `/api/*` は、CloudFront の裏の Lambda（Function URL、IAM 認証 + OAC）が
サイトと同じ Basic 認証を通ってから受ける。

| メソッドとパス | 中身 |
|---|---|
| `GET /api/library` | マイライブラリ（お気に入り・保存した記事・保存した条件） |
| `POST /api/library` | マイライブラリを丸ごと置き換える（`updated_at` が新しい方が勝つ） |
| `GET /api/settings` | 通知するサービスと種類 |
| `POST /api/settings` | 通知するサービスと種類を置き換える |

どちらも articles テーブルの `pk="#settings"` の項目（`sk="notify"` / `sk="library"`）に置く。
受け口の Lambda が触れるのはこの項目だけ（IAM の `dynamodb:LeadingKeys` で絞っている）。

#### 古い記事を要約し直す

注目度などの項目を足したときは、Curator の Lambda を手で呼んで埋め戻す。
直近 N 日の記事のうち `importance` を持たないものを、記事ページを取り直して最大 M 件要約し直す。
一度で終わらなければ、`targets` が 0 になるまで繰り返す（15 分の上限に収めるため件数で区切っている）。

```bash
aws lambda invoke --function-name <FunctionName> \
  --payload '{"recurate_days": 60, "limit": 120}' --cli-binary-format raw-in-base64-out out.json
```

通知するサービスと記事の種類は、サイト右上の「通知設定」で選ぶ。種類は要約のときにモデルが 1 つ付ける。

| 種類 | 例 |
|---|---|
| 新サービス | これまで無かったサービスの発表 |
| 新機能 | 既存サービスへの機能追加。Bedrock で使えるモデルが増えた場合も含む |
| 対応の拡大 | リージョン、インスタンスタイプやサイズ、対応バージョンの追加 |
| 解説・事例 | ブログの使い方の解説、構築例、導入事例 |
| 料金・その他 | 料金の改定、名前の変更、提供終了など |

通知するのは「選んだサービス × 選んだ種類」に当たる記事と、生成 AI の新サービスだ。
後者は名前がまだリストに無いので、サービスも種類も問わずに送る。
保存先は articles テーブルの `pk=#settings, sk=notify` の 1 項目で、まだ保存していなければ
`site.notify_default` と `site.notify_kinds_default` を使う。
1 回の実行で、当たった新着を Slack に 1 通（最大 20 件）で送る。

Slack の Webhook の URL もコードと CDK には書かない。CDK が作るシークレット
`aws-news/slack-webhook` に、デプロイ後に URL を入れる。入れるまでは通知を送らない
（`https://hooks.slack.com/` で始まらない値は無視する）。

```bash
aws secretsmanager put-secret-value --region ap-northeast-1 \
  --secret-id aws-news/slack-webhook --secret-string 'https://hooks.slack.com/services/...'
```

パスワードはコードにも CDK にも書かない。デプロイ後に、出力の `AuthStoreArn` の
KeyValueStore へキー `basic`（値は `ユーザー名:パスワード` の Base64）を登録する。
キーが無いあいだは誰も通さない。

KeyValueStore は CloudFront の一部なので、リージョンは `us-east-1` を指定する。

```bash
ARN=$(jq -r .AwsNews.AuthStoreArn infra/cdk-outputs.json)
ETAG=$(aws cloudfront-keyvaluestore describe-key-value-store --region us-east-1 \
  --kvs-arn "$ARN" --query ETag --output text)
aws cloudfront-keyvaluestore put-key --region us-east-1 --kvs-arn "$ARN" --key basic \
  --value "$(printf '%s' 'ユーザー名:パスワード' | base64)" --if-match "$ETAG"
```

手動で 1 回動かすときは、出力の `FunctionName` を呼ぶ。

```bash
aws lambda invoke --region ap-northeast-1 --function-name <FunctionName> /dev/stdout
```

### 定期実行

AWS に載せずローカルで回すなら cron で足りる（Slack 通知は AWS 上でだけ送る）。

```cron
0 9,18 * * * cd /path/to/aws-news && /path/to/uv run awsnews --site data/site.html >> data/run.log 2>&1
```

## エージェントを増やす

`config/sources.yaml` の `agents:` に 1 ブロック足すだけでよい。コードの変更は要らない。

```yaml
  - key: security
    name: セキュリティ担当
    emoji: "🛡️"
    color: 0xE01E5A
    sources:
      - type: rss
        url: https://example.com/feed/
        label: 媒体名
        fetch_body: true          # RSS の description が短い媒体で使う
    charter: |
      このエージェントが何者で、誰に向けて書くか。
```

情報源の `type` は 2 種類。

- `rss` — RSS / Atom フィード。`include_categories` で category による前段フィルタもできる（今は使っていない）
- `sitemap` — RSS を出していないサイト向け。`lastmod` で新着を拾い、記事ページから本文と公開日を取る

## 主な設定（`config/sources.yaml` の `defaults`）

| キー | 既定値 | 意味 |
|---|---|---|
| `model_id` | `jp.amazon.nova-2-lite-v1:0` | Bedrock の推論プロファイル（東京・大阪で処理） |
| `region` | `ap-northeast-1` | Bedrock のリージョン |
| `reasoning_effort` | `off` | 思考モード。`off` / `low` / `medium` / `high` |
| `temperature` | 0.3 | Nova は 0 にすると同じ文を繰り返す癖があるため 0 にしない |
| `backfill_days` | 3 | この日数より古い記事は対象外 |
| `max_articles_per_run` | 12 | 1 エージェントが 1 回で要約する上限（What's New は 60） |

`defaults` の値はエージェント単位で上書きできる。
モデル比較のときは実行時にも上書きできる。

```bash
uv run awsnews --agent aws-whatsnew --limit 6 --no-store \
  --model us.anthropic.claude-haiku-4-5-20251001-v1:0
```

## モデル選択（2026-09-05 実測、点数を付けていた頃の記録）

2026-11-14 に点数付けをやめ、LLM ベンダーの担当（`llm-vendors`）も外した。
以下はそれ以前の比較で、モデルの癖とプロンプトの書き方の記録として残している。

同一の記事 6 件（`llm-vendors`）に同じプロンプトで付いたスコア。

| 記事 | Nova 2 Lite | Nova 2 Lite (thinking medium) | Haiku 4.5 | Sonnet 4.6 |
|---|---|---|---|---|
| GPT-6 Astra 発表（Bedrock でも提供） | 95 | 95 | 72 | 82 |
| Gemini 3.8 Flash Cyber / Fairwind | 85 | 85 | 62 | 22 |
| Playco のゲーム開発事例 | 75 | 85 | 45 | 28 |
| Legora の財務諸表事例 | 75 | 70 | 35 | 32 |
| GPT-6 Astra 安全性概要（本文取得不可） | 85 | 70 | 35 | 52 |
| OpenAI 10 億ドル拠出 | 30 | 20 | 15 | 12 |
| **所要時間** | 4 秒 | 90 秒 | 25 秒 | 24 秒 |

読み取れること。

- **Nova はスコアが高値に張り付き、判別の粒度が粗い。** `aws-ai` では 12 件中 8 件が
  同点（85）になり、閾値をどこに置いても中間の切り分けができない。
  事例紹介（Playco / Legora）にも 75 を付けるため、閾値を 80 まで上げて実用にしている。
- **thinking を入れても判別力は上がらない。** medium にすると所要時間が 20 倍を超える一方、
  Playco の事例紹介はむしろ 75 → 85 に上がった。盛れば良いというものではない。
- **Haiku 4.5 は Nova より判別が効く。** 事例紹介を閾値以下に落とせる。
- **Sonnet 4.6 が最も基準に忠実。** ただし他モデルより高コスト。

**閾値はモデルとセットで調整すること。** 当初は Nova 前提で 80 にしていたが、
80 以上が「発表」の帯だったため実装の解説記事が全部落ちた。種類をタブで分けた今は 55 にしている。

### 追試: 評価基準の書き方でモデル差は縮む

上表は `scoring` に「高く評価する / 低く評価する」を散文で書いていたときの結果。
そこにスコア帯の定義と判定指針を足して測り直した。

```yaml
scoring: |
  スコアの目安:
    80-100: 新モデルのリリース、API の破壊的変更、エージェント開発に直接効く新機能。
    55-79 : 実装判断の参考になる技術レポート、性能・安全性の検証結果。
    30-54 : 技術的な内容を含むが、読者の実装判断には直接効かないもの。
    0-29  : 導入事例・資金調達・提携・政策提言・一般消費者向け機能の紹介。
  判定の指針:
    MUST: 「A 社が X を使って業務を N% 改善した」形の導入事例は、
          API 仕様やモデル機能の新情報を含まない限り 30 点未満とせよ。
```

| 記事 | Nova（前 → 後） | Haiku（前 → 後） | Sonnet（前 → 後） |
|---|---|---|---|
| GPT-6 Astra 発表 | 95 → 95 | 72 → 82 | 82 → 88 |
| Playco のゲーム開発事例 | **75 → 30** | 45 → 25 | 28 → 18 |
| Legora の財務諸表事例 | **75 → 30** | 35 → 22 | 32 → 18 |
| OpenAI 10 億ドル拠出 | 30 → 20 | 15 → 15 | 12 → 12 |

判定指針を 2 行足しただけで、Nova が導入事例を 30 点未満に落とすようになった。
**Nova は判断を委ねると粗いが、基準を書き切れば従う。**
判別力の差はモデルの地力よりも、基準をどこまで言語化したかに依存する。

一方で Nova 固有の癖も残る。

- **スコアが帯の境界値に張り付く。** 帯を定義すると、その境界（55 / 75 / 85）ばかりを出す。
  `aws-ai` の 12 件は 75 が 8 件、55 が 3 件、80 が 1 件だった。
  Sonnet のように連続的には散らないので、**4 段階の分類器として扱う**のが実態に合う。
- **プロンプトの書き方が Claude より強く効く。** セクション見出し、`MUST` / `DO NOT` の命令形、
  長文を先頭・指示を末尾、そして**出力の手本を 1 つ示すこと**。
  手本を入れる前は multimodal を「多モーダル」と誤訳し、nightly を英語のまま残し、
  敬体が混入し、記事に無い製品名をタグに入れていた。手本を足すとこれらが消えた。
- **手本には実在の記事を使わない。** 手本と同じ記事が入力に来ると、文をそのまま写す。
  そのため `config.py` の手本は架空のサービス名にしてある。
- **impact の具体性は Sonnet に一歩劣る。** 「〜が得られる」という一般論に流れやすい。

トークン消費は 3 モデルでほぼ同等（同じ 6 記事で入力 14K〜16K）。
ただし Haiku 4.5 だけ 25K〜33K と多く、単価の安さがコスト優位につながらない。

### 実測コスト（Nova 2 Lite）

当時の全 3 エージェントを 1 回通した実測: 入力 56,262 / 出力 4,924 トークン。

`us-west-2` の Nova 2.0 Lite は入力 $0.33 / 1M、出力 $2.75 / 1M（AWS Price List API より取得）
なので **1 回あたり約 $0.032**。1 日 2 回なら月 $2 程度に収まる。

Claude Haiku 4.5 / Sonnet 4.6 の Bedrock 価格は、Price List API にも
公開価格ページにも該当エントリが見つからず、本リポジトリでは確認できていない。

## 設計上の判断

**記事ごとに Agent インスタンスを作り直している**（`curator.py`）。
会話履歴を共有すると前の記事の判断が次の記事の要約に引きずられるため、意図的に独立させた。
モデル接続（`BedrockModel`）だけは使い回している。

**要約を `summary` と `impact` に分けている**（`models.py`）。
1 つのフィールドに詰めると必ず 200 文字を超えて冗長になったため、
「何が起きたか」と「読者に何が効くか」を分離した。

**モデルごとの方言を `modelspec.py` に閉じ込めている。**
思考モードの指定フィールドは Nova が `reasoningConfig`、Claude が `thinking` で、
片方の形式をもう片方に送ると `ValidationException` になる。
呼び出し側は `reasoning_effort` に `off` / `low` / `medium` / `high` と書くだけでよい。

**プロンプトを Nova 流に構造化している**（`config.py` / `curator.py`）。
`# Core Mandates` などのセクション見出しと `MUST` / `DO NOT` の命令形を使い、
記事本文を `DOCUMENT START` / `DOCUMENT END` で囲んで先頭に置き、指示を末尾に置く。
Nova は Claude 流の自然な依頼文だと精度が落ちるため。この形は Claude に投げても
精度を落とさないので、モデル別にプロンプトを分けてはいない。

**本文抽出に専用ライブラリを入れていない**（`collect.py`）。
LLM に渡すのに足る密度があればよく、`<script>`/`<style>` を落として
`<article>`/`<main>` 内の `<p>` を拾えば実用上足りることを実測で確認した。

## 現状の制約

- **JS で本文を描画するページからは本文を取れない。** その場合は RSS の description
  （150 文字程度）だけで要約する。sitemap 型の情報源（RSS を出していないサイト向け）は
  `llm-vendors` で Anthropic を拾うのに使っていた。今は使っていないがコードは残してある。
- **利用モデルはアカウントのモデルアクセスに依存する。**
  検証に使った AWS アカウントでは Claude Opus 5 / Sonnet 5 / Opus 4.8 は
  `AccessDeniedException`（モデルアクセス未有効）となり、Sonnet 4.6 / Haiku 4.5 /
  Nova 系のみ利用できた。`bedrock list-inference-profiles` が `ACTIVE` を返しても
  モデルアクセスがあるとは限らないため、疎通は実際に `converse` を叩いて確かめること。
  Nova Premier は Legacy 扱いで `ResourceNotFoundException` になる（EOL 2026-09-14）。

## ディレクトリ

```
config/sources.yaml   エージェントと情報源の定義（増やすのはここ）
src/awsnews/
  collect.py          RSS / sitemap からの収集と本文抽出（LLM を使わない決定的な処理）
  curator.py          Strands Agent による選別・要約とトークン集計
  modelspec.py        モデルごとの方言（思考モードの指定フィールド）の吸収
  models.py           Article / Curation のスキーマ。Curation は structured output の定義でもある
  store.py            既読管理とサイト用の記事の保管（SQLite / DynamoDB）
  site.py             ニュースサイト（1 枚の HTML）の組み立て
  console.py          要約の結果の標準出力表示
  cli.py              収集 → 要約 → 保管 → サイト生成のつなぎ
  handler.py          Lambda の入口（DynamoDB 版の台帳を使い、Slack に通知し、S3 に置く）
  notify.py           通知の設定（サービスと種類）と Slack への送信
  api.py              サイトの /api/* の受け口（マイライブラリ、通知設定）
  library.py          マイライブラリの保管（articles の pk="#settings", sk="library"）
  categories.py       カテゴリ 18 分類の表と、タグからカテゴリを当てる規則
  publish.py          サイトを S3 に置く
infra/                CDK（Python）。Lambda / DynamoDB / S3 / CloudFront / Scheduler
Dockerfile            Lambda 用のコンテナイメージ
data/seen.db          既読と記事の DB（gitignore 済み）
evals/                評価フェーズ用
```
