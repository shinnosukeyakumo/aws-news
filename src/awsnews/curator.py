"""キュレーターエージェント。記事を 1 件ずつ独立に選別・要約する。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from strands import Agent
from strands.models import BedrockModel

from .config import AgentConfig
from .models import Article, CuratedArticle, Curation

logger = logging.getLogger(__name__)

# Bedrock のスロットリングを避けるための同時実行数。
# 記事ごとに独立した推論なので順序依存はない。
MAX_CONCURRENCY = 4

_TASK_TEMPLATE = """以下の記事を評価し、担当領域の読者に向けた要約を作れ。

{article}

評価基準に照らしてスコアを付け、日本語の見出しと要約を書け。
記事の本文抜粋が短く内容を判断しきれない場合は、その旨を reason に書き、
スコアは控えめに付けること。"""


class Curator:
    """1 つの担当領域を受け持つエージェント。

    記事ごとに Agent インスタンスを作り直す。会話履歴を共有すると
    前の記事の判断が次の記事のスコアに引きずられるため、意図的に独立させている。
    モデル接続（BedrockModel）だけは使い回す。
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self._model = BedrockModel(
            model_id=config.model_id,
            region_name=config.region,
        )

    def _curate_one(self, article: Article) -> CuratedArticle | None:
        agent = Agent(
            model=self._model,
            system_prompt=self.config.system_prompt,
            callback_handler=None,   # 標準出力へのストリーム表示を止める
        )
        try:
            result = agent(
                _TASK_TEMPLATE.format(article=article.to_prompt_block()),
                structured_output_model=Curation,
            )
        except Exception as exc:  # noqa: BLE001 - 1 件の失敗で全体を止めない
            logger.error("[%s] 要約に失敗 %s: %s", self.config.key, article.url, exc)
            return None

        curation = result.structured_output
        if curation is None:
            logger.error("[%s] 構造化出力が空 %s", self.config.key, article.url)
            return None

        logger.info(
            "[%s] score=%3d %s", self.config.key, curation.score, curation.title_ja
        )
        return CuratedArticle(
            article=article, curation=curation, agent_key=self.config.key
        )

    def curate(self, articles: list[Article]) -> list[CuratedArticle]:
        """記事群を並列に評価する。失敗した記事は結果から落ちる。"""
        if not articles:
            return []
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            results = list(pool.map(self._curate_one, articles))
        return [r for r in results if r is not None]
