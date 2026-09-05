"""キュレーターエージェント。記事を 1 件ずつ独立に選別・要約する。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock

from strands import Agent
from strands.models import BedrockModel

from .config import AgentConfig
from .models import Article, CuratedArticle, Curation
from .modelspec import reasoning_fields

logger = logging.getLogger(__name__)

# Bedrock のスロットリングを避けるための同時実行数。
# 記事ごとに独立した推論なので順序依存はない。
MAX_CONCURRENCY = 4

# 長文（記事本文）を先頭に、指示を末尾に置く。Nova はこの並びで精度が上がる。
_TASK_TEMPLATE = """##Article##
{article}

##Task##
上記の記事を Scoring Criteria に照らして採点し、担当領域の読者に向けた日本語の要約を作れ。

##Instructions##
MUST: score は 0〜100 の整数で付けよ。判断は Scoring Criteria のみに従え。
MUST: title_ja は原題の直訳ではなく、何の話かが分かる日本語の見出しにせよ。
MUST: summary には「何が発表・報告されたか」だけを書け。
MUST: impact には「読者の実装や技術判断に何が効くか」を具体的に 1 文で書け。
MUST: 本文が短く内容を判断しきれない場合は、その旨を reason に書き、score を控えめに付けよ。
DO NOT USE INFORMATION THAT IS NOT IN THE DOCUMENT ABOVE!"""


@dataclass
class Usage:
    """1 回の実行で消費したトークン。コスト把握のために集計する。"""

    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    def add(self, accumulated: dict) -> None:
        self.input_tokens += int(accumulated.get("inputTokens", 0))
        self.output_tokens += int(accumulated.get("outputTokens", 0))
        self.calls += 1


class Curator:
    """1 つの担当領域を受け持つエージェント。

    記事ごとに Agent インスタンスを作り直す。会話履歴を共有すると
    前の記事の判断が次の記事のスコアに引きずられるため、意図的に独立させている。
    モデル接続（BedrockModel）だけは使い回す。
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.usage = Usage()
        self._usage_lock = Lock()
        self._model = BedrockModel(
            model_id=config.model_id,
            region_name=config.region,
            temperature=config.temperature,
            additional_request_fields=reasoning_fields(
                config.model_id, config.reasoning_effort
            ),
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

        with self._usage_lock:
            self.usage.add(dict(result.metrics.accumulated_usage))

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
