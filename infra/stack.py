"""aws-news のスタック。

EventBridge Scheduler → Lambda（コンテナ）→ DynamoDB / Bedrock → S3 ← CloudFront（Basic 認証）
"""

from __future__ import annotations

from pathlib import Path

import yaml
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    TimeZone,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_dynamodb as dynamodb,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_scheduler as scheduler,
    aws_scheduler_targets as targets,
)
from aws_cdk import CfnOutput
from constructs import Construct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# 推論プロファイルの接頭辞 → 実際に処理されうるリージョン
PROFILE_REGIONS = {
    "jp": ["ap-northeast-1", "ap-northeast-3"],
    "apac": ["ap-northeast-1", "ap-northeast-2", "ap-northeast-3",
             "ap-south-1", "ap-southeast-1", "ap-southeast-2"],
}


def _model_ids() -> set[str]:
    """sources.yaml に出てくる model_id を全部集める。IAM をそれに絞るため。"""
    raw = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    ids = {raw["defaults"]["model_id"]}
    ids |= {a["model_id"] for a in raw.get("agents", []) if "model_id" in a}
    return ids


class AwsNewsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 既読と採点結果。消すと全記事を採点し直すことになるので、スタックを消しても残す
        table = dynamodb.Table(
            self, "Articles",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True),
            removal_policy=RemovalPolicy.RETAIN,
        )
        table.add_global_secondary_index(
            index_name="by-date",
            partition_key=dynamodb.Attribute(name="feed", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sort_at", type=dynamodb.AttributeType.STRING),
        )

        # サイトの置き場。中身は毎回作り直すので、スタックと一緒に消してよい
        bucket = s3.Bucket(
            self, "Site",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        auth_store = cloudfront.KeyValueStore(self, "AuthStore")
        auth_fn = cloudfront.Function(
            self, "BasicAuth",
            code=cloudfront.FunctionCode.from_file(file_path=str(HERE / "basic_auth.js")),
            runtime=cloudfront.FunctionRuntime.JS_2_0,
            key_value_store=auth_store,
        )
        distribution = cloudfront.Distribution(
            self, "Distribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                function_associations=[cloudfront.FunctionAssociation(
                    function=auth_fn, event_type=cloudfront.FunctionEventType.VIEWER_REQUEST)],
            ),
            price_class=cloudfront.PriceClass.PRICE_CLASS_200,   # 日本を含む
            http_version=cloudfront.HttpVersion.HTTP2_AND_3,
        )

        fn = lambda_.DockerImageFunction(
            self, "Curator",
            code=lambda_.DockerImageCode.from_image_asset(
                str(ROOT),
                platform=ecr_assets.Platform.LINUX_ARM64,
                exclude=[".venv", "data", "infra", "docs", ".git", ".omni", "**/__pycache__"],
            ),
            architecture=lambda_.Architecture.ARM_64,
            memory_size=1024,
            timeout=Duration.minutes(15),
            # 自動で再実行すると Bedrock の呼び出しが二重になる。失敗したら次の定期実行に任せる
            retry_attempts=0,
            environment={"TABLE_NAME": table.table_name, "BUCKET_NAME": bucket.bucket_name},
            log_group=logs.LogGroup(
                self, "CuratorLogs",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )

        # 権限は使うものだけに絞る
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["dynamodb:GetItem", "dynamodb:BatchGetItem", "dynamodb:PutItem", "dynamodb:Query"],
            resources=[table.table_arn, f"{table.table_arn}/index/by-date"],
        ))
        bucket.grant_put(fn)
        model_arns: list[str] = []
        for model_id in sorted(_model_ids()):
            prefix, _, base = model_id.partition(".")
            model_arns.append(f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/{model_id}")
            model_arns += [f"arn:aws:bedrock:{r}::foundation-model/{base}" for r in PROFILE_REGIONS[prefix]]
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=model_arns,
        ))

        scheduler.Schedule(
            self, "TwiceDaily",
            schedule=scheduler.ScheduleExpression.cron(
                minute="0", hour="9,18", time_zone=TimeZone.ASIA_TOKYO),
            target=targets.LambdaInvoke(fn, retry_attempts=0),
            description="aws-news を 9:00 と 18:00（JST）に実行する",
        )

        CfnOutput(self, "SiteUrl", value=f"https://{distribution.distribution_domain_name}/")
        CfnOutput(self, "AuthStoreArn", value=auth_store.key_value_store_arn)
        CfnOutput(self, "FunctionName", value=fn.function_name)
