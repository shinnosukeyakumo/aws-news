"""記事とキュレーション結果のデータモデル。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Article(BaseModel):
    """収集した記事 1 件。LLM に渡す前の生データ。"""

    url: str
    title: str
    source_label: str
    published_at: datetime | None = None
    summary_raw: str = ""
    categories: list[str] = Field(default_factory=list)

    def to_prompt_block(self, body_chars: int = 1800) -> str:
        """LLM に渡す 1 記事分のテキスト。

        Nova は長文を先頭・指示を末尾に置いた方が精度が出るため、
        本文は明示的な区切りで囲んで「参照テキスト」であることを示す。
        """
        published = self.published_at.strftime("%Y-%m-%d") if self.published_at else "不明"
        return (
            "DOCUMENT START\n"
            f"媒体: {self.source_label}\n"
            f"公開日: {published}\n"
            f"原題: {self.title}\n"
            f"カテゴリ: {', '.join(self.categories) if self.categories else 'なし'}\n"
            f"本文（冒頭 {body_chars} 文字までの抜粋。末尾で文が切れていても記事の欠落ではない）:\n"
            f"{self.summary_raw[:body_chars]}\n"
            "DOCUMENT END"
        )


class Curation(BaseModel):
    """1 記事に対するキュレーター（エージェント）の判断と要約。

    Strands の structured_output_model にそのまま渡す。
    フィールドの説明文がそのままスキーマとしてモデルに届くため、
    プロンプトの一部として書く。
    """

    title_ja: str = Field(
        max_length=60,
        description="記事の内容を表す日本語の見出し。40 文字以内。原題の直訳ではなく、何の話かが分かる形にする。",
    )
    summary: str = Field(
        max_length=200,
        description=(
            "何が発表・報告されたかを日本語で書く。2 文以内、120 文字以内。"
            "記事に書かれていないことは書かない。"
            "本文が不足していて判断しきれない場合も、その但し書きはここではなく reason に書く。"
        ),
    )
    impact: str = Field(
        max_length=140,
        description=(
            "読者の実装や技術判断に何が効くかを日本語 1 文で書く。80 文字以内。"
            "「試す価値がある」のような一般論ではなく、"
            "何を変える必要があるか・何が作れるようになったかを具体的に書く。"
        ),
    )
    score: int = Field(
        ge=0, le=100,
        description="担当領域の読者にとっての重要度。0〜100。判断基準は system prompt の評価基準に従う。",
    )
    reason: str = Field(
        max_length=120,
        description=(
            "そのスコアを付けた理由。日本語 1 文、60 文字以内。"
            "本文が不足していて判断しきれなかった場合はここに書く。"
        ),
    )
    tags: list[str] = Field(
        default_factory=list,
        description="関連する製品名・技術名のタグ。最大 3 個。例: Bedrock AgentCore, Strands Agents, Nova",
    )


class CuratedArticle(BaseModel):
    """記事とキュレーション結果の組。通知層に渡る最終形。"""

    article: Article
    curation: Curation
    agent_key: str
