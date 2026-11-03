"""組み立てたサイトを S3 に置く。"""

from __future__ import annotations

import json

import boto3

# 更新は 1 日 2 回なので、キャッシュ削除（invalidation）は使わず短い TTL で済ませる
CACHE_CONTROL = "max-age=60"


def put_site(bucket: str, html_text: str, articles: list[dict]) -> None:
    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=bucket, Key="index.html", Body=html_text.encode("utf-8"),
        ContentType="text/html; charset=utf-8", CacheControl=CACHE_CONTROL,
    )
    s3.put_object(
        Bucket=bucket, Key="articles.json",
        Body=json.dumps(articles, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json; charset=utf-8", CacheControl=CACHE_CONTROL,
    )
