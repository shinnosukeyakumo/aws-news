"""記事のカテゴリ。AWS の製品カテゴリにならって 18 個に分ける。

要約のときにエージェントが 1 つ選ぶ（Curation.category）。
カテゴリを選ばせる前に要約した記事は、タグのサービス名から guess() で当てる。
"""

from __future__ import annotations

import re

# キー → (表示名, 色, アイコンの略号)。サイトのタブはこの順に並ぶ（件数の多い順に並べ替えるのはサイト側）
CATEGORIES: dict[str, tuple[str, str, str]] = {
    "ai_ml": ("AI/ML", "#0E8A7D", "AI"),
    "compute": ("Compute", "#E07A16", "CPU"),
    "containers": ("Containers", "#D9622B", "CTR"),
    "storage": ("Storage", "#5E9E2E", "STO"),
    "database": ("Database", "#B23ED4", "DB"),
    "network": ("Network", "#7A4FE0", "NET"),
    "security": ("Security & Identity", "#D6334C", "SEC"),
    "management": ("Management", "#C93B7C", "OPS"),
    "developer": ("Developer", "#3B6FD4", "DEV"),
    "analytics": ("Analytics", "#6A5AE0", "ANL"),
    "integration": ("Integration", "#C2387A", "INT"),
    "migration": ("Migration", "#2E9E8F", "MIG"),
    "end_user": ("End User", "#C7522A", "EUC"),
    "business": ("Business", "#B8407A", "BIZ"),
    "cost": ("Cloud Finance", "#3C8C4E", "$"),
    "media": ("Media", "#D2691E", "MED"),
    "iot": ("IoT", "#2F8F5B", "IoT"),
    "other": ("その他", "#7C7C84", "ETC"),
}

# タグ（サービス名）からカテゴリを当てるための手がかり。上から順に見て、最初に当たったものを使う
_RULES: list[tuple[str, str]] = [
    ("ai_ml", r"Bedrock|SageMaker|Nova|Strands|Q Developer|Amazon Q\b|Kiro|Transform|Comprehend|Rekognition|"
              r"Textract|Polly|Transcribe|Translate|Lex|Kendra|Personalize|Trainium|Inferentia|DevOps Agent|"
              r"Agent|HealthOmics|Braket|Quick(?!Sight)"),
    ("containers", r"ECS|EKS|Elastic Container|Kubernetes|Fargate|ECR|App Runner"),
    ("compute", r"EC2|Elastic Compute|Lambda|Batch|Outposts|Local Zone|Wavelength|Lightsail|Elastic Beanstalk|"
                r"Graviton|ParallelCluster|EVS|Corretto"),
    ("storage", r"S3|EBS|Elastic Block|EFS|FSx|Backup|Storage Gateway|Glacier|DataSync"),
    ("database", r"RDS|Aurora|DynamoDB|ElastiCache|MemoryDB|Neptune|DocumentDB|Keyspaces|Timestream|DSQL|Redshift"),
    ("network", r"VPC|CloudFront|Route 53|Direct Connect|Transit Gateway|Cloud WAN|Load Balanc|PrivateLink|"
                r"Global Accelerator|VPN|Interconnect|API Gateway|Network Firewall"),
    ("security", r"IAM|Identity|Cognito|GuardDuty|Inspector|Security|KMS|Key Management|Secrets Manager|WAF|"
                 r"Shield|Macie|Certificate|Detective|Directory|Verified|STS|Cedar"),
    ("management", r"CloudWatch|CloudFormation|CloudTrail|Config|Systems Manager|Organizations|Control Tower|"
                   r"Health|Well-Architected|AppConfig|License Manager|Resource Access|Service Catalog|Trusted"),
    ("developer", r"CodeBuild|CodePipeline|CodeCommit|CodeDeploy|CodeCatalyst|Cloud9|CDK|Command Line|SDK|"
                  r"Amplify|X-Ray|Emulator|Toolkit"),
    ("analytics", r"Athena|Glue|EMR|Kinesis|MSK|OpenSearch|QuickSight|Lake Formation|DataZone|Clean Rooms|"
                  r"Data Exchange|Flink|MWAA"),
    ("integration", r"SQS|SNS|EventBridge|Step Functions|MQ|AppFlow|AppSync"),
    ("migration", r"Migration|DMS|Database Migration|Snow|Mainframe"),
    ("end_user", r"WorkSpaces|AppStream|WorkSpaces Applications|Chime|WorkMail"),
    ("business", r"Connect|Marketplace|Partner|Supply Chain|Pinpoint|SES|End User Messaging|Revenue"),
    ("cost", r"Cost|Billing|Budgets|Savings Plans|Pricing"),
    ("media", r"Elemental|IVS|MediaTailor|MediaConnect|Deadline|Kinesis Video"),
    ("iot", r"IoT|Greengrass|RoboMaker"),
]
# タグは正式名に揃えてあるので大文字小文字を区別する（SES が Services に当たらないように）
_COMPILED = [(k, re.compile(p)) for k, p in _RULES]


def guess(tags: list[str], generative_ai: bool = False) -> str:
    """タグからカテゴリを当てる。当たらなければ、生成 AI の記事は ai_ml、それ以外は other。"""
    for tag in tags:
        for key, pattern in _COMPILED:
            if pattern.search(tag):
                return key
    return "ai_ml" if generative_ai else "other"
