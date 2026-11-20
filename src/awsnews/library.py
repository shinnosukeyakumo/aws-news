"""マイライブラリ（お気に入りのカテゴリ・保存した記事・保存した条件）の保管。

ブラウザの localStorage にも同じものを持ち、端末をまたいで揃えるために
articles テーブルの 1 項目（pk="#settings", sk="library"）へ丸ごと置く。
使うのは自分 1 人なので、項目単位の結合はせず updated_at が新しい方で上書きする。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("awsnews")

_KEY = {"pk": "#settings", "sk": "library"}
# 1 項目 400KB の上限に余裕を持たせる。保存した記事は要約ごと持つので件数で抑える
MAX_SAVED = 500
MAX_FAVORITES = 50
MAX_PRESETS = 30
_SNAPSHOT_FIELDS = ("url", "title_ja", "published_at", "importance", "category",
                    "agent_key", "summary")


def _table(name: str):
    import boto3

    return boto3.resource("dynamodb").Table(name)


def empty() -> dict:
    return {"favorites": [], "saved": [], "presets": [], "updated_at": None}


def load(table_name: str) -> dict:
    item = _table(table_name).get_item(Key=_KEY).get("Item")
    if not item:
        return empty()
    return {**json.loads(item["body"]), "updated_at": item.get("updated_at")}


def validate(body: dict) -> dict:
    """ブラウザから来た中身を、保管してよい形に整える。形が違えば ValueError。"""
    favorites, saved, presets = body.get("favorites"), body.get("saved"), body.get("presets")
    if not isinstance(favorites, list) or not all(isinstance(f, str) for f in favorites):
        raise ValueError("favorites を文字列の配列で送ること")
    if not isinstance(saved, list) or not all(isinstance(s, dict) and isinstance(s.get("url"), str)
                                              for s in saved):
        raise ValueError("saved を url を持つオブジェクトの配列で送ること")
    if not isinstance(presets, list) or not all(isinstance(p, dict) and isinstance(p.get("name"), str)
                                                for p in presets):
        raise ValueError("presets を name を持つオブジェクトの配列で送ること")
    return {
        "favorites": list(dict.fromkeys(favorites))[:MAX_FAVORITES],
        "saved": [{k: s.get(k) for k in (*_SNAPSHOT_FIELDS, "saved_at")} for s in saved][:MAX_SAVED],
        "presets": [{"name": p["name"][:40], "filters": p.get("filters") or {}}
                    for p in presets][:MAX_PRESETS],
    }


def save(table_name: str, body: dict) -> dict:
    data = validate(body)
    updated_at = datetime.now(timezone.utc).isoformat()
    _table(table_name).put_item(Item={
        **_KEY, "body": json.dumps(data, ensure_ascii=False), "updated_at": updated_at,
    })
    logger.info("ライブラリを保存した: お気に入り %d / 記事 %d / 条件 %d",
                len(data["favorites"]), len(data["saved"]), len(data["presets"]))
    return {**data, "updated_at": updated_at}
