"""Lambda の入口。全エージェントを回し、通知し、サイトを作り直して S3 に置く。

EventBridge Scheduler から 1 日 2 回呼ばれる。イベントの中身は使わない。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import notify, publish, site, verify
from .cli import run_agent
from .config import SiteConfig, load_agents, load_site
from .models import CuratedArticle
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
    fresh: list[CuratedArticle] = []
    failed = 0
    for config in load_agents(CONFIG_PATH):
        try:
            fresh += run_agent(config, store, site_config,
                               limit=config.max_articles_per_run, record=True)
        except Exception:  # noqa: BLE001 - 1 エージェントの失敗で他を止めない
            failed += 1
            logger.exception("[%s] エージェントの実行に失敗", config.key)

    notified = _notify(table_name, site_config, fresh)

    # 要約が一部失敗しても、溜まっている分からサイトは作り直す
    since = datetime.now(timezone.utc) - timedelta(days=site_config.days)
    articles = store.recent(since)
    # 「検証する」で承認した記事には、その後の状態をカードに出す。
    # ページを開いたときにも /api/verify で取り直すので、ここは初期表示のため
    try:
        status_of = {r["url"]: r["status"]
                     for r in verify.list_requests(os.environ["VERIFY_TABLE_NAME"])}
    except Exception:  # noqa: BLE001 - 状態が読めなくてもサイトは出す
        status_of = {}
        logger.exception("検証の状態を読めなかった")
    for a in articles:
        if a["url"] in status_of:
            a["verify"] = status_of[a["url"]]
    html_text = site.render(articles, site_config, api=True)
    publish.put_site(os.environ["BUCKET_NAME"], html_text, articles)
    logger.info("サイトを更新した。新着 %d 件（通知 %d 件）/ 直近 %d 日 %d 件 / 失敗 %d 担当",
                len(fresh), notified, site_config.days, len(articles), failed)
    return {"fresh": len(fresh), "notified": notified,
            "articles": len(articles), "failed_agents": failed}


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
