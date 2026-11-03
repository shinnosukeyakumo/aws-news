"""標準出力への表示。"""

from __future__ import annotations

from .config import AgentConfig
from .models import CuratedArticle


def render_console(config: AgentConfig, items: list[CuratedArticle],
                   min_score: int) -> str:
    """採点結果を目で確かめるための標準出力表示。"""
    lines = [f"\n{'=' * 72}", f"{config.emoji} {config.name}  ({config.model_id})", "=" * 72]
    if not items:
        lines.append("  新着なし")
        return "\n".join(lines)

    for item in sorted(items, key=lambda i: i.curation.score, reverse=True):
        c = item.curation
        mark = "掲載" if c.score >= min_score else "見送り"
        lines += [
            f"\n[{mark}] score={c.score} [{c.category}]  {c.title_ja}",
            f"  {c.summary}",
            f"  効き目: {c.impact}",
            f"  理由: {c.reason}",
            f"  タグ: {', '.join(c.tags) if c.tags else 'なし'}",
            f"  {item.article.url}",
        ]
    return "\n".join(lines)
