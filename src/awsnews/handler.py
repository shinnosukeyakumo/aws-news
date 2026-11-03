"""Lambda の入口。全エージェントを回し、サイトを作り直して S3 に置く。

EventBridge Scheduler から 1 日 2 回呼ばれる。イベントの中身は使わない。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import publish, site
from .cli import run_agent
from .config import load_agents, load_site
from .store import DynamoStore

logger = logging.getLogger("awsnews")

# コンテナでは /var/task/config/sources.yaml に置いている（Dockerfile）
CONFIG_PATH = Path(os.environ.get(
    "CONFIG_PATH", Path(__file__).resolve().parents[1] / "config" / "sources.yaml"
))


def handler(event, context) -> dict:
    logging.getLogger().setLevel(logging.INFO)   # Lambda の既定は WARNING
    logging.getLogger("httpx").setLevel(logging.WARNING)

    store = DynamoStore(os.environ["TABLE_NAME"])
    site_config = load_site(CONFIG_PATH)
    shown = failed = 0
    for config in load_agents(CONFIG_PATH):
        try:
            shown += len(run_agent(config, store, site_config,
                                   limit=config.max_articles_per_run, record=True))
        except Exception:  # noqa: BLE001 - 1 エージェントの失敗で他を止めない
            failed += 1
            logger.exception("[%s] エージェントの実行に失敗", config.key)

    # 採点が一部失敗しても、溜まっている分からサイトは作り直す
    since = datetime.now(timezone.utc) - timedelta(days=site_config.days)
    articles = store.recent(since)
    publish.put_site(os.environ["BUCKET_NAME"], site.render(articles, site_config), articles)
    logger.info("サイトを更新した。掲載 %d 件（今回）/ 直近 %d 日 %d 件 / 失敗 %d 担当",
                shown, site_config.days, len(articles), failed)
    return {"shown": shown, "articles": len(articles), "failed_agents": failed}
