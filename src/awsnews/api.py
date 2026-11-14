"""サイトの /api/* の受け口。CloudFront の裏の Lambda（Function URL）で動く。

| メソッドとパス              | 中身                                               |
|-----------------------------|----------------------------------------------------|
| POST /api/verify            | 記事を承認し、verify-requests に approved で書く   |
| GET  /api/verify            | 承認した記事の一覧と状態（本文は含めない）         |
| GET  /api/verify/{id}       | 1 件の検証記録（note_md）と下書き（draft_md）      |
| GET  /api/settings          | 通知するサービスと種類                             |
| POST /api/settings          | 通知するサービスと種類を置き換える                 |

認証は CloudFront Function（Basic 認証）が済ませている。
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from pathlib import Path

from . import notify, verify
from .config import load_site

logger = logging.getLogger("awsnews")

CONFIG_PATH = Path(os.environ.get(
    "CONFIG_PATH", Path(__file__).resolve().parents[1] / "config" / "sources.yaml"
))
_VERIFY_ONE = re.compile(r"^/api/verify/([0-9a-f]{16})$")


def response(status: int, body: dict | list) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _json_body(event) -> dict:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    body = json.loads(raw)
    if not isinstance(body, dict):
        raise ValueError("JSON のオブジェクトではない")
    return body


def handler(event, context) -> dict:
    logging.getLogger().setLevel(logging.INFO)   # Lambda の既定は WARNING
    http = event.get("requestContext", {}).get("http", {})
    method, path = http.get("method", ""), event.get("rawPath", "")
    table, verify_table = os.environ["TABLE_NAME"], os.environ["VERIFY_TABLE_NAME"]

    if path == "/api/verify" and method == "GET":
        return response(200, verify.list_requests(verify_table))
    if (m := _VERIFY_ONE.match(path)) and method == "GET":
        item = verify.get_request(verify_table, m.group(1))
        return response(200, item) if item else response(404, {"error": "見つからない"})
    if path == "/api/settings" and method == "GET":
        return response(200, notify.load_settings(table, load_site(CONFIG_PATH)))

    if method != "POST":
        return response(405, {"error": "このパスでは受け付けないメソッド"})
    try:
        body = _json_body(event)
    except (ValueError, UnicodeDecodeError):
        return response(400, {"error": "本文を JSON で送ること"})
    if path == "/api/verify":
        return response(*verify.approve(table, verify_table, body))
    if path == "/api/settings":
        services, kinds = body.get("services"), body.get("kinds")
        if not isinstance(services, list) or not all(isinstance(s, str) for s in services):
            return response(400, {"error": "services を文字列の配列で送ること"})
        if not isinstance(kinds, list) or not all(k in notify.KINDS for k in kinds):
            return response(400, {"error": f"kinds は {list(notify.KINDS)} から選ぶこと"})
        return response(200, notify.save_settings(table, services, kinds))
    return response(404, {"error": "そのパスは無い"})
