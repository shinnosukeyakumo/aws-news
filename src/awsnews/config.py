"""config/sources.yaml の読み込み。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SourceConfig:
    type: str                      # "rss" | "sitemap"
    url: str
    label: str
    include_categories: tuple[str, ...] = ()
    path_prefixes: tuple[str, ...] = ()
    # RSS の description が短い媒体向け。記事ページを取得して本文を補う。
    fetch_body: bool = False
    # この文字数を下回るときだけ本文を取りに行く（無駄な HTTP を避ける）
    body_min_chars: int = 1000


@dataclass(frozen=True)
class AgentConfig:
    key: str
    name: str
    emoji: str
    color: int
    charter: str
    scoring: str
    sources: tuple[SourceConfig, ...]
    model_id: str
    region: str
    backfill_days: int
    max_articles_per_run: int
    min_score: int
    # "off" / "low" / "medium" / "high"。モデルごとの方言は modelspec.py が吸収する。
    reasoning_effort: str
    temperature: float
    # 全担当共通の重要度の段階と、記事の種類の定義。system prompt に入る。
    tiers: str = ""
    categories: tuple[tuple[str, str], ...] = ()

    @property
    def system_prompt(self) -> str:
        """このエージェントの人格と判断基準。選別と要約の両方に効く。

        Amazon Nova は Claude 流の自然な依頼文だと精度が落ちるため、
        セクション見出しと DO / DO NOT の命令形で構造化している。
        この形は Claude に投げても精度を落とさないので、モデル別に分けていない。
        """
        return (
            f"# Core Mandates\n{self.charter.strip()}\n\n"
            f"# Scoring Criteria\n{self.tiers.strip()}\n\n{self.scoring.strip()}\n\n"
            "# Category\n"
            "category には次のうち最も当てはまる key を 1 つ選べ。\n"
            + "".join(f"  {k}: {v}\n" for k, v in self.categories)
            + "\n"
            "# Output Formatting\n"
            "MUST: 日本語で書く。常体（である調）で簡潔に書く。\n"
            "MUST: 字数の上限を守る。title_ja は 40 文字、summary は 120 文字、"
            "impact は 80 文字を超えてはならない。超えそうなら要素を削る。\n"
            "MUST: 製品名・サービス名は原語表記のまま使う（例: Amazon Bedrock AgentCore）。\n"
            "MUST: 外来語は一般的な定訳のカタカナ表記を使え"
            "（multimodal はマルチモーダル、nightly は夜間）。\n"
            "MUST: tags は記事本文に実際に登場する製品名・技術名だけを挙げよ。\n"
            "DO NOT: 記事に書かれていない事実を補うな。推測を書くな。\n"
            "DO NOT: 記事に出てこない製品名を tags に入れるな。\n"
            "DO NOT: 日本語の文の中に英単語をそのまま混ぜるな。\n"
            "DO NOT: 「〜な世界が広がります」「〜は必見です」のような煽り文句を使うな。\n"
            "DO NOT: 「〜が可能になる」「〜が理解できる」のような一般論で impact を埋めるな。"
            "何がどう変わるかを具体的に書け。\n"
            "DO NOT: 同じ文や似た文を繰り返すな。\n\n"
            "# Example\n"
            "以下は書きぶりの手本であって実在の記事ではない。\n"
            "文の長さ・具体性の水準・常体の語調だけを参考にせよ。\n"
            "DO NOT: この例文に出てくる語句・製品名・内容を出力に持ち込むな。\n"
            "  title_ja: 架空サービスの入力フィルタが画像に対応\n"
            "  summary: 架空サービスの入力フィルタが画像の検査に対応した。"
            "テキストと同じポリシー定義で画像も扱え、追加のモデル呼び出しは要らない。\n"
            "  impact: 画像を受けるエージェントで、画像用のフィルタを別途実装する必要がなくなる。\n"
            "  reason: 既存構成をそのまま置き換えられる機能追加であり、実装の削減に直結する。\n"
            "  tags: 架空サービス, 入力フィルタ\n"
        )


@dataclass(frozen=True)
class WatchConfig:
    name: str
    pattern: str


@dataclass(frozen=True)
class SiteConfig:
    """ニュースサイトの表示に関わる設定。採点には効かない。"""

    title: str
    days: int
    min_score: int
    watch: tuple[WatchConfig, ...]
    # 別名 → 正式名
    tag_aliases: dict[str, str] = field(default_factory=dict)

    def normalize_tags(self, tags: list[str]) -> list[str]:
        """別名を正式名に揃え、重複を落とす。表にないタグはそのまま残す。"""
        folded = {k.casefold(): v for k, v in self.tag_aliases.items()}
        return list(dict.fromkeys(folded.get(t.strip().casefold(), t.strip()) for t in tags))


def load_site(path: Path) -> SiteConfig:
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    site = raw.get("site", {})
    aliases: dict[str, str] = {}
    for canonical, others in (site.get("tag_aliases") or {}).items():
        for alias in [canonical, *(others or [])]:   # 正式名の大文字小文字違いも揃える
            aliases[alias] = canonical
    return SiteConfig(
        title=site.get("title", "aws-news"),
        days=int(site.get("days", 30)),
        min_score=int(raw.get("defaults", {}).get("min_score", 55)),
        watch=tuple(WatchConfig(w["name"], w["pattern"]) for w in site.get("watch", [])),
        tag_aliases=aliases,
    )


def load_agents(path: Path, only: list[str] | None = None) -> list[AgentConfig]:
    """YAML を読んで AgentConfig の一覧を返す。

    Args:
        path: sources.yaml のパス
        only: 指定があればその key のエージェントだけに絞る
    """
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {})
    categories = tuple((str(k), str(v)) for k, v in (raw.get("categories") or {}).items())
    _check_categories(categories)

    agents: list[AgentConfig] = []
    for entry in raw.get("agents", []):
        if only and entry["key"] not in only:
            continue
        sources = tuple(
            SourceConfig(
                type=s["type"],
                url=s["url"],
                label=s["label"],
                include_categories=tuple(s.get("include_categories", ())),
                path_prefixes=tuple(s.get("path_prefixes", ())),
                fetch_body=bool(s.get("fetch_body", False)),
                body_min_chars=int(s.get("body_min_chars", 1000)),
            )
            for s in entry["sources"]
        )
        agents.append(
            AgentConfig(
                key=entry["key"],
                name=entry["name"],
                emoji=entry.get("emoji", "📰"),
                color=int(entry.get("color", 0x5865F2)),
                charter=entry["charter"],
                scoring=entry["scoring"],
                sources=sources,
                model_id=entry.get("model_id", defaults["model_id"]),
                region=entry.get("region", defaults["region"]),
                backfill_days=int(entry.get("backfill_days", defaults["backfill_days"])),
                max_articles_per_run=int(
                    entry.get("max_articles_per_run", defaults["max_articles_per_run"])
                ),
                min_score=int(entry.get("min_score", defaults["min_score"])),
                reasoning_effort=str(
                    entry.get("reasoning_effort", defaults.get("reasoning_effort", "off"))
                ),
                temperature=float(
                    entry.get("temperature", defaults.get("temperature", 0.3))
                ),
                tiers=str(raw.get("tiers", "")),
                categories=categories,
            )
        )

    if only:
        missing = set(only) - {a.key for a in agents}
        if missing:
            raise SystemExit(f"設定に存在しないエージェント: {', '.join(sorted(missing))}")
    return agents


def _check_categories(categories: tuple[tuple[str, str], ...]) -> None:
    """YAML の種類とモデルの型がずれていたら起動時に止める。"""
    from typing import get_args

    from .models import Category

    expected = set(get_args(Category))
    got = {k for k, _ in categories}
    if got != expected:
        raise SystemExit(
            f"sources.yaml の categories が models.Category と一致しない: "
            f"YAML={sorted(got)} / 型={sorted(expected)}"
        )
