"""通知の設定（どのサービスのどの種類の記事を通知するか）と、Slack への送信。

通知するのは次のどちらかに当たる記事:
- 生成 AI の新サービス。名前がまだ誰にも分からないので、サービス名も種類も問わない
- 選んだサービスをタグに持ち、かつ選んだ種類（Curation.kind）の記事

設定は articles テーブルの 1 項目（pk="#settings", sk="notify"）に置く。
pk がエージェントの key と重ならず、feed 属性も持たないので、
既読の判定にもサイトの一覧（GSI by-date）にも混ざらない。
設定がまだ無いときは sources.yaml の site.notify_default / notify_kinds_default を使う。

Slack の Incoming Webhook の URL は Secrets Manager に置き、コードと CDK には書かない。
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone

from .config import SiteConfig
from .models import Curation, CuratedArticle

logger = logging.getLogger("awsnews")

_KEY = {"pk": "#settings", "sk": "notify"}
# 1 回の通知に載せる記事の上限。re:Invent の時期に Slack が埋まらないようにする
MAX_ITEMS = 20
# 記事の種類。キーは Curation.kind の値。サイトの通知設定にもこの順で並ぶ
KINDS = {
    "new_service": "新サービス",
    "feature": "新機能",
    "expansion": "対応の拡大（リージョン・インスタンスなど）",
    "howto": "解説・事例",
    "other": "料金・その他",
}


def _table(name: str):
    import boto3

    return boto3.resource("dynamodb").Table(name)


def load_settings(table_name: str, site: SiteConfig) -> dict:
    item = _table(table_name).get_item(Key=_KEY).get("Item") or {}
    # 種類を選べるようになる前に保存した設定には kinds が無い
    return {"services": list(item.get("services", site.notify_default)),
            "kinds": list(item.get("kinds", site.notify_kinds_default))}


def save_settings(table_name: str, services: list[str], kinds: list[str]) -> dict:
    saved = {"services": sorted({s.strip() for s in services if s.strip()}),
             "kinds": [k for k in KINDS if k in kinds]}
    _table(table_name).put_item(Item={
        **_KEY, **saved, "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    logger.info("通知の設定を更新した: %s", saved)
    return saved


def wanted(c: Curation, settings: dict) -> bool:
    if c.kind == "new_service" and c.generative_ai:
        return True
    services = {s.casefold() for s in settings["services"]}
    return c.kind in settings["kinds"] and any(t.casefold() in services for t in c.tags)


def targets(items: list[CuratedArticle], settings: dict) -> list[CuratedArticle]:
    return [i for i in items if wanted(i.curation, settings)]


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
        label = " / ".join([KINDS[c.kind].split("（")[0], *c.tags])
        lines.append(f"• <{i.article.url}|{_escape(c.title_ja)}>  _{_escape(label)}_\n"
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
