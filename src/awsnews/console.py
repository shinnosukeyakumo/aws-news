"""標準出力への表示。"""

from __future__ import annotations

from .config import AgentConfig
from .models import CuratedArticle


def render_console(config: AgentConfig, items: list[CuratedArticle]) -> str:
    """要約結果を目で確かめるための標準出力表示。"""
    lines = [f"\n{'=' * 72}", f"{config.emoji} {config.name}  ({config.model_id})", "=" * 72]
    if not items:
        lines.append("  新着なし")
        return "\n".join(lines)

    for item in items:
        c = item.curation
        lines += [
            f"\n{c.title_ja}",
            f"  {c.summary}",
            f"  効き目: {c.impact}",
            f"  サービス: {', '.join(c.tags) if c.tags else 'なし'}",
            f"  {item.article.url}",
        ]
    return "\n".join(lines)
