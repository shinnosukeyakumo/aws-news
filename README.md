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
| `model_id` | `us.anthropic.claude-sonnet-4-6` | Bedrock の推論プロファイル |
| `region` | `us-west-2` | Bedrock のリージョン |
| `backfill_days` | 3 | この日数より古い記事は対象外 |
| `max_articles_per_run` | 12 | 1 エージェントが 1 回で評価する上限 |
| `min_score` | 55 | この点数未満は Discord に流さない |

`defaults` の値はエージェント単位で上書きできる。

## 設計上の判断

**記事ごとに Agent インスタンスを作り直している**（`curator.py`）。
会話履歴を共有すると前の記事の判断が次の記事のスコアに引きずられるため、意図的に独立させた。
モデル接続（`BedrockModel`）だけは使い回している。

**要約を `summary` と `impact` に分けている**（`models.py`）。
1 つのフィールドに詰めると必ず 200 文字を超えて冗長になったため、
「何が起きたか」と「読者に何が効くか」を分離した。

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
  検証に使ったアカウント（017820658462）では Claude Opus 5 / Sonnet 5 / Opus 4.8 は
  `AccessDeniedException`（モデルアクセス未有効）となり、Sonnet 4.6 と Haiku 4.5 のみ利用できた。
  モデルアクセスを有効化すれば `defaults.model_id` の 1 行で切り替わる。

## ディレクトリ

```
config/sources.yaml   エージェントと情報源の定義（増やすのはここ）
src/awsnews/
  collect.py          RSS / sitemap からの収集と本文抽出（LLM を使わない決定的な処理）
  curator.py          Strands Agent による選別・要約
  models.py           Article / Curation のスキーマ。Curation は structured output の定義でもある
  store.py            既読管理（SQLite）
  discord.py          Discord Webhook への配信と dry-run 表示
  cli.py              収集 → 選別 → 配信のつなぎ
data/seen.db          既読 DB（gitignore 済み）
evals/                評価フェーズ用
```
