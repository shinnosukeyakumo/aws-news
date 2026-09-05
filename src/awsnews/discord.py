"""Discord Webhook への配信。"""

from __future__ import annotations

import logging
import time

import httpx

from .config import AgentConfig
from .models import CuratedArticle

logger = logging.getLogger(__name__)

# Discord の仕様上、1 メッセージあたりの embed は 10 個まで
MAX_EMBEDS_PER_MESSAGE = 10
EMBED_DESC_LIMIT = 4096
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _build_embed(item: CuratedArticle, config: AgentConfig) -> dict:
    c = item.curation
    tags = " ".join(f"`{t}`" for t in c.tags[:3])
    description = f"{c.summary}\n\n**▸ 効き目** {c.impact}"
    if tags:
        description += f"\n\n{tags}"
    description += f"\n-# 重要度 {c.score} ・ {item.article.source_label}"

    embed = {
        "title": c.title_ja[:256],
        "url": item.article.url,
        "description": description[:EMBED_DESC_LIMIT],
        "color": config.color,
    }
    if item.article.published_at:
        embed["timestamp"] = item.article.published_at.isoformat()
    return embed


def post(webhook_url: str, config: AgentConfig, items: list[CuratedArticle]) -> None:
    """1 エージェント分の結果を投稿する。スコアの高い順に並べる。"""
    if not items:
        return

    ordered = sorted(items, key=lambda i: i.curation.score, reverse=True)
    header = f"{config.emoji} **{config.name}** — 新着 {len(ordered)} 件"

    with httpx.Client(timeout=TIMEOUT) as client:
        for i in range(0, len(ordered), MAX_EMBEDS_PER_MESSAGE):
            chunk = ordered[i : i + MAX_EMBEDS_PER_MESSAGE]
            payload = {
                "embeds": [_build_embed(item, config) for item in chunk],
                "allowed_mentions": {"parse": []},   # 意図しないメンションを防ぐ
            }
            if i == 0:
                payload["content"] = header   # 見出しは先頭メッセージにだけ付ける
            _post_with_retry(client, webhook_url, payload)
            logger.info("[%s] Discord へ %d 件投稿", config.key, len(chunk))


def _post_with_retry(client: httpx.Client, url: str, payload: dict,
                     max_attempts: int = 4) -> None:
    for attempt in range(1, max_attempts + 1):
        resp = client.post(url, json=payload)
        if resp.status_code == 429:
            wait = float(resp.json().get("retry_after", 1.0))
            logger.warning("Discord のレート制限。%.1f 秒待つ (試行 %d)", wait, attempt)
            time.sleep(wait + 0.5)
            continue
        resp.raise_for_status()
        return
    raise RuntimeError(f"Discord への投稿が {max_attempts} 回とも失敗した")


def render_console(config: AgentConfig, items: list[CuratedArticle],
                   min_score: int) -> str:
    """--dry-run 用。Discord に投げる前に中身を目で確かめるための表示。"""
    lines = [f"\n{'=' * 72}", f"{config.emoji} {config.name}  ({config.model_id})", "=" * 72]
    if not items:
        lines.append("  新着なし")
        return "\n".join(lines)

    for item in sorted(items, key=lambda i: i.curation.score, reverse=True):
        c = item.curation
        mark = "通知" if c.score >= min_score else "見送り"
        lines += [
            f"\n[{mark}] score={c.score}  {c.title_ja}",
            f"  {c.summary}",
            f"  効き目: {c.impact}",
            f"  理由: {c.reason}",
            f"  タグ: {', '.join(c.tags) if c.tags else 'なし'}",
            f"  {item.article.url}",
        ]
    return "\n".join(lines)
