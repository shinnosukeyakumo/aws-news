"""aws-news を AWS に載せる CDK アプリ。構成は docs/design.md を参照。"""

from __future__ import annotations

import os

import aws_cdk as cdk

from stack import AwsNewsStack

app = cdk.App()
AwsNewsStack(
    app, "AwsNews",
    env=cdk.Environment(account=os.environ.get("CDK_DEFAULT_ACCOUNT"), region="ap-northeast-1"),
)
app.synth()
