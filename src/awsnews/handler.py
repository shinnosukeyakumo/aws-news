"""Lambda の入口。全エージェントを回し、通知し、サイトを作り直して S3 に置く。

EventBridge Scheduler から 1 日 2 回呼ばれる。イベントの中身は使わない。
手で {"recurate_days": N, "limit": M} を渡すと、直近 N 日の記事のうち
注目度（importance）を持たない古い記事を最大 M 件だけ要約し直す（項目を足したときの埋め戻し用）。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from . import notify, publish, site
from .cli import run_agent
from .collect import TIMEOUT, USER_AGENT, extract_body
from .config import SiteConfig, load_agents, load_site
from .curator import Curator
from .models import Article, CuratedArticle
from .store import DynamoStore

logger = logging.getLogger("awsnews")

# コンテナでは /var/task/config/sources.yaml に置いている（Dockerfile）
CONFIG_PATH = Path(os.environ.get(
    "CONFIG_PATH", Path(__file__).resolve().parents[1] / "config" / "sources.yaml"
))


def handler(event, context) -> dict:
    logging.getLogger().setLevel(logging.INFO)   # Lambda の既定は WARNING
    logging.getLogger("httpx").setLevel(logging.WARNING)

    table_name = os.environ["TABLE_NAME"]
    store = DynamoStore(table_name)
    site_config = load_site(CONFIG_PATH)
    agents = load_agents(CONFIG_PATH)

    if isinstance(event, dict) and "recurate_days" in event:
        result = _recurate(store, site_config, agents,
                           days=int(event["recurate_days"]), limit=int(event.get("limit", 120)))
        result["articles"] = _publish(store, site_config, agents)
        return result

    fresh: list[CuratedArticle] = []
    failed = 0
    for config in agents:
        try:
            fresh += run_agent(config, store, site_config,
                               limit=config.max_articles_per_run, record=True)
        except Exception:  # noqa: BLE001 - 1 エージェントの失敗で他を止めない
            failed += 1
            logger.exception("[%s] エージェントの実行に失敗", config.key)

    notified = _notify(table_name, site_config, fresh)
    # 要約が一部失敗しても、溜まっている分からサイトは作り直す
    count = _publish(store, site_config, agents)
    logger.info("サイトを更新した。新着 %d 件（通知 %d 件）/ 直近 %d 日 %d 件 / 失敗 %d 担当",
                len(fresh), notified, site_config.days, count, failed)
    return {"fresh": len(fresh), "notified": notified, "articles": count, "failed_agents": failed}


def _publish(store, site_config: SiteConfig, agents) -> int:
    """直近の記事でサイトを作り直す。今の担当に無いエージェント（LLM ベンダーなど）の記事は載せない。"""
    since = datetime.now(timezone.utc) - timedelta(days=site_config.days)
    keys = {a.key for a in agents}
    articles = site.prepare([a for a in store.recent(since) if a.get("agent_key") in keys], site_config)
    html_text = site.render(articles, site_config, api=True)
    publish.put_site(os.environ["BUCKET_NAME"], html_text, articles)
    return len(articles)


def _recurate(store, site_config: SiteConfig, agents, *, days: int, limit: int) -> dict:
    """importance を持たない記事を、記事ページを取り直して要約し直す。"""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    by_key = {a.key: a for a in agents}
    old = [r for r in store.recent(since)
           if r.get("agent_key") in by_key and r.get("importance") is None][:limit]
    logger.info("要約し直す記事 %d 件", len(old))

    grouped: dict[str, list[Article]] = {}
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": USER_AGENT}) as client:
        for r in old:
            body = ""
            try:
                resp = client.get(r["url"])
                resp.raise_for_status()
                body = extract_body(resp.text)
            except httpx.HTTPError as exc:
                logger.warning("本文の取得に失敗 %s: %s", r["url"], exc)
            published = r.get("published_at")
            grouped.setdefault(r["agent_key"], []).append(Article(
                url=r["url"], title=r["title_original"], source_label=r["source_label"],
                published_at=datetime.fromisoformat(published) if published else None,
                summary_raw=body or r.get("summary") or "",
            ))

    done = 0
    for key, articles in grouped.items():
        for item in Curator(by_key[key]).curate(articles):
            item.curation.tags = site_config.normalize_tags(item.curation.tags)
            store.save(item)
            done += 1
    logger.info("要約し直した %d / %d 件", done, len(old))
    return {"recurated": done, "targets": len(old)}


def _notify(table_name: str, site_config: SiteConfig, fresh: list[CuratedArticle]) -> int:
    """通知の設定に当たる新着を Slack に 1 通で送る。失敗してもサイトの更新は続ける。"""
    try:
        hits = notify.targets(fresh, notify.load_settings(table_name, site_config))
        if not hits:
            return 0
        url = notify.webhook_url(os.environ["SLACK_SECRET_ID"])
        if not url:
            logger.warning("Slack の Webhook URL が未設定のため、通知 %d 件を送らなかった", len(hits))
            return 0
        notify.send(url, notify.message(hits, os.environ.get("SITE_URL")))
        return len(hits)
    except Exception:  # noqa: BLE001
        logger.exception("Slack への通知に失敗")
        return 0
