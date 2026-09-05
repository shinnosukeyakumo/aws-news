"""情報源から記事を集める層。LLM は一切使わない決定的な処理。"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

import feedparser
import httpx

from .config import SourceConfig
from .models import Article

logger = logging.getLogger(__name__)

USER_AGENT = "aws-news-curator/0.1 (+https://github.com/shinnosukeyakumo)"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# 本文抽出用。script/style を先に落とさないと CSS が段落として混入する。
_NOISE_RE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.S | re.I)
_MAIN_RE = re.compile(r"<(article|main)\b[^>]*>(.*?)</\1>", re.S | re.I)
_P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S | re.I)
# 段落として採用する最小文字数。これ未満はナビゲーションやキャプションとみなす。
_MIN_PARAGRAPH_CHARS = 60


def _strip_html(text: str) -> str:
    """HTML タグを落として空白を整える。要約は LLM に渡すのでこの程度で足りる。"""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", text or ""))).strip()


def extract_body(html_text: str) -> str:
    """記事ページの HTML から本文らしい段落を抜き出す。

    RSS の description が数百文字しかない媒体（OpenAI / Google / Anthropic）向け。
    完璧な本文抽出は狙わない。LLM に渡すのに足る密度があればよいので、
    専用ライブラリ（trafilatura 等）は入れず正規表現で済ませている。
    """
    cleaned = _NOISE_RE.sub(" ", html_text)
    scope_match = _MAIN_RE.search(cleaned)
    scope = scope_match.group(2) if scope_match else cleaned

    seen: set[str] = set()
    paragraphs: list[str] = []
    for raw in _P_RE.findall(scope):
        text = _strip_html(raw)
        if len(text) < _MIN_PARAGRAPH_CHARS or text in seen:
            continue
        seen.add(text)
        paragraphs.append(text)
    return " ".join(paragraphs)


def _to_utc(struct_time) -> datetime | None:
    if not struct_time:
        return None
    try:
        return datetime(*struct_time[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def collect(source: SourceConfig, *, since: datetime) -> list[Article]:
    """情報源 1 つから since 以降の記事を集める。"""
    if source.type == "rss":
        articles = _collect_rss(source)
    elif source.type == "sitemap":
        articles = _collect_sitemap(source)
    else:
        raise ValueError(f"未知の情報源タイプ: {source.type}")

    fresh = [a for a in articles if a.published_at is None or a.published_at >= since]
    if source.fetch_body:
        _enrich_bodies(source, fresh)
    logger.info(
        "収集 %-18s 取得=%d 期間内=%d", source.label, len(articles), len(fresh)
    )
    return fresh


def _enrich_bodies(source: SourceConfig, articles: list[Article]) -> None:
    """本文が薄い記事だけ、記事ページを取りに行って summary_raw を差し替える。"""
    targets = [a for a in articles if len(a.summary_raw) < source.body_min_chars]
    if not targets:
        return
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": USER_AGENT}) as client:
        for article in targets:
            try:
                resp = client.get(article.url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("本文の取得に失敗 %s: %s", article.url, exc)
                continue
            body = extract_body(resp.text)
            if len(body) > len(article.summary_raw):
                article.summary_raw = body
    logger.debug("本文を補完 %s: %d 件", source.label, len(targets))


def _collect_rss(source: SourceConfig) -> list[Article]:
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": USER_AGENT}) as client:
        resp = client.get(source.url)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)

    articles: list[Article] = []
    for entry in feed.entries:
        categories = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]
        # What's New のように 1 つの category に複数値がカンマで詰まっている場合がある
        flat = [c.strip() for raw in categories for c in raw.split(",") if c.strip()]

        if source.include_categories and not any(
            want in cat for cat in flat for want in source.include_categories
        ):
            continue

        body = entry.get("content", [{}])[0].get("value", "") or entry.get("summary", "")
        articles.append(
            Article(
                url=entry.link,
                title=_strip_html(entry.get("title", "")),
                source_label=source.label,
                published_at=_to_utc(entry.get("published_parsed") or entry.get("updated_parsed")),
                summary_raw=_strip_html(body),
                categories=flat,
            )
        )
    return articles


def _collect_sitemap(source: SourceConfig) -> list[Article]:
    """RSS を出していないサイト向け。sitemap の lastmod で新着を拾い、
    記事ページの og: メタからタイトルと概要を取る。"""
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": USER_AGENT}) as client:
        resp = client.get(source.url)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        candidates: list[tuple[datetime | None, str]] = []
        for url_el in root.findall("s:url", ns):
            loc_el = url_el.find("s:loc", ns)
            if loc_el is None or not loc_el.text:
                continue
            loc = loc_el.text
            if source.path_prefixes and not any(p in loc for p in source.path_prefixes):
                continue
            lastmod_el = url_el.find("s:lastmod", ns)
            published = None
            if lastmod_el is not None and lastmod_el.text:
                try:
                    published = datetime.fromisoformat(
                        lastmod_el.text.replace("Z", "+00:00")
                    ).astimezone(timezone.utc)
                except ValueError:
                    pass
            candidates.append((published, loc))

        # 新しい順。ページ取得は 1 件ずつ HTTP が飛ぶので上限を切る。
        candidates.sort(key=lambda x: (x[0] or datetime.min.replace(tzinfo=timezone.utc)),
                        reverse=True)
        articles: list[Article] = []
        for lastmod, loc in candidates[:30]:
            meta = _fetch_page_meta(client, loc)
            if meta is None:
                continue
            title, description, page_date = meta
            articles.append(
                Article(
                    url=loc,
                    title=title,
                    source_label=source.label,
                    # ページ内の公開日を優先し、無ければ sitemap の lastmod で代用する
                    published_at=page_date or lastmod,
                    summary_raw=description,
                )
            )
    return articles


_OG_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:(title|description)["\'][^>]+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)

# sitemap の lastmod は「更新日」であって公開日ではない。
# 記事ページの本文に埋め込まれた "Jul 30, 2026" 形式の日付を公開日として優先する。
_PAGE_DATE_RE = re.compile(
    r">\s*((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+20\d{2})\s*<"
)


def _parse_page_date(html_text: str) -> datetime | None:
    match = _PAGE_DATE_RE.search(html_text)
    if not match:
        return None
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(match.group(1), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None



def _fetch_page_meta(
    client: httpx.Client, url: str
) -> tuple[str, str, datetime | None] | None:
    """記事ページからタイトル・本文・公開日を取る。"""
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("ページ取得に失敗 %s: %s", url, exc)
        return None

    found = {k.lower(): _strip_html(v) for k, v in _OG_RE.findall(resp.text)}
    title = found.get("title") or url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
    # og:description は 1〜2 文しかないため、本文が取れるならそちらを優先する
    body = extract_body(resp.text)
    description = found.get("description", "")
    return title, (body if len(body) > len(description) else description), _parse_page_date(resp.text)


def since_datetime(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)
