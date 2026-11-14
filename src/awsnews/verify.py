"""承認の記録（verify-requests テーブル）の読み書き。

カードの「検証する」は POST /api/verify に記事のキー（pk=エージェント、sk=URL）を送る。
api.py がそれを受け、articles から記事を写して status=approved で書く。
その先（picked → done / needs-real / failed）と、検証の結果・記録・下書きは
agentcore-playground 側が書く。受け渡しの形は docs/design.md の「検証の依頼」を参照。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("awsnews")

# articles の body から verify-requests に写す属性
_COPIED = ("url", "title_ja", "title_original", "source_label", "tags", "summary")
# 一覧で返す属性。記録（note_md）と下書き（draft_md）は重いので 1 件ずつ取らせる。
# 下書きがあるかどうかは、playground が draft_md と一緒に書く has_draft で分かる
_LISTED = ("id", "url", "title_ja", "source_label", "tags", "status", "result",
           "message", "has_draft", "approved_at", "picked_at", "done_at")


def request_id(url: str) -> str:
    """同じ記事を二重に承認しないためのキー。URL の SHA-256 の先頭 16 桁。"""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _table(name: str):
    import boto3

    return boto3.resource("dynamodb").Table(name)


def list_requests(table_name: str) -> list[dict]:
    """承認した記事の一覧（新しい順）。件数は手で押した数なので Scan で足りる。"""
    table = _table(table_name)
    names = {f"#{i}": k for i, k in enumerate(_LISTED)}
    kwargs = {"ProjectionExpression": ", ".join(names),
              "ExpressionAttributeNames": names}
    out: list[dict] = []
    while True:
        resp = table.scan(**kwargs)
        out += resp["Items"]
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return sorted(out, key=lambda i: i.get("approved_at", ""), reverse=True)


def get_request(table_name: str, rid: str) -> dict | None:
    return _table(table_name).get_item(Key={"id": rid}).get("Item")


def approve(table_name: str, verify_table_name: str, req: dict) -> tuple[int, dict]:
    """記事を承認する。返り値は (HTTP ステータス, 本文)。"""
    from botocore.exceptions import ClientError

    try:
        pk, sk = str(req["pk"]), str(req["sk"])
    except KeyError:
        return 400, {"error": "pk と sk を送ること"}
    item = _table(table_name).get_item(Key={"pk": pk, "sk": sk}).get("Item")
    if not item or item.get("status") != "curated":
        return 404, {"error": "要約済みの記事が見つからない"}
    record = json.loads(item["body"])

    rid = request_id(record["url"])
    try:
        _table(verify_table_name).put_item(
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
        return 409, {"id": rid, "status": old}
    logger.info("検証を承認した: %s %s", rid, record["url"])
    return 200, {"id": rid, "status": "approved"}
