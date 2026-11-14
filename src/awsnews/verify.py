"""「検証する」ボタンの受け口と、承認の記録（verify-requests テーブル）の読み書き。

ボタンは POST /api/verify に記事のキー（pk=エージェント、sk=URL）を送る。
CloudFront の裏の Lambda（Function URL）がそれを受け、articles から記事を写して
status=approved で書く。その先（picked → done / needs-real / failed）は
agentcore-playground 側が書く。受け渡しの形は docs/design.md の「検証の依頼」を参照。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("awsnews")

# articles の body から verify-requests に写す属性
_COPIED = ("url", "title_ja", "title_original", "source_label", "tags", "summary")


def request_id(url: str) -> str:
    """同じ記事を二重に承認しないためのキー。URL の SHA-256 の先頭 16 桁。"""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def statuses(table_name: str) -> dict[str, str]:
    """URL → 状態。サイトの再生成時に読む。件数は手で押した数なので Scan で足りる。"""
    import boto3

    table = boto3.resource("dynamodb").Table(table_name)
    out: dict[str, str] = {}
    kwargs = {"ProjectionExpression": "#u, #s", "ExpressionAttributeNames": {"#u": "url", "#s": "status"}}
    while True:
        resp = table.scan(**kwargs)
        out |= {i["url"]: i["status"] for i in resp["Items"] if "url" in i}
        if "LastEvaluatedKey" not in resp:
            return out
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def _response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def handler(event, context) -> dict:
    """Function URL の入口。認証は CloudFront Function（Basic 認証）が済ませている。"""
    import boto3
    from botocore.exceptions import ClientError

    logging.getLogger().setLevel(logging.INFO)   # Lambda の既定は WARNING
    if event.get("requestContext", {}).get("http", {}).get("method") != "POST":
        return _response(405, {"error": "POST だけを受け付ける"})
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        req = json.loads(raw)
        pk, sk = str(req["pk"]), str(req["sk"])
    except (ValueError, KeyError, TypeError):
        return _response(400, {"error": "pk と sk を JSON で送ること"})

    db = boto3.resource("dynamodb")
    item = db.Table(os.environ["TABLE_NAME"]).get_item(Key={"pk": pk, "sk": sk}).get("Item")
    if not item or item.get("status") != "curated":
        return _response(404, {"error": "採点済みの記事が見つからない"})
    record = json.loads(item["body"])

    rid = request_id(record["url"])
    try:
        db.Table(os.environ["VERIFY_TABLE_NAME"]).put_item(
            Item={
                "id": rid,
                **{k: record[k] for k in _COPIED if record.get(k) is not None},
                "status": "approved",
                "approved_at": datetime.now(timezone.utc).isoformat(),
            },
            ConditionExpression="attribute_not_exists(id)",
            ReturnValuesOnConditionCheckFailure="ALL_OLD",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        old = e.response.get("Item", {}).get("status", {}).get("S", "approved")
        return _response(409, {"id": rid, "status": old})
    logger.info("検証を承認した: %s %s", rid, record["url"])
    return _response(200, {"id": rid, "status": "approved"})
