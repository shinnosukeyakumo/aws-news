"""通知の設定（どのサービスを通知するか）と、Slack への送信。

設定は articles テーブルの 1 項目（pk="#settings", sk="notify"）に置く。
pk がエージェントの key と重ならず、feed 属性も持たないので、
既読の判定にもサイトの一覧（GSI by-date）にも混ざらない。
設定がまだ無いときは sources.yaml の site.notify_default を使う。

Slack の Incoming Webhook の URL は Secrets Manager に置き、コードと CDK には書かない。
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone

from .models import CuratedArticle

logger = logging.getLogger("awsnews")

_KEY = {"pk": "#settings", "sk": "notify"}
# 1 回の通知に載せる記事の上限。re:Invent の時期に Slack が埋まらないようにする
MAX_ITEMS = 20


def _table(name: str):
    import boto3

    return boto3.resource("dynamodb").Table(name)


def load_services(table_name: str, default: tuple[str, ...]) -> list[str]:
    item = _table(table_name).get_item(Key=_KEY).get("Item")
    return list(item["services"]) if item else list(default)


def save_services(table_name: str, services: list[str]) -> list[str]:
    cleaned = sorted({s.strip() for s in services if s.strip()})
    _table(table_name).put_item(Item={
        **_KEY, "services": cleaned, "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    logger.info("通知するサービスを更新した: %s", cleaned)
    return cleaned


def targets(items: list[CuratedArticle], services: list[str]) -> list[CuratedArticle]:
    """通知するサービスのどれかをタグに持つ記事。"""
    wanted = {s.casefold() for s in services}
    return [i for i in items if any(t.casefold() in wanted for t in i.curation.tags)]


def webhook_url(secret_id: str) -> str | None:
    """Secrets Manager から Webhook の URL を読む。まだ入れていなければ None。"""
    import boto3

    value = boto3.client("secretsmanager").get_secret_value(SecretId=secret_id)["SecretString"]
    # CDK が作った直後はランダムな文字列が入っている。URL を入れるまでは送らない
    return value if value.startswith("https://hooks.slack.com/") else None


def message(items: list[CuratedArticle], site_url: str | None) -> dict:
    """Slack に送る本文。1 回の実行で 1 通にまとめる。"""
    shown = items[:MAX_ITEMS]
    lines = [f"*AWS News* 通知対象の新着 {len(items)} 件"]
    for i in shown:
        c = i.curation
        services = " / ".join(c.tags)
        lines.append(f"• <{i.article.url}|{_escape(c.title_ja)}>  _{_escape(services)}_\n"
                     f"   {_escape(c.impact)}")
    if len(items) > len(shown):
        lines.append(f"ほか {len(items) - len(shown)} 件")
    if site_url:
        lines.append(f"<{site_url}|サイトで見る>")
    return {"text": "\n".join(lines), "unfurl_links": False}


def _escape(text: str) -> str:
    # Slack の mrkdwn で特別な意味を持つ 3 文字だけを置き換える
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send(url: str, payload: dict) -> None:
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"content-type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as res:   # noqa: S310 - URL は Secrets Manager の値
        res.read()
