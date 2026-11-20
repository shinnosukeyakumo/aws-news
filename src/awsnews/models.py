"""記事とキュレーション結果のデータモデル。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

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
    """1 記事に対するエージェントの要約。

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
        ),
    )
    impact: str = Field(
        max_length=140,
        description=(
            "開発者にとって何が変わるかを日本語 1 文で書く。80 文字以内。"
            "「試す価値がある」のような一般論ではなく、"
            "何ができるようになったか・何を変える必要があるかを具体的に書く。"
        ),
    )
    tags: list[str] = Field(
        default_factory=list,
        description=(
            "記事の主題になっている AWS のサービス名。正式名で最大 3 個。"
            "例: Amazon EC2, AWS Lambda, Amazon Bedrock AgentCore。通知の要否はこの名前で決まる。"
        ),
    )
    kind: Literal["new_service", "feature", "expansion", "howto", "other"] = Field(
        description=(
            "記事の種類を 1 つ選ぶ。"
            "new_service: これまで無かったサービスや製品の発表。"
            "feature: 既存のサービスに新しい機能が加わった。Bedrock で使えるモデルが増えた場合もここ。"
            "expansion: 機能はそのままで、使える範囲が広がっただけ。"
            "リージョンの追加、インスタンスタイプやサイズの追加、対応する OS やエンジンのバージョンの追加。"
            "howto: 使い方の解説、構築例、導入事例。"
            "other: 料金の改定、名前の変更、提供終了など、上のどれにも当たらないもの。"
        ),
    )
    generative_ai: bool = Field(
        description="生成 AI、LLM、AI エージェントに関わる記事なら true。それ以外は false。",
    )
    category: Literal[
        "ai_ml", "compute", "containers", "storage", "database", "network", "security",
        "management", "developer", "analytics", "integration", "migration", "end_user",
        "business", "cost", "media", "iot", "other",
    ] = Field(
        description=(
            "tags の先頭のサービスが属する AWS の製品カテゴリを 1 つ選ぶ。"
            "ai_ml: Bedrock, AgentCore, SageMaker, Nova, Amazon Q, Kiro, Trainium など。"
            "compute: EC2, Lambda, Batch, Outposts, Local Zones。containers: ECS, EKS, Fargate, ECR。"
            "storage: S3, EBS, EFS, FSx, Backup。database: RDS, Aurora, DynamoDB, ElastiCache, Redshift。"
            "network: VPC, CloudFront, Route 53, Direct Connect, Transit Gateway, ELB, API Gateway。"
            "security: IAM, Cognito, GuardDuty, KMS, Secrets Manager, WAF, Security Hub。"
            "management: CloudWatch, CloudFormation, CloudTrail, Config, Systems Manager, Organizations。"
            "developer: CodeBuild, CodePipeline, CDK, CLI, SDK, Amplify。"
            "analytics: Athena, Glue, EMR, Kinesis, MSK, OpenSearch, QuickSight。"
            "integration: SQS, SNS, EventBridge, Step Functions。migration: DMS, Application Migration Service。"
            "end_user: WorkSpaces, AppStream。business: Amazon Connect, Marketplace, SES。"
            "cost: Cost Explorer, Billing, Budgets。media: Elemental, IVS。iot: IoT Core, Greengrass。"
            "other: どれにも当たらないもの。"
        ),
    )
    importance: int = Field(
        ge=1, le=3,
        description=(
            "AWS で開発するエンジニア全体にとっての注目度を 1〜3 で付ける。"
            "3: 新サービス、主要サービスの大きな機能、多くの構成に効く変更。"
            "2: そのサービスの利用者には役立つ機能の追加。"
            "1: リージョン・インスタンスタイプ・バージョンの追加、小さな改善、事例紹介。"
        ),
    )
    jp_regions: Literal["tokyo_osaka", "tokyo", "osaka", "none", "unknown"] = Field(
        description=(
            "日本のリージョンで使えるかを記事の記述だけから判断する。"
            "tokyo_osaka: 東京（ap-northeast-1）と大阪（ap-northeast-3）の両方、"
            "または「すべての商用リージョン」で使える。"
            "tokyo: 東京は挙がっているが大阪は無い。osaka: 大阪だけ。"
            "none: 使えるリージョンが列挙されていて、日本のリージョンが含まれない。"
            "unknown: リージョンの記述が無い。推測で埋めるな。"
        ),
    )


class CuratedArticle(BaseModel):
    """記事とキュレーション結果の組。通知層に渡る最終形。"""

    article: Article
    curation: Curation
    agent_key: str
