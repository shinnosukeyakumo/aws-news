"""保管した記事からニュースサイトの HTML を組み立てる。

1 ファイルで完結する静的ページにする。記事データはページに埋め込み、
期間・カテゴリ・絞り込み・詳細表示はブラウザ側の JavaScript で行う。
S3 に置くだけで配信できる。通知設定とマイライブラリだけは /api/* と同期する。
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from . import categories
from .config import SiteConfig
from .notify import KINDS


def prepare(articles: list[dict], site: SiteConfig) -> list[dict]:
    """サイトに載せる形に整える。タグの表記を揃え、カテゴリが無い（または旧い値の）記事はタグから当てる。"""
    out = []
    for a in articles:
        a = {**a, "tags": site.normalize_tags(a.get("tags") or [])}
        if a.get("category") not in categories.CATEGORIES:
            a["category"] = categories.guess(a["tags"], bool(a.get("generative_ai")))
        out.append(a)
    return out


def render(articles: list[dict], site: SiteConfig, *,
           generated_at: datetime | None = None, api: bool = False,
           notify: dict | None = None) -> str:
    """記事の一覧（store.to_record の形）からページ全体の HTML を返す。

    api=True のときだけ通知設定とライブラリの同期を有効にする。受け口の /api/*
    は AWS 上のサイトにしか無いので、ローカルで書き出すページではブラウザ内に閉じる。
    """
    generated = (generated_at or datetime.now(timezone.utc)).isoformat()
    payload = {
        "generated_at": generated,
        "api": api,
        "notify": notify or {"services": list(site.notify_default),
                             "kinds": list(site.notify_kinds_default)},
        "kinds": KINDS,
        "categories": [{"key": k, "label": label, "color": color, "abbr": abbr}
                       for k, (label, color, abbr) in categories.CATEGORIES.items()],
        "articles": prepare(articles, site),
    }
    # </script> で埋め込みが途切れないようにする
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(site.title)
    return _TEMPLATE.replace("__TITLE__", title).replace("__DATA__", data)


def build(articles: list[dict], site: SiteConfig, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(articles, site), encoding="utf-8")


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<title>__TITLE__</title>
<script>try{const t=JSON.parse(localStorage.getItem('awsnews-theme'));if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;}catch(e){}</script>
<style>
:root{
  --bg:#F3F3F0; --panel:#FFFFFF; --ink:#18181B; --sub:#4E4E56; --faint:#86868F; --rule:#E2E2DD;
  --chip:#ECECE7; --accent:#2F55D4; --accent-ink:#FFFFFF; --new:#E0453A; --star:#D99A00; --sel:#EEF2FF;
  --f:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP",system-ui,sans-serif;
  --hd:0px;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#101012; --panel:#19191C; --ink:#EDEDEF; --sub:#B2B2BA; --faint:#7C7C86; --rule:#2B2B30;
  --chip:#26262B; --accent:#8CA2FF; --accent-ink:#101012; --new:#FF6B5F; --star:#F2B731; --sel:#1F2333;
  color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#101012; --panel:#19191C; --ink:#EDEDEF; --sub:#B2B2BA; --faint:#7C7C86; --rule:#2B2B30;
  --chip:#26262B; --accent:#8CA2FF; --accent-ink:#101012; --new:#FF6B5F; --star:#F2B731; --sel:#1F2333;
  color-scheme:dark}
*{box-sizing:border-box}
[hidden]{display:none!important}
html.lock,html.lock body{overflow:hidden}
body{margin:0;overflow-x:clip;background:var(--bg);color:var(--ink);font-family:var(--f);font-size:15px;line-height:1.65;-webkit-text-size-adjust:100%;-webkit-font-smoothing:antialiased}
button{font:inherit;color:inherit;cursor:pointer}
a{color:inherit}
.wrap{max-width:1240px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}

/* ヘッダー */
.hd{position:sticky;top:0;z-index:20;background:var(--panel);border-bottom:1px solid var(--rule);padding-top:env(safe-area-inset-top,0px)}
.hd-top{display:flex;align-items:center;gap:10px;padding-block:10px 8px}
.hd-top h1{margin:0;font-size:19px;font-weight:800;letter-spacing:0;line-height:1.2}
.upd{font-size:12px;color:var(--faint);font-variant-numeric:tabular-nums;white-space:nowrap}
.sp{flex:1}
.hbtn.rl{padding:5px 8px;font-size:15px;line-height:1}
.hbtn{border:1px solid var(--rule);background:var(--panel);border-radius:8px;padding:5px 10px;font-size:13px;font-weight:600;white-space:nowrap;display:inline-flex;align-items:center;gap:6px}
.hbtn:hover{border-color:var(--faint)}
.hbtn .n{min-width:18px;height:18px;border-radius:9px;background:var(--accent);color:var(--accent-ink);font-size:11px;font-weight:700;display:inline-grid;place-items:center;padding:0 5px}
.hbtn[aria-pressed="true"]{background:var(--ink);color:var(--panel);border-color:var(--ink)}
.tools{display:flex;gap:8px;padding-bottom:10px;align-items:center}
.search{flex:1;min-width:0;position:relative}
.search input{width:100%;border:1px solid var(--rule);background:var(--bg);border-radius:8px;padding:7px 34px 7px 12px;font:inherit;font-size:14px;color:var(--ink)}
.search input:focus{outline:2px solid var(--accent);outline-offset:-1px}
.search kbd{position:absolute;right:8px;top:50%;transform:translateY(-50%)}
kbd{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;border:1px solid var(--rule);border-bottom-width:2px;border-radius:4px;padding:0 5px;color:var(--sub);background:var(--panel)}
.hide-s{display:none}
@media (min-width:640px){.hide-s{display:inline-flex}.show-s{display:none}}
/* スマホ：見出しの行を画面幅に収める。はみ出すと開くたびに表示がずれる */
.ttl{display:flex;align-items:baseline;gap:10px;min-width:0}
.hd-top h1{white-space:nowrap}
@media (max-width:639.98px){
  .hd-top{gap:6px}
  .ttl{flex-direction:column;align-items:flex-start;gap:0}
  .upd{font-size:11px;line-height:1.3}
  .search input{font-size:16px}   /* 16px 未満だと iPhone が入力時に画面を拡大する */
}

/* 期間・カテゴリ */
.bar{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;padding-block:10px 0}
.bar::-webkit-scrollbar{display:none}
.chip{border:1px solid var(--rule);background:var(--panel);border-radius:999px;padding:4px 12px;font-size:13px;white-space:nowrap;display:inline-flex;align-items:center;gap:6px;flex:none}
.chip[aria-pressed="true"]{background:var(--ink);color:var(--panel);border-color:var(--ink)}
.chip .n{font-size:11.5px;color:var(--faint);font-variant-numeric:tabular-nums}
.chip[aria-pressed="true"] .n{color:inherit;opacity:.7}
.tabs{border-bottom:1px solid var(--rule);padding-bottom:10px}
.tab .heart{color:var(--new);font-size:12px}
.sw{width:10px;height:10px;border-radius:3px;background:var(--cc);flex:none}
.sortbar{display:flex;align-items:center;gap:10px;padding-block:10px;font-size:13px;color:var(--sub);flex-wrap:wrap}
.seg{display:inline-flex;border:1px solid var(--rule);border-radius:8px;overflow:hidden;background:var(--panel)}
.seg button{border:0;background:none;padding:4px 12px;font-size:13px}
.seg button[aria-pressed="true"]{background:var(--ink);color:var(--panel)}
.count b{color:var(--ink);font-variant-numeric:tabular-nums}
.active{display:flex;gap:6px;flex-wrap:wrap}
.active button{border:0;background:var(--chip);border-radius:6px;padding:2px 8px;font-size:12px}
.active button::after{content:" ×";color:var(--faint)}

/* 一覧と詳細 */
.main{display:grid;grid-template-columns:minmax(0,1fr);gap:20px;padding-bottom:40px}
@media (min-width:1024px){.main{grid-template-columns:minmax(0,1fr) 460px}}
.day{display:flex;align-items:baseline;gap:10px;margin:18px 0 8px;font-size:13px;color:var(--sub);font-weight:600}
.day:first-child{margin-top:4px}
.day b{font-size:17px;color:var(--ink);font-variant-numeric:tabular-nums;font-weight:800}
.day span:last-child{color:var(--faint);font-weight:400}
.group{background:var(--panel);border:1px solid var(--rule);border-radius:12px;overflow:hidden}
.card{display:grid;grid-template-columns:40px minmax(0,1fr) auto;gap:12px;padding:12px 14px;border-top:1px solid var(--rule);cursor:pointer;position:relative}
.card:first-child{border-top:0}
.card:hover{background:color-mix(in srgb,var(--sel) 60%,transparent)}
.card[aria-current="true"]{background:var(--sel)}
.card[aria-current="true"]::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--accent)}
.ico{width:40px;height:40px;border-radius:9px;background:var(--cc);color:#fff;display:grid;place-items:center;font-size:12px;font-weight:800;letter-spacing:.02em;flex:none}
.ico.sm{width:24px;height:24px;border-radius:6px;font-size:9px}
.card h3{margin:0;font-size:15px;line-height:1.45;font-weight:700}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--new);margin-right:6px;vertical-align:2px}
.card .sum{margin:3px 0 0;font-size:13px;color:var(--sub);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px;font-size:11.5px}
.meta span{background:var(--chip);border-radius:5px;padding:1px 7px;color:var(--sub);white-space:nowrap}
.meta .jp{background:none;border:1px solid var(--rule)}
.meta .bell{background:none;color:var(--accent);padding:1px 0}
.side{display:flex;flex-direction:column;align-items:flex-end;justify-content:space-between;gap:6px}
.stars{color:var(--star);font-size:12px;letter-spacing:1px;white-space:nowrap}
.stars i{font-style:normal;color:var(--rule)}
.bm{border:0;background:none;padding:4px;margin:-4px;color:var(--faint);line-height:0;border-radius:6px}
.bm:hover{color:var(--ink)}
.bm[aria-pressed="true"]{color:var(--accent)}
.bm svg{width:18px;height:18px}
.empty{padding:40px 16px;text-align:center;color:var(--faint);background:var(--panel);border:1px solid var(--rule);border-radius:12px}

.detail{display:none}
@media (min-width:1024px){
  .detail{display:block;position:sticky;top:calc(var(--hd) + 12px);align-self:start;max-height:calc(100vh - var(--hd) - 24px);overflow:auto;background:var(--panel);border:1px solid var(--rule);border-radius:12px}
}
@media (max-width:1023.98px){
  .detail.open{display:block;position:fixed;inset:0;z-index:40;background:var(--panel);overflow:auto;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
}
.dt-bar{position:sticky;top:0;background:var(--panel);display:flex;align-items:center;gap:6px;padding:10px 14px;border-bottom:1px solid var(--rule);z-index:1}
.dt-bar .ctr{font-size:12.5px;color:var(--faint);font-variant-numeric:tabular-nums;padding:0 4px}
.dt-body{padding:16px 18px 24px}
.dt-kick{display:flex;align-items:center;gap:8px;margin:0;font-size:12.5px;color:var(--sub);font-weight:600}
.dt-body h2{margin:10px 0 4px;font-size:20px;line-height:1.4;font-weight:800}
.orig{margin:0;font-size:12.5px;color:var(--faint)}
.dt-meta{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px 14px;margin:16px 0;padding:12px 14px;background:var(--bg);border-radius:10px}
.dt-meta dt{font-size:11px;color:var(--faint)}
.dt-meta dd{margin:0;font-size:13px;font-weight:600}
.dt-body h3{margin:18px 0 4px;font-size:12.5px;color:var(--faint);font-weight:700}
.dt-body p.txt{margin:0;font-size:15px}
.dt-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:18px}
.open-orig{display:flex;justify-content:center;align-items:center;gap:6px;margin-top:20px;padding:10px;border-radius:10px;background:var(--accent);color:var(--accent-ink);font-weight:700;text-decoration:none}
.ph{padding:40px 24px;color:var(--faint);font-size:13.5px;text-align:center}
.ph p{margin:0 0 12px}

/* ドロワー */
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:45;display:none}
.scrim.on{display:block}
.drawer{position:fixed;top:0;right:0;bottom:0;width:min(440px,100%);background:var(--panel);z-index:50;display:flex;flex-direction:column;transform:translateX(100%);transition:transform .2s ease;box-shadow:-8px 0 24px rgba(0,0,0,.12);padding-top:env(safe-area-inset-top,0px)}
.drawer.on{transform:none}
.dr-h{display:flex;align-items:center;gap:8px;padding:14px 16px;border-bottom:1px solid var(--rule)}
.dr-h h2{margin:0;font-size:16px;font-weight:800}
.dr-b{flex:1;overflow:auto;padding:4px 16px 16px}
.dr-f{display:flex;gap:8px;padding:12px 16px calc(12px + env(safe-area-inset-bottom,0px));border-top:1px solid var(--rule)}
.pri{background:var(--accent);color:var(--accent-ink);border:0;border-radius:8px;padding:8px 14px;font-weight:700}
.sec{background:none;border:1px solid var(--rule);border-radius:8px;padding:8px 12px;font-size:13.5px}
.x{border:0;background:none;font-size:20px;line-height:1;padding:4px 8px;color:var(--sub)}
.dr-b h3{margin:18px 0 8px;font-size:12.5px;color:var(--faint);font-weight:700}
.wrapchips{display:flex;flex-wrap:wrap;gap:6px}
.checks{display:grid;gap:4px}
.checks label{display:flex;align-items:center;gap:8px;font-size:14px;padding:3px 0}
.checks .n{margin-left:auto;font-size:12px;color:var(--faint)}
input[type=checkbox]{accent-color:var(--accent);width:16px;height:16px;margin:0}
.tree-q{width:100%;border:1px solid var(--rule);background:var(--bg);border-radius:8px;padding:6px 10px;font:inherit;font-size:13.5px;color:var(--ink);margin-bottom:6px}
.tree details{border-top:1px solid var(--rule)}
.tree summary{display:flex;align-items:center;gap:8px;padding:8px 0;list-style:none;cursor:pointer;font-size:14px;font-weight:600}
.tree summary::-webkit-details-marker{display:none}
.tree summary::before{content:"›";color:var(--faint);width:10px;transition:transform .15s}
.tree details[open] summary::before{transform:rotate(90deg)}
.tree .n{margin-left:auto;font-size:12px;color:var(--faint);font-weight:400}
.tree .svcs{padding:0 0 8px 18px}
.tree .svcs label{display:flex;align-items:center;gap:8px;font-size:13.5px;padding:3px 0}
.hrt{border:0;background:none;padding:0 4px;font-size:15px;color:var(--faint);line-height:1}
.hrt[aria-pressed="true"]{color:var(--new)}
.ltabs{display:flex;gap:4px;padding:10px 16px 0;border-bottom:1px solid var(--rule)}
.ltabs button{border:0;background:none;padding:8px 10px;font-size:13.5px;color:var(--sub);border-bottom:2px solid transparent;margin-bottom:-1px}
.ltabs button[aria-selected="true"]{color:var(--ink);font-weight:700;border-color:var(--ink)}
.sync{font-size:12px;color:var(--faint);display:flex;align-items:center;gap:6px}
.sync::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--faint)}
.sync[data-s="ok"]::before{background:#2E9E5B}
.sync[data-s="sync"]::before{background:var(--star)}
.sync[data-s="err"]::before{background:var(--new)}
.litem{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--rule)}
.litem .t{flex:1;min-width:0;border:0;background:none;text-align:left;padding:0}
.litem .t b{display:block;font-size:14px;line-height:1.45}
.litem .t small{display:block;font-size:12px;color:var(--faint)}
.lhint{font-size:13px;color:var(--faint);padding:16px 0}

dialog{border:0;border-radius:14px;padding:0;background:var(--panel);color:var(--ink);width:min(480px,calc(100% - 32px));max-height:calc(100% - 48px)}
dialog::backdrop{background:rgba(0,0,0,.4)}
.dlg{display:flex;flex-direction:column;max-height:calc(100vh - 48px)}
.dlg-h{display:flex;align-items:center;padding:14px 18px;border-bottom:1px solid var(--rule)}
.dlg-h h2{margin:0;font-size:16px;font-weight:800;flex:1}
.dlg-b{overflow:auto;padding:4px 18px 14px}
.dlg-f{display:flex;justify-content:flex-end;gap:8px;padding:12px 18px;border-top:1px solid var(--rule)}
.dlg-b h3{font-size:12.5px;color:var(--faint);margin:16px 0 6px}
.hint{font-size:13px;color:var(--sub)}
.keys{width:100%;border-collapse:collapse;font-size:13.5px}
.keys td{padding:6px 0;border-bottom:1px solid var(--rule)}
.keys td:first-child{width:110px}
footer{padding:8px 0 32px;font-size:12px;color:var(--faint)}
</style>
</head>
<body>
<header class="hd" id="hd"><div class="wrap">
  <div class="hd-top">
    <div class="ttl"><h1>__TITLE__</h1><span class="upd" id="upd"></span></div><button class="hbtn rl" id="reloadbtn" title="最新の記事を読み直す（R）" aria-label="最新の記事を読み直す">↻</button><span class="sp"></span>
    <button class="hbtn" id="libbtn" title="マイライブラリ（L）">ライブラリ<span class="n" id="libn" hidden></span></button>
    <button class="hbtn" id="setbtn" hidden title="Slack 通知の設定">通知</button>
    <button class="hbtn" id="themebtn" title="表示テーマを切り替える"></button>
  </div>
  <div class="tools">
    <div class="search"><label class="vh" for="q">記事を検索</label><input type="search" id="q" placeholder="見出し・要約・サービス名で検索" autocomplete="off"><kbd class="hide-s">/</kbd></div>
    <button class="hbtn" id="newbtn" aria-pressed="false" title="前回ひらいた後の記事だけ">新着<span class="n" id="newn" hidden></span></button>
    <button class="hbtn" id="filbtn" title="絞り込み（F）">絞り込み<span class="n" id="filn" hidden></span></button>
    <button class="hbtn hide-s" id="helpbtn" title="キーボード操作（?）">?</button>
  </div>
</div></header>

<div class="wrap">
  <nav class="bar" id="periods" aria-label="期間"></nav>
  <nav class="bar tabs" id="tabs" aria-label="カテゴリ"></nav>
  <div class="sortbar" id="sortbar"></div>
  <div class="main">
    <div id="list"></div>
    <aside class="detail" id="detail" aria-label="記事の詳細"></aside>
  </div>
  <footer>見出し・要約・注目度・カテゴリは AI による自動生成です。判断の前に原文を確認してください。</footer>
</div>

<div class="scrim" id="scrim"></div>
<section class="drawer" id="fil" aria-label="絞り込み">
  <div class="dr-h"><h2>絞り込み</h2><span class="sp"></span><button class="x" data-close-drawer aria-label="閉じる">×</button></div>
  <div class="dr-b" id="fil-b"></div>
  <div class="dr-f"><button class="pri" data-close-drawer id="fil-show"></button><span class="sp"></span><button class="sec" id="fil-save">条件を保存</button><button class="sec" id="fil-reset">リセット</button></div>
</section>
<section class="drawer" id="lib" aria-label="マイライブラリ">
  <div class="dr-h"><h2>マイライブラリ</h2><span class="sync" id="sync"></span><span class="sp"></span><button class="x" data-close-drawer aria-label="閉じる">×</button></div>
  <div class="ltabs" role="tablist" id="ltabs"></div>
  <div class="dr-b" id="lib-b"></div>
</section>

<dialog id="dset" aria-labelledby="dset-h"><form method="dialog" class="dlg">
  <div class="dlg-h"><h2 id="dset-h">通知の設定</h2></div>
  <div class="dlg-b">
    <p class="hint">チェックしたサービスの、チェックした種類の新着を Slack に送ります。生成 AI の新サービスは、ここの設定にかかわらず送ります。</p>
    <h3>種類</h3>
    <div class="checks" id="dset-kinds"></div>
    <h3>サービス</h3>
    <input type="search" class="tree-q" id="dset-q" placeholder="サービス名で絞り込む" autocomplete="off">
    <div class="checks" id="dset-list"></div>
  </div>
  <div class="dlg-f"><button class="sec" value="cancel">やめる</button><button class="pri" value="save">保存</button></div>
</form></dialog>

<dialog id="dhelp" aria-labelledby="dhelp-h"><form method="dialog" class="dlg">
  <div class="dlg-h"><h2 id="dhelp-h">キーボード操作</h2><button class="x" value="close" aria-label="閉じる">×</button></div>
  <div class="dlg-b"><table class="keys"><tbody>
    <tr><td><kbd>j</kbd> <kbd>↓</kbd></td><td>次の記事</td></tr>
    <tr><td><kbd>k</kbd> <kbd>↑</kbd></td><td>前の記事</td></tr>
    <tr><td><kbd>o</kbd></td><td>原文を開く</td></tr>
    <tr><td><kbd>s</kbd></td><td>選んでいる記事を保存する・外す</td></tr>
    <tr><td><kbd>/</kbd></td><td>検索</td></tr>
    <tr><td><kbd>f</kbd></td><td>絞り込み</td></tr>
    <tr><td><kbd>l</kbd></td><td>マイライブラリ</td></tr>
    <tr><td><kbd>r</kbd></td><td>最新の記事を読み直す</td></tr>
    <tr><td><kbd>Esc</kbd></td><td>閉じる</td></tr>
    <tr><td><kbd>?</kbd></td><td>この一覧</td></tr>
  </tbody></table></div>
</form></dialog>

<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
  const D=JSON.parse(document.getElementById('data').textContent);
  const $=s=>document.querySelector(s);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const LS={get(k,d){try{const v=localStorage.getItem(k);return v==null?d:JSON.parse(v);}catch(e){return d;}},
            set(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}}};

  // 情報源。ここに無いエージェントの記事は出さない
  const SRC={'aws-whatsnew':"What's New",'aws-ai':'AWS ブログ'};
  const KINDS=D.kinds, kShort=k=>k&&KINDS[k]?KINDS[k].split('（')[0]:'';
  const CAT=Object.fromEntries(D.categories.map(c=>[c.key,c]));
  const JP={tokyo_osaka:'東京・大阪',tokyo:'東京',osaka:'大阪',none:'日本は対象外',unknown:'記載なし'};
  const tokyoOk=a=>a.jp_regions==='tokyo'||a.jp_regions==='tokyo_osaka';
  const pub=a=>a.published_at||a.sort_at||D.generated_at;
  const A=D.articles.filter(a=>SRC[a.agent_key]).map((a,i)=>{
    const c=CAT[a.category]||CAT.other;
    return {...a,_i:i,_t:Date.parse(pub(a)),_c:c,
      _h:[a.title_ja,a.title_original,a.summary,a.impact,c.label,...(a.tags||[])].join(' ').toLowerCase()};
  });
  const byUrl=new Map(A.map(a=>[a.url,a]));

  const tz={timeZone:'Asia/Tokyo'};
  const fUpd=new Intl.DateTimeFormat('ja-JP',{...tz,month:'numeric',day:'numeric',hour:'numeric',minute:'2-digit'});
  const fMd=new Intl.DateTimeFormat('ja-JP',{...tz,month:'numeric',day:'numeric'});
  const fWd=new Intl.DateTimeFormat('ja-JP',{...tz,weekday:'long'});
  const fFull=new Intl.DateTimeFormat('ja-JP',{...tz,year:'numeric',month:'long',day:'numeric',weekday:'short'});
  const dayKey=t=>new Intl.DateTimeFormat('en-CA',tz).format(new Date(t));
  const dot=t=>fMd.format(new Date(t)).replace('/','.');
  $('#upd').textContent=fUpd.format(new Date(D.generated_at))+' 更新';

  // 期間は日本時間で区切る。週は月曜はじまり
  const H9=9*36e5, DAY=864e5;
  const PERIODS=[['today','今日'],['this_week','今週'],['last_week','先週'],['this_month','今月'],['last_month','先月'],['all','すべて']];
  function ranges(){
    const j=new Date(Date.now()+H9), y=j.getUTCFullYear(), m=j.getUTCMonth(), w=(j.getUTCDay()+6)%7;
    const today=Date.UTC(y,m,j.getUTCDate())-H9, week=today-w*DAY;
    const month=Date.UTC(y,m,1)-H9, prev=Date.UTC(y,m-1,1)-H9;
    return {all:[-Infinity,Infinity],today:[today,Infinity],this_week:[week,Infinity],last_week:[week-7*DAY,week],this_month:[month,Infinity],last_month:[prev,month]};
  }
  let R=ranges();

  // 新着は前回ひらいた時刻より後の記事。初めて開いたときは更新の 24 時間前を前回とみなす
  let seen=Date.parse(D.generated_at)-DAY;
  try{const v=localStorage.getItem('awsnews-seen'); if(v&&!isNaN(Date.parse(v))) seen=Date.parse(v);}catch(e){}
  addEventListener('pagehide',()=>{try{localStorage.setItem('awsnews-seen',new Date().toISOString());}catch(e){}});
  const isNew=a=>a._t>seen;

  // 表示の状態。検索語と新着だけは毎回まっさらから始める
  const DEF={period:'all',cat:'all',sort:'date',minImp:0,sources:[],kinds:[],tokyo:false,services:[]};
  let S={...DEF,...LS.get('awsnews-view',{}),q:'',onlyNew:false};
  if(!PERIODS.some(p=>p[0]===S.period)) S.period='all';
  const saveView=()=>{const {q,onlyNew,...v}=S; LS.set('awsnews-view',v);};

  // テーマ: 自動 → ライト → ダーク
  const THEMES={auto:'自動',light:'ライト',dark:'ダーク'};
  let theme=LS.get('awsnews-theme','auto'); if(!THEMES[theme]) theme='auto';
  function applyTheme(){
    if(theme==='auto') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme=theme;
    // スマホでは幅が足りないので、記号だけにする
    $('#themebtn').innerHTML='<span class="show-s" aria-hidden="true">◐</span><span class="hide-s">テーマ: '+THEMES[theme]+'</span>';
    $('#themebtn').setAttribute('aria-label','テーマ: '+THEMES[theme]);
  }
  applyTheme();
  // ブラウザのキャッシュを避けるため、クエリを付けて開き直す。CloudFront 側は最大 60 秒前の版になりうる
  const reload=()=>{const u=new URL(location.href); u.searchParams.set('r',Date.now()); location.replace(u.toString());};
  $('#reloadbtn').addEventListener('click',reload);
  $('#themebtn').addEventListener('click',()=>{const k=Object.keys(THEMES); theme=k[(k.indexOf(theme)+1)%k.length]; LS.set('awsnews-theme',theme); applyTheme();});

  // ---- マイライブラリ（localStorage に持ち、AWS 上では /api/library と揃える） ----
  let LIB={favorites:[],saved:[],presets:[],updated_at:null,dirty:false,...LS.get('awsnews-lib',{})};
  let syncState=D.api?'sync':'local', syncTimer=null;
  const SYNC={ok:'同期済み',local:'この端末だけ',sync:'同期中',err:'同期できません'};
  const libBody=()=>({favorites:LIB.favorites,saved:LIB.saved,presets:LIB.presets});
  function libChanged(){
    LIB.updated_at=new Date().toISOString(); LIB.dirty=true; LS.set('awsnews-lib',LIB);
    if(D.api){ syncState='sync'; clearTimeout(syncTimer); syncTimer=setTimeout(pushLib,700); }
    renderSync(); renderLibCount();
  }
  async function pushLib(){
    try{ const r=await post('/api/library',libBody()); LIB={...LIB,...r,dirty:false}; LS.set('awsnews-lib',LIB); syncState='ok'; }
    catch(e){ syncState='err'; }
    renderSync();
  }
  async function pullLib(){
    try{
      const r=await get('/api/library');
      // この端末で変えたまま送れていない分が新しければ、こちらを正にする
      if(LIB.dirty&&(!r.updated_at||LIB.updated_at>r.updated_at)){ await pushLib(); return; }
      LIB={favorites:r.favorites||[],saved:r.saved||[],presets:r.presets||[],updated_at:r.updated_at,dirty:false};
      LS.set('awsnews-lib',LIB); syncState='ok'; renderAll();
    }catch(e){ syncState='err'; }
    renderSync();
  }
  function renderSync(){ const el=$('#sync'); el.dataset.s=syncState; el.textContent=SYNC[syncState]; }
  function renderLibCount(){ const n=LIB.saved.length, el=$('#libn'); el.hidden=!n; el.textContent=n; }
  const isFav=k=>LIB.favorites.includes(k);
  function toggleFav(k){ LIB.favorites=isFav(k)?LIB.favorites.filter(x=>x!==k):[...LIB.favorites,k]; libChanged(); renderAll(); }
  const isSaved=url=>LIB.saved.some(s=>s.url===url);
  function toggleSave(a){
    if(!a) return;
    if(isSaved(a.url)) LIB.saved=LIB.saved.filter(s=>s.url!==a.url);
    else LIB.saved=[{url:a.url,title_ja:a.title_ja,published_at:pub(a),importance:a.importance??null,category:a.category,
                     agent_key:a.agent_key,summary:a.summary,saved_at:new Date().toISOString()},...LIB.saved];
    libChanged(); renderList(); renderDetail(); if(drawer==='lib') renderLib();
  }
  const favLabel=k=>k.startsWith('c:')?(CAT[k.slice(2)]||{label:k}).label:k.slice(2);

  // ---- 絞り込み ----
  function pass(a,skip){
    const [lo,hi]=R[S.period];
    if(a._t<lo||a._t>=hi) return false;
    if(S.onlyNew&&!isNew(a)) return false;
    if(S.minImp&&(a.importance||0)<S.minImp) return false;
    if(S.sources.length&&!S.sources.includes(a.agent_key)) return false;
    if(S.kinds.length&&!S.kinds.includes(a.kind)) return false;
    if(S.tokyo&&!tokyoOk(a)) return false;
    if(skip!=='svc'&&S.services.length&&!(a.tags||[]).some(t=>S.services.includes(t))) return false;
    if(S.q){ for(const w of S.q.toLowerCase().split(/\s+/)) if(w&&!a._h.includes(w)) return false; }
    if(skip!=='cat'&&skip!=='svc'&&!inCat(a,S.cat)) return false;
    return true;
  }
  const inCat=(a,k)=>k==='all'||(k.startsWith('s:')?(a.tags||[]).includes(k.slice(2)):a.category===k.slice(2));
  const activeCount=()=>(S.minImp?1:0)+(S.sources.length?1:0)+(S.kinds.length?1:0)+(S.tokyo?1:0)+(S.services.length?1:0);
  let L=[], selUrl=null;
  function compute(){
    L=A.filter(a=>pass(a));
    L.sort(S.sort==='imp'?(x,y)=>(y.importance||0)-(x.importance||0)||y._t-x._t:(x,y)=>y._t-x._t);
  }

  // ---- 描画 ----
  const stars=n=>n?`<span class="stars" aria-label="注目度 ${n}">${'★'.repeat(n)}<i>${'★'.repeat(3-n)}</i></span>`:'<span class="stars" aria-label="注目度なし"><i>★★★</i></span>';
  const ico=(c,sm)=>`<span class="ico${sm?' sm':''}" style="--cc:${c.color}" aria-hidden="true">${esc(c.abbr)}</span>`;
  const BM='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M6 3h12v18l-6-4.5L6 21z"/></svg>';
  const BMF='<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M6 3h12v18l-6-4.5L6 21z"/></svg>';
  let notifySet=new Set(), kindSet=new Set();
  const setNotify=n=>{D.notify=n; notifySet=new Set(n.services.map(s=>s.toLowerCase())); kindSet=new Set(n.kinds);};
  setNotify(D.notify);
  const isBell=a=>(a.kind==='new_service'&&a.generative_ai)||((!a.kind||kindSet.has(a.kind))&&(a.tags||[]).some(t=>notifySet.has(t.toLowerCase())));

  function renderPeriods(){
    $('#periods').innerHTML=PERIODS.map(([k,l])=>`<button class="chip" data-period="${k}" aria-pressed="${S.period===k}">${l}</button>`).join('');
  }
  function renderTabs(){
    const pool=A.filter(a=>pass(a,'cat'));
    const cnt=k=>pool.filter(a=>inCat(a,k)).length;
    const cats=D.categories.map(c=>'c:'+c.key).filter(k=>!isFav(k));
    const tabs=['all',...LIB.favorites,...cats.map(k=>[k,cnt(k)]).filter(([k,n])=>n||S.cat===k).sort((x,y)=>y[1]-x[1]).map(x=>x[0])];
    $('#tabs').innerHTML=tabs.map(k=>{
      const c=k.startsWith('c:')?CAT[k.slice(2)]:null;
      const label=k==='all'?'すべて':favLabel(k);
      return `<button class="chip tab" data-cat="${esc(k)}" aria-pressed="${S.cat===k}">${isFav(k)?'<span class="heart">♥</span>':''}${c?`<span class="sw" style="--cc:${c.color}"></span>`:''}${esc(label)}<span class="n">${k==='all'?pool.length:cnt(k)}</span></button>`;
    }).join('');
  }
  function renderSortbar(){
    const chips=[];
    if(S.minImp) chips.push(['minImp',`★${S.minImp}以上`]);
    S.sources.forEach(s=>chips.push(['src:'+s,SRC[s]]));
    S.kinds.forEach(k=>chips.push(['kind:'+k,kShort(k)]));
    if(S.tokyo) chips.push(['tokyo','東京で利用可']);
    S.services.forEach(s=>chips.push(['svc:'+s,s]));
    if(S.q) chips.push(['q',`「${S.q}」`]);
    $('#sortbar').innerHTML=`<div class="seg" role="group" aria-label="並び順"><button data-sort="date" aria-pressed="${S.sort==='date'}">日付順</button><button data-sort="imp" aria-pressed="${S.sort==='imp'}">注目度順</button></div>
      <span class="count"><b>${L.length}</b> 件</span><span class="active">${chips.map(([k,l])=>`<button data-unset="${esc(k)}" title="外す">${esc(l)}</button>`).join('')}</span>`;
    const n=activeCount(), fn=$('#filn'); fn.hidden=!n; fn.textContent=n;
    const nn=A.filter(isNew).length, ne=$('#newn'); ne.hidden=!nn; ne.textContent=nn;
    $('#newbtn').setAttribute('aria-pressed',S.onlyNew);
  }
  function card(a){
    const svc=(a.tags||[])[0]||a._c.label;
    return `<article class="card" data-url="${esc(a.url)}" aria-current="${a.url===selUrl}">
      ${ico(a._c)}
      <div><h3>${isNew(a)?'<i class="dot" title="新着"></i>':''}${esc(a.title_ja)}</h3>
        <p class="sum">${esc(a.summary)}</p>
        <div class="meta"><span>${esc(svc)}</span>${a.kind?`<span>${esc(kShort(a.kind))}</span>`:''}${tokyoOk(a)?'<span class="jp">東京</span>':''}${S.sort==='imp'?`<span>${dot(a._t)}</span>`:''}${D.api&&isBell(a)?'<span class="bell">通知</span>':''}</div></div>
      <div class="side">${stars(a.importance)}<button class="bm" data-save="${esc(a.url)}" aria-pressed="${isSaved(a.url)}" aria-label="保存">${isSaved(a.url)?BMF:BM}</button></div>
    </article>`;
  }
  function renderList(){
    if(!L.length){ $('#list').innerHTML='<p class="empty">この条件の記事はありません。</p>'; return; }
    let h='';
    if(S.sort==='date'){
      const groups=new Map();
      L.forEach(a=>{const k=dayKey(a._t); if(!groups.has(k)) groups.set(k,[]); groups.get(k).push(a);});
      for(const items of groups.values()){
        const t=items[0]._t;
        h+=`<h2 class="day"><b>${dot(t)}</b><span>${fWd.format(new Date(t))}</span><span>${items.length} 件</span></h2><div class="group">${items.map(card).join('')}</div>`;
      }
    } else h=`<div class="group">${L.map(card).join('')}</div>`;
    $('#list').innerHTML=h;
  }
  function renderDetail(){
    const el=$('#detail'), a=selUrl&&byUrl.get(selUrl);
    if(!a){
      el.innerHTML=`<div class="ph"><p>記事を選ぶと、ここに詳細が出ます。</p><p><kbd>j</kbd> <kbd>k</kbd> で移動、<kbd>o</kbd> で原文、<kbd>s</kbd> で保存。</p></div>`;
      return;
    }
    const i=L.indexOf(a);
    el.innerHTML=`<div class="dt-bar"><button class="sec" data-nav="-1" ${i<=0?'disabled':''} aria-label="前の記事">‹</button><span class="ctr">${i<0?'—':i+1} / ${L.length}</span><button class="sec" data-nav="1" ${i<0||i>=L.length-1?'disabled':''} aria-label="次の記事">›</button><span class="sp"></span>
        <button class="bm" data-save="${esc(a.url)}" aria-pressed="${isSaved(a.url)}" aria-label="保存">${isSaved(a.url)?BMF:BM}</button><button class="x" data-close-detail aria-label="閉じる">×</button></div>
      <div class="dt-body">
        <p class="dt-kick">${ico(a._c,true)}${esc((a.tags||[])[0]||'')}<span style="color:var(--faint)">${esc(a._c.label)}</span></p>
        <h2>${esc(a.title_ja)}</h2><p class="orig">${esc(a.title_original)}</p>
        <dl class="dt-meta">
          <div><dt>発表日</dt><dd>${fFull.format(new Date(a._t))}</dd></div>
          <div><dt>注目度</dt><dd>${stars(a.importance)}</dd></div>
          <div><dt>種類</dt><dd>${esc(kShort(a.kind)||'—')}</dd></div>
          <div><dt>国内</dt><dd>${esc(JP[a.jp_regions]||'—')}</dd></div>
          <div><dt>情報源</dt><dd>${esc(SRC[a.agent_key])}</dd></div>
          ${D.api?`<div><dt>Slack 通知</dt><dd>${isBell(a)?'対象':'対象外'}</dd></div>`:''}
        </dl>
        <h3>概要</h3><p class="txt">${esc(a.summary)}</p>
        <h3>何が変わるか</h3><p class="txt">${esc(a.impact)}</p>
        <div class="dt-tags">${(a.tags||[]).map(t=>`<button class="chip" data-svc="${esc(t)}" aria-pressed="${S.services.includes(t)}">${esc(t)}</button>`).join('')}</div>
        <a class="open-orig" href="${esc(a.url)}" target="_blank" rel="noopener">原文を開く ↗</a>
      </div>`;
  }
  function renderAll(){
    R=ranges(); compute(); renderPeriods(); renderTabs(); renderSortbar(); renderList(); renderDetail();
    if(drawer==='fil') renderFil(); if(drawer==='lib') renderLib();
    renderLibCount();
  }
  function change(fn){ fn(); saveView(); renderAll(); }

  // ---- 詳細の開閉と移動 ----
  const wide=matchMedia('(min-width:1024px)');
  function select(url,{open=true,scroll=false}={}){
    selUrl=url;
    document.querySelectorAll('.card[aria-current="true"]').forEach(c=>c.setAttribute('aria-current','false'));
    const c=[...document.querySelectorAll('.card')].find(x=>x.dataset.url===url);
    if(c){ c.setAttribute('aria-current','true'); if(scroll) c.scrollIntoView({block:'nearest'}); }
    renderDetail(); $('#detail').scrollTop=0;
    if(open&&!wide.matches){ $('#detail').classList.add('open'); document.documentElement.classList.add('lock'); }
  }
  function closeDetail(){
    if(wide.matches){ selUrl=null; renderList(); renderDetail(); return; }
    $('#detail').classList.remove('open'); document.documentElement.classList.remove('lock');
  }
  function move(d){
    if(!L.length) return;
    const i=L.findIndex(a=>a.url===selUrl);
    const n=i<0?0:Math.max(0,Math.min(L.length-1,i+d));
    select(L[n].url,{open:false,scroll:true});
  }

  // ---- ドロワー ----
  let drawer=null, libTab='fav';
  function openDrawer(id){
    drawer=id; document.querySelectorAll('.drawer').forEach(d=>d.classList.toggle('on',d.id===id));
    $('#scrim').classList.add('on'); document.documentElement.classList.add('lock');
    id==='fil'?renderFil():renderLib();
  }
  function closeDrawer(){
    drawer=null; document.querySelectorAll('.drawer').forEach(d=>d.classList.remove('on'));
    $('#scrim').classList.remove('on');
    if(!$('#detail').classList.contains('open')) document.documentElement.classList.remove('lock');
  }
  let treeQ='', openCats=new Set();
  function renderFil(){
    const pool=A.filter(a=>pass(a,'svc'));
    const svcCount=new Map(), catCount=new Map(), svcCat=new Map();
    pool.forEach(a=>{catCount.set(a.category,(catCount.get(a.category)||0)+1);
      (a.tags||[]).forEach(t=>{svcCount.set(t,(svcCount.get(t)||0)+1); if(!svcCat.has(t)) svcCat.set(t,a.category);});});
    S.services.forEach(t=>{ if(!svcCat.has(t)) svcCat.set(t,(A.find(a=>(a.tags||[]).includes(t))||{category:'other'}).category); });
    const q=treeQ.toLowerCase();
    const tree=D.categories.map(c=>{
      const svcs=[...svcCat].filter(([t,k])=>k===c.key&&(!q||t.toLowerCase().includes(q)||c.label.toLowerCase().includes(q)))
        .map(([t])=>t).sort((x,y)=>(svcCount.get(y)||0)-(svcCount.get(x)||0)||x.localeCompare(y));
      if(!svcs.length&&(q||!catCount.get(c.key))) return '';
      const fk='c:'+c.key, open=q||openCats.has(c.key)||svcs.some(t=>S.services.includes(t));
      return `<details data-tree="${c.key}" ${open?'open':''}><summary>${ico(c,true)}${esc(c.label)}<span class="n">${catCount.get(c.key)||0}</span><button type="button" class="hrt" data-fav="${fk}" aria-pressed="${isFav(fk)}" aria-label="お気に入り">${isFav(fk)?'♥':'♡'}</button></summary>
        <div class="svcs">${svcs.map(t=>`<label><input type="checkbox" data-svcchk="${esc(t)}" ${S.services.includes(t)?'checked':''}>${esc(t)}<span class="n" style="margin-left:auto">${svcCount.get(t)||0}</span><button type="button" class="hrt" data-fav="${esc('s:'+t)}" aria-pressed="${isFav('s:'+t)}" aria-label="お気に入り">${isFav('s:'+t)?'♥':'♡'}</button></label>`).join('')}</div></details>`;
    }).join('');
    const focused=document.activeElement&&document.activeElement.id==='tree-q';
    $('#fil-b').innerHTML=`<h3>期間</h3><div class="wrapchips">${PERIODS.map(([k,l])=>`<button class="chip" data-period="${k}" aria-pressed="${S.period===k}">${l}</button>`).join('')}</div>
      <h3>注目度</h3><div class="seg" role="group">${[[0,'すべて'],[1,'★1以上'],[2,'★2以上'],[3,'★3']].map(([v,l])=>`<button data-imp="${v}" aria-pressed="${S.minImp===v}">${l}</button>`).join('')}</div>
      <h3>情報源</h3><div class="checks">${Object.entries(SRC).map(([k,l])=>`<label><input type="checkbox" data-src="${k}" ${S.sources.includes(k)?'checked':''}>${esc(l)}</label>`).join('')}</div>
      <h3>種類</h3><div class="checks">${Object.keys(KINDS).map(k=>`<label><input type="checkbox" data-kind="${k}" ${S.kinds.includes(k)?'checked':''}>${esc(KINDS[k])}</label>`).join('')}</div>
      <h3>リージョン</h3><div class="checks"><label><input type="checkbox" data-tokyo ${S.tokyo?'checked':''}>東京リージョンで使えると書かれている記事だけ</label></div>
      <h3>カテゴリとサービス</h3><input type="search" class="tree-q" id="tree-q" placeholder="サービス名で探す" value="${esc(treeQ)}" autocomplete="off"><div class="tree">${tree||'<p class="lhint">当てはまるサービスがありません。</p>'}</div>`;
    if(focused){ const t=$('#tree-q'); t.focus(); t.setSelectionRange(t.value.length,t.value.length); }
    $('#fil-show').textContent=`${L.length} 件を表示`;
  }
  function presetSummary(f){
    const p=[];
    p.push((PERIODS.find(x=>x[0]===f.period)||[0,'すべて'])[1]);
    if(f.cat&&f.cat!=='all') p.push(favLabel(f.cat));
    if(f.minImp) p.push(`★${f.minImp}以上`);
    (f.kinds||[]).forEach(k=>p.push(kShort(k)));
    (f.sources||[]).forEach(s=>p.push(SRC[s]));
    if(f.tokyo) p.push('東京');
    (f.services||[]).forEach(s=>p.push(s));
    return p.join(' ・ ');
  }
  function renderLib(){
    const T=[['fav','お気に入り',LIB.favorites.length],['saved','保存した記事',LIB.saved.length],['presets','保存した条件',LIB.presets.length]];
    $('#ltabs').innerHTML=T.map(([k,l,n])=>`<button role="tab" data-ltab="${k}" aria-selected="${libTab===k}">${l} ${n}</button>`).join('');
    let h='';
    if(libTab==='fav'){
      h=LIB.favorites.length?LIB.favorites.map(k=>{const c=k.startsWith('c:')?CAT[k.slice(2)]:null;
        return `<div class="litem">${c?ico(c,true):'<span class="ico sm" style="--cc:var(--faint)">SVC</span>'}<button class="t" data-gocat="${esc(k)}"><b>${esc(favLabel(k))}</b><small>${A.filter(a=>inCat(a,k)).length} 件 ・ ${c?'カテゴリ':'サービス'}</small></button><button class="hrt" data-fav="${esc(k)}" aria-pressed="true" aria-label="お気に入りから外す">♥</button></div>`;}).join('')
        :'<p class="lhint">絞り込みの「カテゴリとサービス」で ♡ を押すと、ここに並び、カテゴリのタブの先頭にも出ます。</p>';
    } else if(libTab==='saved'){
      h=LIB.saved.length?LIB.saved.map(s=>{const c=CAT[s.category]||CAT.other;
        return `<div class="litem">${ico(c,true)}<button class="t" data-goart="${esc(s.url)}"><b>${esc(s.title_ja)}</b><small>${s.published_at?dot(Date.parse(s.published_at)):''} ・ ${esc(c.label)}${byUrl.has(s.url)?'':' ・ 表示期間の外'}</small></button><button class="bm" data-save="${esc(s.url)}" aria-pressed="true" aria-label="保存を外す">${BMF}</button></div>`;}).join('')
        :'<p class="lhint">記事の右の栞を押すと保存できます。表示期間（60 日）を過ぎても、ここには残ります。</p>';
    } else {
      h=LIB.presets.length?LIB.presets.map((p,i)=>`<div class="litem"><button class="t" data-preset="${i}"><b>${esc(p.name)}</b><small>${esc(presetSummary(p.filters))}</small></button><button class="x" data-delpreset="${i}" aria-label="削除">×</button></div>`).join('')
        :'<p class="lhint">絞り込みの「条件を保存」で、今の期間・カテゴリ・条件を名前を付けて残せます。</p>';
    }
    $('#lib-b').innerHTML=h;
  }

  // ---- API ----
  // CloudFront の OAC 経由で Lambda に POST するときは、本文の SHA-256 をヘッダーで渡す決まり
  async function post(path,obj){
    const body=JSON.stringify(obj);
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(body));
    const hex=[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
    const res=await fetch(path,{method:'POST',headers:{'content-type':'application/json','x-amz-content-sha256':hex},body});
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }
  async function get(path){
    const res=await fetch(path,{cache:'no-store'});
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  // ---- 通知設定 ----
  const dset=$('#dset'), dlist=$('#dset-list'), dq=$('#dset-q'), dkinds=$('#dset-kinds');
  let draftSet=new Set(), draftKinds=new Set();
  function renderKinds(){
    dkinds.innerHTML=Object.entries(KINDS).map(([k,t])=>`<label><input type="checkbox" data-nkind="${esc(k)}" ${draftKinds.has(k)?'checked':''}>${esc(t)}</label>`).join('');
  }
  function renderSettings(){
    const c=new Map(); A.forEach(a=>(a.tags||[]).forEach(t=>c.set(t,(c.get(t)||0)+1)));
    // 保存済みで直近の記事に出てこないサービスも残す
    const names=new Map([...c.keys()].map(t=>[t.toLowerCase(),t]));
    draftSet.forEach(s=>{ if(!names.has(s)) names.set(s,D.notify.services.find(x=>x.toLowerCase()===s)||s); });
    const q=dq.value.trim().toLowerCase();
    const list=[...names].filter(([k])=>!q||k.includes(q))
      .sort((x,y)=>draftSet.has(y[0])-draftSet.has(x[0])||(c.get(y[1])||0)-(c.get(x[1])||0)||x[1].localeCompare(y[1],'ja'));
    dlist.innerHTML=list.map(([k,t])=>`<label><input type="checkbox" data-nsvc="${esc(k)}" data-name="${esc(t)}" ${draftSet.has(k)?'checked':''}>${esc(t)}<span class="n">${c.get(t)||0} 件</span></label>`).join('')||'<p class="hint">当てはまるサービスがありません。</p>';
  }
  $('#setbtn').addEventListener('click',()=>{draftSet=new Set(notifySet); draftKinds=new Set(kindSet); dq.value=''; renderKinds(); renderSettings(); dset.showModal();});
  dkinds.addEventListener('change',e=>{const k=e.target.dataset.nkind; if(!k) return; e.target.checked?draftKinds.add(k):draftKinds.delete(k);});
  dq.addEventListener('input',renderSettings);
  dlist.addEventListener('change',e=>{const k=e.target.dataset.nsvc; if(!k) return; e.target.checked?draftSet.add(k):draftSet.delete(k);});
  dset.addEventListener('close',async()=>{
    if(dset.returnValue!=='save') return;
    const named=new Map([...dlist.querySelectorAll('[data-nsvc]')].map(i=>[i.dataset.nsvc,i.dataset.name]));
    A.forEach(a=>(a.tags||[]).forEach(t=>named.has(t.toLowerCase())||named.set(t.toLowerCase(),t)));
    D.notify.services.forEach(t=>named.has(t.toLowerCase())||named.set(t.toLowerCase(),t));
    const services=[...draftSet].map(k=>named.get(k)||k);
    try{ setNotify(await post('/api/settings',{services,kinds:[...draftKinds]})); renderAll(); }
    catch(err){ alert(`保存できませんでした（${err.message}）`); }
  });

  // ---- 操作 ----
  const qEl=$('#q'); let qTimer=null;
  qEl.addEventListener('input',()=>{clearTimeout(qTimer); qTimer=setTimeout(()=>{S.q=qEl.value.trim(); renderAll();},120);});
  $('#newbtn').addEventListener('click',()=>{S.onlyNew=!S.onlyNew; renderAll();});
  $('#filbtn').addEventListener('click',()=>openDrawer('fil'));
  $('#libbtn').addEventListener('click',()=>openDrawer('lib'));
  $('#helpbtn').addEventListener('click',()=>$('#dhelp').showModal());
  $('#scrim').addEventListener('click',closeDrawer);
  $('#fil-reset').addEventListener('click',()=>change(()=>{S={...DEF,q:S.q,onlyNew:S.onlyNew};}));
  $('#fil-save').addEventListener('click',()=>{
    const name=prompt('この条件に付ける名前',presetSummary(S).slice(0,40));
    if(!name) return;
    const {q,onlyNew,...filters}=S;
    LIB.presets=[{name:name.slice(0,40),filters},...LIB.presets]; libChanged();
    libTab='presets'; openDrawer('lib');
  });

  document.addEventListener('change',e=>{
    const t=e.target, d=t.dataset;
    if('src' in d) change(()=>{S.sources=t.checked?[...S.sources,d.src]:S.sources.filter(x=>x!==d.src);});
    else if('kind' in d) change(()=>{S.kinds=t.checked?[...S.kinds,d.kind]:S.kinds.filter(x=>x!==d.kind);});
    else if('tokyo' in d) change(()=>{S.tokyo=t.checked;});
    else if('svcchk' in d) change(()=>{S.services=t.checked?[...S.services,d.svcchk]:S.services.filter(x=>x!==d.svcchk);});
  });
  document.addEventListener('input',e=>{ if(e.target.id==='tree-q'){ treeQ=e.target.value; renderFil(); } });
  document.addEventListener('toggle',e=>{const k=e.target.dataset&&e.target.dataset.tree; if(k){ e.target.open?openCats.add(k):openCats.delete(k); }},true);

  document.addEventListener('click',e=>{
    const el=e.target.closest('button,[data-url]'); if(!el) return;
    const d=el.dataset;
    if('fav' in d){ e.preventDefault(); e.stopPropagation(); toggleFav(d.fav); return; }
    if('save' in d){ e.stopPropagation(); toggleSave(byUrl.get(d.save)||LIB.saved.find(s=>s.url===d.save)); return; }
    if('period' in d) return change(()=>{S.period=d.period;});
    if('cat' in d) return change(()=>{S.cat=d.cat;});
    if('sort' in d) return change(()=>{S.sort=d.sort;});
    if('imp' in d) return change(()=>{S.minImp=+d.imp;});
    if('svc' in d) return change(()=>{S.services=S.services.includes(d.svc)?S.services.filter(x=>x!==d.svc):[d.svc]; if(!wide.matches) closeDetail();});
    if('unset' in d){ const u=d.unset; return change(()=>{
      if(u==='minImp') S.minImp=0; else if(u==='tokyo') S.tokyo=false;
      else if(u==='q'){ S.q=''; qEl.value=''; }
      else if(u.startsWith('src:')) S.sources=S.sources.filter(x=>x!==u.slice(4));
      else if(u.startsWith('kind:')) S.kinds=S.kinds.filter(x=>x!==u.slice(5));
      else if(u.startsWith('svc:')) S.services=S.services.filter(x=>x!==u.slice(4)); }); }
    if('nav' in d) return move(+d.nav);
    if('closeDetail' in d) return closeDetail();
    if('closeDrawer' in d) return closeDrawer();
    if('ltab' in d){ libTab=d.ltab; return renderLib(); }
    if('gocat' in d){ closeDrawer(); return change(()=>{S.cat=d.gocat;}); }
    if('goart' in d){
      const a=byUrl.get(d.goart);
      if(!a){ window.open(d.goart,'_blank','noopener'); return; }
      closeDrawer();
      if(!L.includes(a)) change(()=>{S={...DEF,sort:S.sort,q:'',onlyNew:false}; qEl.value='';});
      return select(a.url,{scroll:true});
    }
    if('preset' in d){ const p=LIB.presets[+d.preset]; closeDrawer(); return change(()=>{S={...DEF,...p.filters,q:'',onlyNew:false}; qEl.value='';}); }
    if('delpreset' in d){ LIB.presets=LIB.presets.filter((_,i)=>i!==+d.delpreset); libChanged(); return renderLib(); }
    if(el.classList.contains('card')&&!e.target.closest('a')) select(d.url);
  });

  document.addEventListener('keydown',e=>{
    if(e.metaKey||e.ctrlKey||e.altKey) return;
    if(e.target.matches('input,textarea,select')){ if(e.key==='Escape') e.target.blur(); return; }
    if(document.querySelector('dialog[open]')) return;
    const a=selUrl&&byUrl.get(selUrl);
    switch(e.key){
      case 'j': case 'ArrowDown': if(drawer) return; e.preventDefault(); move(1); break;
      case 'k': case 'ArrowUp': if(drawer) return; e.preventDefault(); move(-1); break;
      case '/': e.preventDefault(); closeDrawer(); qEl.focus(); qEl.select(); break;
      case 'f': drawer==='fil'?closeDrawer():openDrawer('fil'); break;
      case 'l': drawer==='lib'?closeDrawer():openDrawer('lib'); break;
      case 'r': reload(); break;
      case 's': if(a) toggleSave(a); break;
      case 'o': if(a) window.open(a.url,'_blank','noopener'); break;
      case 'Escape': if(drawer) closeDrawer(); else closeDetail(); break;
      case '?': $('#dhelp').showModal(); break;
    }
  });

  // ヘッダーの高さを詳細ペインの貼り付け位置に使う
  const hd=$('#hd');
  const setHd=()=>document.documentElement.style.setProperty('--hd',hd.offsetHeight+'px');
  new ResizeObserver(setHd).observe(hd); setHd();
  wide.addEventListener('change',()=>{ $('#detail').classList.remove('open'); document.documentElement.classList.remove('lock'); renderDetail(); });

  renderAll(); renderSync();
  // AWS 上のサイトでだけ、設定とライブラリを取り直す
  if(D.api){
    $('#setbtn').hidden=false;
    get('/api/settings').then(r=>{setNotify(r); renderAll();}).catch(()=>{});
    pullLib();
  }
})();
</script>
</body>
</html>
"""
