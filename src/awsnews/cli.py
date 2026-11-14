"""エントリポイント。収集 → 選別・要約 → 保管 → サイト生成をつなぐ。"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from . import console, site
from .collect import collect, since_datetime
from .config import AgentConfig, SiteConfig, load_agents, load_site
from .curator import Curator
from .models import Article, CuratedArticle
from .store import SeenStore, Store, to_record

logger = logging.getLogger("awsnews")

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "sources.yaml"
DEFAULT_DB = ROOT / "data" / "seen.db"


def _gather(config: AgentConfig, store: Store, limit: int) -> list[Article]:
    """情報源をまたいで記事を集め、未処理のものを新しい順に返す。"""
    collected: dict[str, Article] = {}
    since = since_datetime(config.backfill_days)
    for source in config.sources:
        try:
            for article in collect(source, since=since):
                collected.setdefault(article.url, article)   # URL 重複は先勝ち
        except Exception as exc:  # noqa: BLE001 - 1 つの情報源の失敗で全体を止めない
            logger.error("[%s] 情報源の取得に失敗 %s: %s", config.key, source.label, exc)

    unseen_urls = store.filter_unseen(config.key, list(collected))
    unseen = [a for url, a in collected.items() if url in unseen_urls]
    unseen.sort(key=lambda a: (a.published_at is not None, a.published_at), reverse=True)
    return unseen[:limit]


def run_agent(config: AgentConfig, store: Store, site_config: SiteConfig, *,
              limit: int, record: bool,
              sink: list[CuratedArticle] | None = None) -> list[CuratedArticle]:
    logger.info("=== %s %s ===", config.emoji, config.name)
    articles = _gather(config, store, limit)
    if not articles:
        logger.info("[%s] 新着なし", config.key)
        return []

    logger.info("[%s] %d 件を要約する", config.key, len(articles))
    curator = Curator(config)
    curated = curator.curate(articles)
    for item in curated:
        item.curation.tags = site_config.normalize_tags(item.curation.tags)
    if sink is not None:
        sink.extend(curated)
    print(console.render_console(config, curated))

    if record:
        for item in curated:
            store.mark(config.key, item.article.url, item.article.title, True)
            store.save(item)
        # 要約に失敗した記事も記録し、次回に再挑戦させない（無限リトライ防止）
        curated_urls = {c.article.url for c in curated}
        for article in articles:
            if article.url not in curated_urls:
                store.mark(config.key, article.url, article.title, False)

    usage = curator.usage
    logger.info(
        "[%s] 要約 %d 件 / 失敗 %d 件 / トークン in=%d out=%d (%s)",
        config.key, len(curated), len(articles) - len(curated),
        usage.input_tokens, usage.output_tokens, config.model_id,
    )
    return curated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="awsnews",
        description="AWS のニュースをエージェントが要約し、ニュースサイトを作る",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="エージェント定義 YAML")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="既読管理 DB")
    parser.add_argument("--agent", action="append", dest="agents",
                        help="対象エージェントの key（複数指定可。既定は全部）")
    parser.add_argument("--limit", type=int, default=None,
                        help="1 エージェントあたりの要約件数の上限（既定は設定ファイルの値）")
    parser.add_argument("--no-store", action="store_true",
                        help="既読を記録しない（同じ記事で繰り返し試すとき用）")
    parser.add_argument("--stats", action="store_true", help="既読 DB の統計だけ表示して終わる")
    # 以下は設定ファイルの値を実行時に上書きする。モデル比較のため。
    parser.add_argument("--model", help="model_id を上書きする（例: us.amazon.nova-2-lite-v1:0）")
    parser.add_argument("--reasoning", choices=["off", "low", "medium", "high"],
                        help="思考モードを上書きする")
    parser.add_argument("--temperature", type=float, help="temperature を上書きする")
    parser.add_argument("--days", type=int, dest="backfill_days",
                        help="遡る日数を上書きする（週次まとめなら 7）")
    parser.add_argument("--site", type=Path, metavar="PATH",
                        help="保管した直近の記事からニュースサイトの HTML を書き出す")
    parser.add_argument("--site-only", action="store_true",
                        help="収集と要約をせず、保管済みの記事だけで --site を作り直す")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv(ROOT / ".env")

    store = SeenStore(args.db)
    if args.stats:
        print(f"{'エージェント':<16}{'処理済み':>8}{'要約済み':>8}")
        for key, total, notified in store.stats():
            print(f"{key:<16}{total:>8}{notified or 0:>8}")
        return 0

    site_config = load_site(args.config)
    if args.site_only:
        if not args.site:
            raise SystemExit("--site-only には --site PATH が要る")
        _build_site(args.site, site_config, store, [])
        return 0

    agents = load_agents(args.config, only=args.agents)
    overrides = {
        k: v for k, v in (
            ("model_id", args.model),
            ("reasoning_effort", args.reasoning),
            ("temperature", args.temperature),
            ("backfill_days", args.backfill_days),
        ) if v is not None
    }
    if overrides:
        agents = [dataclasses.replace(a, **overrides) for a in agents]
        logger.info("設定を上書き: %s", overrides)

    total = 0
    collected: list[CuratedArticle] = []
    for config in agents:
        limit = args.limit or config.max_articles_per_run
        total += len(run_agent(config, store, site_config, limit=limit,
                               record=not args.no_store, sink=collected))

    if args.site:
        _build_site(args.site, site_config, store, collected)

    logger.info("完了。要約 %d 件。", total)
    return 0


def _build_site(path: Path, site_config: SiteConfig, store: Store,
                extra: list[CuratedArticle]) -> None:
    """保管済みの直近の記事に今回の分を重ねてサイトを書き出す。

    --no-store で試したときも、今回要約した記事が画面に出るようにするため。
    """
    since = datetime.now(timezone.utc) - timedelta(days=site_config.days)
    merged = {(r["agent_key"], r["url"]): r for r in store.recent(since)}
    for item in extra:
        merged[(item.agent_key, item.article.url)] = to_record(item)
    site.build(list(merged.values()), site_config, path)
    logger.info("%s にサイトを書き出した（%d 件）", path, len(merged))


if __name__ == "__main__":
    sys.exit(main())
