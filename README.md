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

定期実行は当面 cron で足りる。

```cron
0 9,18 * * * cd /path/to/aws-news && /path/to/uv run awsnews >> data/run.log 2>&1
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
  cli.py              収集 → 選別 → 配信のつなぎ
data/seen.db          既読 DB（gitignore 済み）
evals/                評価フェーズ用
```
