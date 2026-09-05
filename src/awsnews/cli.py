"""エントリポイント。収集 → 選別・要約 → 配信をつなぐ。"""

from __future__ import annotations

import argparse
import dataclasses
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import discord
from .collect import collect, since_datetime
from .config import AgentConfig, load_agents
from .curator import Curator
from .models import Article, CuratedArticle
from .store import SeenStore

logger = logging.getLogger("awsnews")

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "sources.yaml"
DEFAULT_DB = ROOT / "data" / "seen.db"


def _gather(config: AgentConfig, store: SeenStore, limit: int) -> list[Article]:
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


def run_agent(config: AgentConfig, store: SeenStore, *, dry_run: bool,
              webhook_url: str | None, limit: int, record: bool) -> list[CuratedArticle]:
    logger.info("=== %s %s ===", config.emoji, config.name)
    articles = _gather(config, store, limit)
    if not articles:
        logger.info("[%s] 新着なし", config.key)
        return []

    logger.info("[%s] %d 件を評価する", config.key, len(articles))
    curator = Curator(config)
    curated = curator.curate(articles)
    to_notify = [c for c in curated if c.curation.score >= config.min_score]

    if dry_run:
        print(discord.render_console(config, curated, config.min_score))
    elif to_notify:
        if not webhook_url:
            raise SystemExit("DISCORD_WEBHOOK_URL が未設定。--dry-run で試すか .env に設定せよ。")
        discord.post(webhook_url, config, to_notify)

    if record:
        for item in curated:
            store.mark(config.key, item.article.url, item.article.title,
                       item.curation.score, item.curation.score >= config.min_score)
        # 評価に失敗した記事も記録し、次回に再挑戦させない（無限リトライ防止）
        curated_urls = {c.article.url for c in curated}
        for article in articles:
            if article.url not in curated_urls:
                store.mark(config.key, article.url, article.title, None, False)

    usage = curator.usage
    logger.info(
        "[%s] 評価 %d 件 / 通知 %d 件 / トークン in=%d out=%d (%s)",
        config.key, len(curated), len(to_notify),
        usage.input_tokens, usage.output_tokens, config.model_id,
    )
    return to_notify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="awsnews",
        description="AWS / LLM ベンダーのニュースをエージェントが選別・要約して Discord に配信する",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="エージェント定義 YAML")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="既読管理 DB")
    parser.add_argument("--agent", action="append", dest="agents",
                        help="対象エージェントの key（複数指定可。既定は全部）")
    parser.add_argument("--dry-run", action="store_true",
                        help="Discord に投げず標準出力に表示する")
    parser.add_argument("--limit", type=int, default=None,
                        help="1 エージェントあたりの評価件数の上限（既定は設定ファイルの値）")
    parser.add_argument("--no-store", action="store_true",
                        help="既読を記録しない（同じ記事で繰り返し試すとき用）")
    parser.add_argument("--stats", action="store_true", help="既読 DB の統計だけ表示して終わる")
    # 以下は設定ファイルの値を実行時に上書きする。モデル比較のため。
    parser.add_argument("--model", help="model_id を上書きする（例: us.amazon.nova-2-lite-v1:0）")
    parser.add_argument("--reasoning", choices=["off", "low", "medium", "high"],
                        help="思考モードを上書きする")
    parser.add_argument("--temperature", type=float, help="temperature を上書きする")
    parser.add_argument("--min-score", type=int, dest="min_score",
                        help="通知の閾値を上書きする")
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
        print(f"{'エージェント':<16}{'処理済み':>8}{'通知済み':>8}")
        for key, total, notified in store.stats():
            print(f"{key:<16}{total:>8}{notified or 0:>8}")
        return 0

    agents = load_agents(args.config, only=args.agents)
    overrides = {
        k: v for k, v in (
            ("model_id", args.model),
            ("reasoning_effort", args.reasoning),
            ("temperature", args.temperature),
            ("min_score", args.min_score),
        ) if v is not None
    }
    if overrides:
        agents = [dataclasses.replace(a, **overrides) for a in agents]
        logger.info("設定を上書き: %s", overrides)
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not args.dry_run and not webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL が未設定。--dry-run 相当で動かす。")
        args.dry_run = True

    total = 0
    for config in agents:
        limit = args.limit or config.max_articles_per_run
        total += len(run_agent(config, store, dry_run=args.dry_run,
                               webhook_url=webhook_url, limit=limit,
                               record=not args.no_store))

    logger.info("完了。通知 %d 件。", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
