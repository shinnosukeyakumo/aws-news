"""選別結果の JSON から共有用ダッシュボードの HTML を組み立てる。

社内勉強会で画面を見ながら話すことを想定している。
スコア順に上から読める構成にし、閾値未満で見送った記事も
「なぜ載っていないか」が分かる形で残す。
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

JST = timezone(timedelta(hours=9))

# スコア帯。config/sources.yaml の「スコアの目安」と対応させている。
TIERS = [
    (80, "high", "要注目"),
    (55, "mid", "実装向け"),
    (30, "low", "限定的"),
    (0, "out", "参考"),
]


def _tier(score: int) -> tuple[str, str]:
    for threshold, key, label in TIERS:
        if score >= threshold:
            return key, label
    return "out", "参考"


def _jst(iso: str | None) -> str:
    if not iso:
        return "日付不明"
    try:
        return datetime.fromisoformat(iso).astimezone(JST).strftime("%-m/%-d")
    except ValueError:
        return "日付不明"


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _article_row(item: dict, adopted: bool) -> str:
    tier_key, tier_label = _tier(item["score"])
    tags = "".join(
        f'<li class="tag">{_esc(t)}</li>' for t in item.get("tags", [])[:3]
    )
    state = "adopted" if adopted else "held"
    return f"""
<article class="entry entry--{state}" data-score="{item['score']}">
  <div class="entry__score" aria-label="重要度 {item['score']}">
    <span class="score__value">{item['score']}</span>
    <span class="score__tier score__tier--{tier_key}">{tier_label}</span>
  </div>
  <div class="entry__body">
    <h3 class="entry__title">
      <a href="{_esc(item['url'])}" target="_blank" rel="noopener">{_esc(item['title_ja'])}</a>
    </h3>
    <p class="entry__summary">{_esc(item['summary'])}</p>
    <p class="entry__impact"><span class="impact__label">効き目</span>{_esc(item['impact'])}</p>
    <div class="entry__foot">
      <ul class="tags">{tags}</ul>
      <p class="entry__meta">
        <span class="meta__source">{_esc(item['source_label'])}</span>
        <span class="meta__date">{_jst(item.get('published_at'))}</span>
      </p>
    </div>
    <details class="entry__why">
      <summary>採点の理由</summary>
      <p>{_esc(item['reason'])}</p>
      <p class="why__original">原題: {_esc(item['title_original'])}</p>
    </details>
  </div>
</article>"""


def _section(agent: dict, items: list[dict]) -> str:
    min_score = agent["min_score"]
    adopted = [i for i in items if i["score"] >= min_score]
    held = [i for i in items if i["score"] < min_score]

    held_block = ""
    if held:
        held_block = f"""
  <details class="held">
    <summary class="held__summary">
      閾値 {min_score} 未満で見送った {len(held)} 件を表示
    </summary>
    <div class="entries entries--held">{''.join(_article_row(i, False) for i in held)}</div>
  </details>"""

    return f"""
<section class="lane" id="lane-{_esc(agent['key'])}">
  <header class="lane__head">
    <h2 class="lane__title">{_esc(agent['name'])}</h2>
    <p class="lane__stat">
      <span class="stat__adopted">{len(adopted)}</span> 件採用
      <span class="stat__sep">/</span> {len(items)} 件を精査
    </p>
  </header>
  <div class="entries">{''.join(_article_row(i, True) for i in adopted) or '<p class="empty">今週は閾値を超えた記事がなかった。</p>'}</div>
  {held_block}
</section>"""


def _topic_bars(articles: list[dict]) -> str:
    counts: dict[str, int] = {}
    for item in articles:
        for tag in item.get("tags", []):
            counts[tag] = counts.get(tag, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]
    top = [(k, v) for k, v in top if v > 1]
    if not top:
        return ""
    peak = max(v for _, v in top)
    rows = "".join(
        f"""<li class="topic">
      <span class="topic__name">{_esc(name)}</span>
      <span class="topic__bar"><span class="topic__fill" style="width: {count / peak * 100:.0f}%"></span></span>
      <span class="topic__count">{count}</span>
    </li>"""
        for name, count in top
    )
    return f"""
<section class="weight">
  <h2 class="weight__title">今週の重心</h2>
  <p class="weight__note">採点した記事に付いたタグの出現数。</p>
  <ul class="topics">{rows}</ul>
</section>"""


_STYLE = """
:root {
  color-scheme: light dark;

  --ground:      #f3f5f8;
  --surface:     #ffffff;
  --surface-alt: #e9edf2;
  --ink:         #141d27;
  --ink-soft:    #465a6e;
  --ink-faint:   #7b8b9d;
  --rule:        #d9e0e8;
  --rule-firm:   #bcc7d4;

  --accent:      #b45c06;
  --accent-wash: #f6e8d6;

  --tier-high:   #b45c06;
  --tier-mid:    #2f6d97;
  --tier-low:    #5f7488;
  --tier-out:    #8b9aab;

  --font-display: 'Archivo', 'Zen Kaku Gothic New', system-ui, sans-serif;
  --font-body:    'Zen Kaku Gothic New', system-ui, sans-serif;
  --font-mono:    'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace;

  --measure: 64ch;
  --radius: 3px;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground:      #0e141b;
    --surface:     #151d26;
    --surface-alt: #1c2631;
    --ink:         #e2e8ef;
    --ink-soft:    #a1b0c0;
    --ink-faint:   #74849a;
    --rule:        #26313e;
    --rule-firm:   #3a4a5c;

    --accent:      #e8963c;
    --accent-wash: #2c2317;

    --tier-high:   #e8963c;
    --tier-mid:    #6aa8d0;
    --tier-low:    #8798aa;
    --tier-out:    #66768a;
  }
}

:root[data-theme="dark"] {
  --ground:      #0e141b;
  --surface:     #151d26;
  --surface-alt: #1c2631;
  --ink:         #e2e8ef;
  --ink-soft:    #a1b0c0;
  --ink-faint:   #74849a;
  --rule:        #26313e;
  --rule-firm:   #3a4a5c;

  --accent:      #e8963c;
  --accent-wash: #2c2317;

  --tier-high:   #e8963c;
  --tier-mid:    #6aa8d0;
  --tier-low:    #8798aa;
  --tier-out:    #66768a;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font-family: var(--font-body);
  font-size: 15px;
  line-height: 1.75;
  -webkit-font-smoothing: antialiased;
}

.wrap {
  max-width: 1040px;
  margin: 0 auto;
  padding: 0 24px 96px;
}

/* ---------- ヘッダ ---------- */

.masthead {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px 32px;
  padding: 56px 0 24px;
  border-bottom: 2px solid var(--ink);
}

.masthead__id { display: flex; flex-direction: column; gap: 6px; }

.masthead__eyebrow {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: .16em;
  text-transform: uppercase;
  color: var(--accent);
}

.masthead__title {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(30px, 4.4vw, 44px);
  font-weight: 700;
  line-height: 1.12;
  letter-spacing: -.02em;
  text-wrap: balance;
}

.masthead__range { margin: 0; color: var(--ink-soft); font-size: 14px; }

.runinfo {
  display: grid;
  grid-template-columns: auto auto;
  gap: 4px 18px;
  margin: 0;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--ink-faint);
}
.runinfo dt { color: var(--ink-faint); }
.runinfo dd { margin: 0; color: var(--ink-soft); font-variant-numeric: tabular-nums; }

/* ---------- 今週の重心 ---------- */

.weight { padding: 36px 0 8px; }

.weight__title {
  margin: 0 0 4px;
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 600;
  letter-spacing: .01em;
}

.weight__note {
  margin: 0 0 18px;
  max-width: var(--measure);
  font-size: 13px;
  color: var(--ink-faint);
}

.topics { list-style: none; margin: 0; padding: 0; display: grid; gap: 7px; }

.topic {
  display: grid;
  grid-template-columns: minmax(0, 210px) 1fr 2.5ch;
  align-items: center;
  gap: 14px;
}

.topic__name {
  font-size: 13px;
  color: var(--ink-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topic__bar {
  height: 7px;
  background: var(--surface-alt);
  border-radius: 999px;
  overflow: hidden;
}

.topic__fill {
  display: block;
  height: 100%;
  background: var(--accent);
  opacity: .82;
  border-radius: 999px;
}

.topic__count {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--ink-faint);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

/* ---------- 担当領域の節 ---------- */

.lane { padding-top: 52px; }

.lane__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--rule-firm);
}

.lane__title {
  position: relative;
  margin: 0;
  padding-left: 14px;
  font-family: var(--font-display);
  font-size: 21px;
  font-weight: 600;
  letter-spacing: -.01em;
}

.lane__title::before {
  content: "";
  position: absolute;
  left: 0;
  top: .28em;
  width: 3px;
  height: .88em;
  background: var(--accent);
}

.lane__stat {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--ink-faint);
  font-variant-numeric: tabular-nums;
}

.stat__adopted { color: var(--ink); font-weight: 600; }
.stat__sep { color: var(--rule-firm); padding: 0 2px; }

.entries { display: flex; flex-direction: column; }

.empty { color: var(--ink-faint); font-size: 14px; padding: 20px 0; }

/* ---------- 記事 1 件 ---------- */

.entry {
  display: grid;
  grid-template-columns: 74px minmax(0, 1fr);
  gap: 22px;
  padding: 22px 0;
  border-bottom: 1px solid var(--rule);
}

.entry__score {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding-top: 2px;
}

.score__value {
  font-family: var(--font-mono);
  font-size: 25px;
  font-weight: 600;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}

.score__tier {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: .06em;
  padding: 1px 0 0;
  border-top: 2px solid currentColor;
  width: 100%;
  margin-top: 4px;
}
.score__tier--high { color: var(--tier-high); }
.score__tier--mid  { color: var(--tier-mid); }
.score__tier--low  { color: var(--tier-low); }
.score__tier--out  { color: var(--tier-out); }

.entry__body { display: flex; flex-direction: column; gap: 9px; min-width: 0; }

.entry__title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 600;
  line-height: 1.5;
  letter-spacing: -.005em;
  text-wrap: pretty;
}

.entry__title a {
  color: var(--ink);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: border-color .15s, color .15s;
}
.entry__title a:hover { color: var(--accent); border-bottom-color: var(--accent); }
.entry__title a:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
  border-radius: 2px;
}

.entry__summary {
  margin: 0;
  max-width: var(--measure);
  color: var(--ink-soft);
  font-size: 14px;
  line-height: 1.85;
}

.entry__impact {
  margin: 0;
  max-width: var(--measure);
  padding: 9px 13px;
  background: var(--accent-wash);
  border-left: 2px solid var(--accent);
  border-radius: 0 var(--radius) var(--radius) 0;
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--ink);
}

.impact__label {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: .1em;
  color: var(--accent);
  margin-right: 9px;
  white-space: nowrap;
}

.entry__foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  margin-top: 1px;
}

.tags { display: flex; flex-wrap: wrap; gap: 6px; list-style: none; margin: 0; padding: 0; }

.tag {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-soft);
  background: var(--surface-alt);
  padding: 2px 8px;
  border-radius: var(--radius);
}

.entry__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-faint);
  white-space: nowrap;
}
.meta__date { font-variant-numeric: tabular-nums; }

.entry__why { font-size: 12.5px; }

.entry__why summary {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-faint);
  cursor: pointer;
  width: fit-content;
  letter-spacing: .03em;
}
.entry__why summary:hover { color: var(--accent); }
.entry__why summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }

.entry__why p {
  margin: 7px 0 0;
  max-width: var(--measure);
  color: var(--ink-soft);
  line-height: 1.75;
}

.why__original {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-faint);
  word-break: break-word;
}

/* ---------- 見送り分 ---------- */

.held { margin-top: 18px; }

.held__summary {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--ink-faint);
  cursor: pointer;
  padding: 9px 0;
  width: fit-content;
  letter-spacing: .02em;
}
.held__summary:hover { color: var(--accent); }
.held__summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }

.entries--held { opacity: .72; }
.entries--held .entry { padding: 16px 0; }
.entries--held .score__value { font-size: 20px; color: var(--ink-faint); }
.entries--held .entry__title { font-size: 15px; }
.entries--held .entry__impact { display: none; }

/* ---------- 脚注 ---------- */

.colophon {
  margin-top: 64px;
  padding-top: 20px;
  border-top: 1px solid var(--rule);
  font-size: 12.5px;
  color: var(--ink-faint);
  max-width: var(--measure);
}
.colophon p { margin: 0 0 8px; }
.colophon code {
  font-family: var(--font-mono);
  font-size: 11.5px;
  background: var(--surface-alt);
  padding: 1px 5px;
  border-radius: var(--radius);
}

@media (max-width: 640px) {
  .wrap { padding: 0 18px 72px; }
  .entry { grid-template-columns: 54px minmax(0, 1fr); gap: 16px; }
  .score__value { font-size: 21px; }
  .topic { grid-template-columns: minmax(0, 130px) 1fr 2.5ch; gap: 10px; }
}

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
"""

_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=Archivo:wght@500;600;700&"
    "family=Zen+Kaku+Gothic+New:wght@400;500;700&"
    'family=IBM+Plex+Mono:wght@400;500;600&display=swap">'
)


def render(payload: dict, *, for_artifact: bool = False) -> str:
    """JSON ペイロードからダッシュボードの HTML を組み立てる。

    for_artifact=True のときは DOCTYPE / html / head / body を出さない。
    Artifact 側がそのスケルトンを付けるため。
    """
    articles = payload["articles"]
    agents = payload["agents"]
    generated = datetime.fromisoformat(payload["generated_at"]).astimezone(JST)

    dates = [
        datetime.fromisoformat(a["published_at"]).astimezone(JST)
        for a in articles
        if a.get("published_at")
    ]
    span = (
        f"{min(dates).strftime('%Y年%-m月%-d日')} 〜 {max(dates).strftime('%-m月%-d日')}"
        if dates
        else "対象期間なし"
    )

    adopted_total = sum(
        1
        for a in articles
        for g in agents
        if g["key"] == a["agent_key"] and a["score"] >= g["min_score"]
    )
    models = sorted({g["model_id"] for g in agents})

    lanes = "".join(
        _section(g, [a for a in articles if a["agent_key"] == g["key"]]) for g in agents
    )

    body = f"""
<div class="wrap">
  <header class="masthead">
    <div class="masthead__id">
      <p class="masthead__eyebrow">AWS &amp; LLM ベンダー 週次まとめ</p>
      <h1 class="masthead__title">今週の AI・クラウド動向</h1>
      <p class="masthead__range">{_esc(span)}</p>
    </div>
    <dl class="runinfo">
      <dt>採用</dt><dd>{adopted_total} / {len(articles)} 件</dd>
      <dt>採点</dt><dd>{_esc(', '.join(models))}</dd>
      <dt>生成</dt><dd>{generated.strftime('%Y-%m-%d %H:%M')} JST</dd>
    </dl>
  </header>

  {_topic_bars(articles)}
  {lanes}

  <footer class="colophon">
    <p>担当領域ごとのエージェントが記事を 0〜100 点で採点し、閾値を超えたものを採用している。
       見出し・要約・「効き目」はいずれも自動生成であり、原文にあたることを前提とした要約である。</p>
    <p>採点の根拠は各記事の「採点の理由」に残してある。基準そのものを変えたい場合は
       <code>config/sources.yaml</code> の <code>scoring</code> を編集する。</p>
  </footer>
</div>"""

    head = f"<title>今週の AI・クラウド動向</title>\n{_FONTS}\n<style>{_STYLE}</style>"

    if for_artifact:
        return f"{head}\n{body}\n"
    return (
        '<!DOCTYPE html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"{head}\n</head>\n<body>{body}</body>\n</html>\n"
    )


def build(json_path: Path, out_path: Path, *, for_artifact: bool = False) -> None:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(payload, for_artifact=for_artifact), encoding="utf-8")
