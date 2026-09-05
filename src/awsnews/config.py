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

    @property
    def system_prompt(self) -> str:
        """このエージェントの人格と判断基準。選別と要約の両方に効く。

        Amazon Nova は Claude 流の自然な依頼文だと精度が落ちるため、
        セクション見出しと DO / DO NOT の命令形で構造化している。
        この形は Claude に投げても精度を落とさないので、モデル別に分けていない。
        """
        return (
            f"# Core Mandates\n{self.charter.strip()}\n\n"
            f"# Scoring Criteria\n{self.scoring.strip()}\n\n"
            "# Output Formatting\n"
            "MUST: 日本語で書く。常体（である調）で簡潔に書く。\n"
            "MUST: 字数の上限を守る。title_ja は 40 文字、summary は 120 文字、"
            "impact は 80 文字を超えてはならない。超えそうなら要素を削る。\n"
            "MUST: 製品名・サービス名は原語表記のまま使う（例: Amazon Bedrock AgentCore）。\n"
            "DO NOT: 記事に書かれていない事実を補うな。推測を書くな。\n"
            "DO NOT: 「〜な世界が広がります」「〜は必見です」のような煽り文句を使うな。\n"
            "DO NOT: 同じ文や似た文を繰り返すな。\n"
        )


def load_agents(path: Path, only: list[str] | None = None) -> list[AgentConfig]:
    """YAML を読んで AgentConfig の一覧を返す。

    Args:
        path: sources.yaml のパス
        only: 指定があればその key のエージェントだけに絞る
    """
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {})

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
            )
        )

    if only:
        missing = set(only) - {a.key for a in agents}
        if missing:
            raise SystemExit(f"設定に存在しないエージェント: {', '.join(sorted(missing))}")
    return agents
