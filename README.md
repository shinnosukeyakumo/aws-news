# aws-news

AWS と LLM ベンダーのニュースを、担当領域ごとのエージェントが選別・要約して Discord に配信する。

RSS をそのまま転送するのではなく、各エージェントが自分の担当領域の基準で
「読者にとって重要か」を 0〜100 点で判定し、閾値を超えたものだけに
日本語の見出し・要約・「効き目」を付けて配信する。

```
情報源(RSS/sitemap) ─→ 収集 ─→ 既読を除外 ─→ エージェントが選別・要約 ─→ 閾値超えだけ Discord
                                                    (Bedrock / Strands Agents)
```

## エージェント構成

| key | 担当 | 情報源 |
|---|---|---|
| `aws-ai` | AWS の生成 AI 領域 | AWS AI Blog (旧 Machine Learning Blog) |
| `aws-whatsnew` | AWS の新機能アナウンス | AWS What's New（`general:products/aiml` で前段フィルタ） |
| `llm-vendors` | LLM ベンダーの発表 | OpenAI News / Google AI Blog / Anthropic |

各エージェントは「担当領域の説明（charter）」と「評価基準（scoring）」を持ち、
それが system prompt になる。同じコードが設定だけを差し替えて 3 体分動く。

## セットアップ

```bash
uv sync

# Discord Webhook URL を設定（1Password 運用）
op inject -i .env.op -o .env
# もしくは直接 export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

AWS の認証は通常のプロファイル解決に従う（`aws sts get-caller-identity` が通ればよい）。

## 使い方

```bash
# Discord に投げず、選別結果を標準出力で確認する（既読も記録しない）
uv run awsnews --dry-run --no-store

# 特定のエージェントだけ、件数を絞って試す
uv run awsnews --agent llm-vendors --limit 3 --dry-run --no-store

# 本番実行（閾値を超えたものを Discord へ投稿し、既読を記録する）
uv run awsnews

# 既読 DB の統計
uv run awsnews --stats
```

### 共有用ダッシュボードを作る

社内勉強会で画面を見ながら話すことを想定したまとめページを生成する。
Discord への投稿とは独立していて、こちらだけでも使える。

```bash
# 直近 7 日を集めてダッシュボードを生成する（Discord には投げない）
uv run awsnews --dry-run --no-store --days 7 --limit 18 \
  --dashboard data/dashboard.html

# Artifact に載せる場合は DOCTYPE / head / body を省いた形で出す
uv run awsnews --dry-run --no-store --days 7 --limit 18 \
  --dashboard data/dashboard.artifact.html --for-artifact
```

`--dashboard` を付けると同じ場所に `.json` も残る。HTML だけ作り直したいときは
JSON から再生成できるので、記事の採点をやり直す必要はない。

```python
from pathlib import Path
from awsnews import dashboard
dashboard.build(Path("data/dashboard.json"), Path("data/dashboard.html"))
```

ページの構成は、担当領域ごとの節を上から読める並びにしてある。
各記事は左にスコア、右に見出し・要約・「効き目」。閾値未満で見送った記事も
節の末尾に畳んであり、「なぜ載っていないか」を採点の理由から追える。

### 定期実行

当面は cron で足りる。

```cron
0 9,18 * * * cd /path/to/aws-news && /path/to/uv run awsnews >> data/run.log 2>&1
# 週次まとめ（月曜朝）
0 8 * * 1 cd /path/to/aws-news && /path/to/uv run awsnews --days 7 --limit 18 --dashboard data/dashboard.html >> data/run.log 2>&1
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
    scoring: |
      高く評価する: ...
      低く評価する: ...
```

情報源の `type` は 2 種類。

- `rss` — RSS / Atom フィード。`include_categories` で category による前段フィルタができる
- `sitemap` — RSS を出していないサイト向け。`lastmod` で新着を拾い、記事ページから本文と公開日を取る

## 主な設定（`config/sources.yaml` の `defaults`）

| キー | 既定値 | 意味 |
|---|---|---|
| `model_id` | `us.amazon.nova-2-lite-v1:0` | Bedrock の推論プロファイル |
| `region` | `us-west-2` | Bedrock のリージョン |
| `reasoning_effort` | `off` | 思考モード。`off` / `low` / `medium` / `high` |
| `temperature` | 0.3 | Nova は 0 にすると同じ文を繰り返す癖があるため 0 にしない |
| `backfill_days` | 3 | この日数より古い記事は対象外 |
| `max_articles_per_run` | 12 | 1 エージェントが 1 回で評価する上限 |
| `min_score` | 80 | この点数未満は Discord に流さない |

`defaults` の値はエージェント単位で上書きできる。
モデル比較のときは実行時にも上書きできる。

```bash
uv run awsnews --agent llm-vendors --limit 6 --dry-run --no-store --min-score 0 \
  --model us.anthropic.claude-haiku-4-5-20251001-v1:0
```

## モデル選択（2026-09-05 実測）

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

**閾値はモデルとセットで調整すること。** `min_score` の 80 は Nova 前提の値であり、
Haiku / Sonnet に切り替えるなら 55 前後に戻す。

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

全 3 エージェントを 1 回通した実測: 入力 56,262 / 出力 4,924 トークン。

`us-west-2` の Nova 2.0 Lite は入力 $0.33 / 1M、出力 $2.75 / 1M（AWS Price List API より取得）
なので **1 回あたり約 $0.032**。1 日 2 回なら月 $2 程度に収まる。

Claude Haiku 4.5 / Sonnet 4.6 の Bedrock 価格は、Price List API にも
公開価格ページにも該当エントリが見つからず、本リポジトリでは確認できていない。

## 設計上の判断

**記事ごとに Agent インスタンスを作り直している**（`curator.py`）。
会話履歴を共有すると前の記事の判断が次の記事のスコアに引きずられるため、意図的に独立させた。
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

## 現状の制約（2026-09-05 時点で実測）

- **Anthropic は RSS を公開していない。** `/rss.xml` `/feed.xml` `/news/rss.xml`
  `/engineering/rss.xml` いずれも 404。sitemap.xml の `lastmod` から新着を拾っている。
  `lastmod` は更新日で公開日ではないため、記事ページ本文の日付表記を優先して使う。
- **JS で本文を描画するページからは本文を取れない。** 例: OpenAI のシステムカード系ページ。
  この場合は RSS の description（150 文字程度）だけで評価することになり、
  エージェントは「判断材料が不足している」と reason に記した上でスコアを控えめに付ける。
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
  store.py            既読管理（SQLite）
  discord.py          Discord Webhook への配信と dry-run 表示
  dashboard.py        共有用ダッシュボード（HTML）の組み立て
  cli.py              収集 → 選別 → 配信のつなぎ
data/seen.db          既読 DB（gitignore 済み）
evals/                評価フェーズ用
```
