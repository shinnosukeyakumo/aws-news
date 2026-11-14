"""保管した記事からニュースサイトの HTML を組み立てる。

1 ファイルで完結する静的ページにする。記事データはページに埋め込み、
タブ・サービス・ウォッチの切り替えはブラウザ側の JavaScript で行う。
S3 に置くだけで配信できる。通知設定と検証の状態だけは /api/* から取り直す。
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import SiteConfig


def render(articles: list[dict], site: SiteConfig, *,
           generated_at: datetime | None = None, api: bool = False,
           notify_services: list[str] | None = None) -> str:
    """記事の一覧（store.to_record の形）からページ全体の HTML を返す。

    api=True のときだけ「検証する」ボタンと「通知設定」を出す。受け口の /api/*
    は AWS 上のサイトにしか無いので、ローカルで書き出すページには出さない。
    """
    generated = (generated_at or datetime.now(timezone.utc)).isoformat()
    payload = {
        "generated_at": generated,
        "api": api,
        "notify": notify_services if notify_services is not None else list(site.notify_default),
        "watch": [{"name": w.name, "pattern": w.pattern} for w in site.watch],
        "articles": [{**a, "tags": site.normalize_tags(a.get("tags") or [])} for a in articles],
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
<style>
:root{
  --bg:#F2F2F7; --card:#FFFFFF; --ink:#1C1C1E; --sub:#55555B; --faint:#8E8E93; --rule:#E5E5EA;
  --accent:#0A6CDB; --new:#D7372C; --chip:#E9E9EE;
  --c-all:#1C1C1E; --c-new:#2F6E9E; --c-blog:#A8781E; --c-bell:#3C7D66; --c-verify:#6C5CA6;
  /* トップ記事の地。文字を白で載せるので、明暗どちらのモードでも濃い色に固定する */
  --k-all:#2C2C2E; --k-new:#22527A; --k-blog:#7A5612; --k-bell:#2B5E4C;
  --f:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP",system-ui,sans-serif;
  --f-head:var(--f);
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#000000; --card:#1C1C1E; --ink:#F2F2F7; --sub:#AEAEB2; --faint:#8E8E93; --rule:#2C2C2E;
  --accent:#4C9DFF; --new:#FF6B61; --chip:#2C2C2E;
  --c-all:#F2F2F7; --c-new:#7DB8E4; --c-blog:#E0B45E; --c-bell:#72BFA2; --c-verify:#A898E0;
  color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#000000; --card:#1C1C1E; --ink:#F2F2F7; --sub:#AEAEB2; --faint:#8E8E93; --rule:#2C2C2E;
  --accent:#4C9DFF; --new:#FF6B61; --chip:#2C2C2E;
  --c-all:#F2F2F7; --c-new:#7DB8E4; --c-blog:#E0B45E; --c-bell:#72BFA2; --c-verify:#A898E0;
  color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--f);font-size:15px;line-height:1.7;-webkit-text-size-adjust:100%;-webkit-font-smoothing:antialiased}
.wrap{max-width:600px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
button{font:inherit;color:inherit}

.mast{background:var(--card);border-bottom:1px solid var(--rule);padding-top:env(safe-area-inset-top,0px)}
.mast .wrap{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-block:14px 12px}
.mast .meta{display:flex;align-items:center;gap:12px}
.setbtn{border:1px solid var(--rule);background:none;border-radius:999px;padding:4px 12px;font-size:12.5px;font-weight:700;color:var(--accent);cursor:pointer;white-space:nowrap}
.mast h1{margin:0;font-family:var(--f-head);font-weight:700;font-size:22px;letter-spacing:0;line-height:1.1}
.upd{font-size:12px;color:var(--sub);font-variant-numeric:tabular-nums;white-space:nowrap}

header{position:sticky;top:0;z-index:5;background:var(--card);box-shadow:0 1px 0 var(--rule)}
header .wrap{padding-block:10px}
.tabs{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:5px}
.tab{--c:var(--c-all);min-width:0;border:1px solid color-mix(in srgb,var(--c) 35%,transparent);border-radius:8px;padding:6px 2px;font-size:12.5px;font-weight:700;line-height:1.25;cursor:pointer;white-space:nowrap;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;color:var(--c);background:transparent}
.tab .n{font-size:11px;font-weight:500;opacity:.75;font-variant-numeric:tabular-nums}
.tab[aria-selected="true"]{background:var(--c);border-color:var(--c);color:var(--card)}
.tab:focus-visible{outline:2px solid var(--c);outline-offset:2px}

main .wrap{padding-block:14px 40px;display:flex;flex-direction:column;gap:14px}
.tagbar{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;margin:0 calc(-1 * max(16px,env(safe-area-inset-left,0px)));padding:0 max(16px,env(safe-area-inset-left,0px))}
.tagbar::-webkit-scrollbar{display:none}
.chip{flex:none;border:0;background:var(--chip);color:var(--sub);border-radius:999px;padding:6px 12px;font-size:12.5px;font-weight:500;line-height:1.3;cursor:pointer;white-space:nowrap}
.chip .n{margin-left:5px;font-variant-numeric:tabular-nums;opacity:.7}
.chip[aria-pressed="true"]{background:var(--accent);color:var(--card)}
.chip:focus-visible,.tags button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.filter{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:13px;color:var(--sub)}
.filter b{color:var(--ink)}
.filter button{border:0;background:none;color:var(--accent);font-weight:700;font-size:13px;cursor:pointer;padding:4px 0;white-space:nowrap}

.lead{background:var(--card);border-radius:14px;overflow:hidden;box-shadow:0 1px 0 var(--rule)}
.lead a.cover{display:flex;flex-direction:column;justify-content:space-between;gap:14px;height:170px;padding:16px 18px;color:#F2F6FB;text-decoration:none;background:linear-gradient(135deg,var(--k),color-mix(in srgb,var(--k) 60%,#000))}
.lead .top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;font-size:12px;font-weight:700;letter-spacing:.06em}
.lead .svc{align-self:flex-end;font-family:var(--f-head);font-size:22px;font-weight:700;line-height:1.3;text-align:right;text-wrap:balance}
.lead .svc small{display:block;font-family:var(--f);font-size:11.5px;font-weight:700;letter-spacing:.1em;margin-top:6px;color:rgba(242,246,251,.8)}
.lead h2{font-family:var(--f-head);font-size:21px;font-weight:700;line-height:1.5;margin:0;text-wrap:balance}
.lead .body{padding:14px 18px 16px;display:flex;flex-direction:column;gap:8px}

.day{font-family:var(--f-head);font-size:15px;font-weight:700;margin:10px 2px -4px;letter-spacing:0;display:flex;align-items:center;gap:10px}
.day::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--rule),transparent)}
.group{background:var(--card);border-radius:14px;overflow:hidden;box-shadow:0 1px 0 var(--rule)}
.row{--c:var(--c-all);padding:15px 16px}
.row + .row{border-top:1px solid var(--rule)}
.kicker{display:flex;flex-wrap:wrap;gap:2px 8px;font-size:11.5px;line-height:1.5;color:var(--faint);margin:0;letter-spacing:.03em}
.kicker .cat{color:var(--c);font-weight:700}
.kicker .bell{color:var(--c-bell);font-weight:700}
.row h3{font-family:var(--f-head);font-size:16.5px;font-weight:700;line-height:1.5;margin:3px 0 5px;text-wrap:pretty}
.row h3 a,.lead h2 a{color:inherit;text-decoration:none}
.row h3 a:hover,.row h3 a:focus-visible,.lead h2 a:hover{text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:4px}
.sum{margin:0;font-size:13.5px;line-height:1.7;color:var(--sub)}
.row .sum{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.imp{margin:6px 0 0;font-size:13.5px;line-height:1.65}
.imp b{color:var(--c);font-weight:700;margin-right:6px}
.tags{display:flex;flex-wrap:wrap;gap:4px 10px;margin-top:6px}
.tags button{border:0;background:none;padding:0;font-size:12px;color:var(--faint);cursor:pointer}
.tags button::before{content:"#"}
.tags button[aria-pressed="true"]{color:var(--accent);font-weight:700}
.foot{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-top:6px}
.foot .tags{margin-top:0}
.vbtn,.vstat{flex:none;font-size:12px;font-weight:700;border-radius:999px;padding:3px 10px;white-space:nowrap}
.vbtn{border:1px solid var(--accent);background:none;color:var(--accent);cursor:pointer}
.vbtn:disabled{opacity:.5;cursor:default}
.vstat{background:color-mix(in srgb,var(--accent) 12%,transparent);color:var(--accent)}
.vstat[data-s="needs-real"],.vstat[data-s="failed"]{background:color-mix(in srgb,var(--new) 14%,transparent);color:var(--new)}
.empty{background:var(--card);border-radius:14px;padding:22px 16px;color:var(--sub);font-size:14px;margin:0}
footer{font-size:12px;color:var(--faint);text-align:center;padding-block:0 28px;letter-spacing:.04em}

/* ウォッチ: タブを問わず、ウォッチ語に当たった記事の見出しだけを新しい順に並べる */
.watch{background:var(--card);border-radius:14px;overflow:hidden;box-shadow:0 1px 0 var(--rule);border-top:3px solid var(--accent)}
.watch-h{display:flex;align-items:baseline;justify-content:space-between;gap:10px;padding:12px 16px 4px}
.watch-h h2{margin:0;font-family:var(--f-head);font-size:16px;font-weight:700;letter-spacing:0}
.watch-h span{font-size:12px;color:var(--faint);font-variant-numeric:tabular-nums}
.watch-h span b{color:var(--accent)}
.wchips{display:flex;gap:6px;flex-wrap:wrap;padding:6px 16px 8px}
.wchips .chip{padding:4px 10px;font-size:12px}
.witem{padding:9px 16px;border-top:1px solid var(--rule)}
.witem a{color:var(--ink);text-decoration:none;font-size:14px;font-weight:500;line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.witem a:hover{text-decoration:underline;text-underline-offset:3px}
.witem p{margin:1px 0 0;font-size:11.5px;color:var(--faint);display:flex;flex-wrap:wrap;gap:0 8px}
.witem p .w{color:var(--accent);font-weight:700}
.witem p .new{color:var(--card);background:var(--new);border-radius:3px;padding:0 5px;font-weight:700;letter-spacing:.1em}
.watch .more{display:block;width:100%;border:0;border-top:1px solid var(--rule);background:none;color:var(--accent);font-weight:700;font-size:13px;padding:10px;cursor:pointer}
.watch-side{display:none}

.side{display:none}
.side-h{margin:6px 2px 0;font-family:var(--f-head);font-weight:700;font-size:14px;letter-spacing:0;color:var(--sub)}
.col{display:flex;flex-direction:column;gap:14px;min-width:0}
#feed{display:flex;flex-direction:column;gap:14px}
@media (min-width:960px){
  .wrap{max-width:1180px}
  header{display:none}
  .mast .wrap{padding-block:22px 18px}
  .mast h1{font-size:34px}
  main .wrap{display:grid;grid-template-columns:236px minmax(0,1fr);gap:32px;align-items:start;padding-block:28px 64px}
  .side{display:flex;flex-direction:column;gap:12px;position:sticky;top:20px;max-height:calc(100vh - 40px);overflow-y:auto;scrollbar-width:thin}
  .side>*{flex-shrink:0}
  .side .tabs{grid-template-columns:1fr;gap:5px}
  .side .tab{justify-content:space-between;padding:11px 14px;font-size:14px;border-radius:10px}
  .side .tagbar{flex-wrap:wrap;overflow:visible;margin:0;padding:0}
  .tagbar-m{display:none}
  .watch-side{display:block}
  .watch-main{display:none}
  .col{gap:20px}
  .lead{display:grid;grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);grid-template-rows:340px}
  .lead a.cover{height:100%;padding:20px 22px}
  .lead .svc{font-size:28px}
  .lead .body{padding:26px 28px;justify-content:center;gap:10px;overflow:hidden}
  .lead .body>*{flex-shrink:0}   /* 縮めると行の途中で切れる。行数は line-clamp で抑える */
  .lead h2,.lead .sum,.lead .imp{display:-webkit-box;-webkit-box-orient:vertical;overflow:hidden}
  .lead h2{-webkit-line-clamp:3;font-size:25px}
  .lead .sum{-webkit-line-clamp:3;font-size:14.5px}
  .lead .imp{-webkit-line-clamp:2}
  .lead .tags{flex-wrap:nowrap;overflow:hidden}
  .day{font-size:17px;margin:14px 2px -2px}
  .group{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;background:none;box-shadow:none;border-radius:0;overflow:visible}
  .group .row{background:var(--card);border-radius:14px;box-shadow:0 1px 0 var(--rule);padding:18px}
  .row + .row{border-top:0}
  .filter{font-size:14px}
}

/* 検証のタブ */
.vcard{background:var(--card);border-radius:14px;box-shadow:0 1px 0 var(--rule);padding:14px 16px;display:flex;flex-direction:column;gap:6px}
.vcard h3{margin:0;font-size:15.5px;font-weight:700;line-height:1.5}
.vcard h3 a{color:inherit;text-decoration:none}
.vcard .st{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;font-size:12px;color:var(--faint)}
.vcard .msg{margin:0;font-size:13px;color:var(--sub)}
.vcard .acts{display:flex;gap:8px;flex-wrap:wrap}
.vcard .acts button{border:1px solid var(--accent);background:none;color:var(--accent);border-radius:8px;padding:5px 12px;font-size:13px;font-weight:700;cursor:pointer}
.res{font-size:11.5px;font-weight:700;border-radius:4px;padding:1px 7px;letter-spacing:.04em;background:var(--chip);color:var(--sub)}
.res[data-r="PASS"]{background:color-mix(in srgb,var(--c-bell) 16%,transparent);color:var(--c-bell)}
.res[data-r="FAIL"],.res[data-r="ERROR"]{background:color-mix(in srgb,var(--new) 14%,transparent);color:var(--new)}
.vhead{font-size:13px;color:var(--sub);margin:0 2px}

/* ダイアログ（通知設定・記録と下書き） */
dialog{border:0;border-radius:16px;padding:0;width:min(560px,calc(100vw - 32px));max-height:calc(100vh - 48px);background:var(--card);color:var(--ink);box-shadow:0 10px 40px rgba(0,0,0,.3)}
dialog::backdrop{background:rgba(0,0,0,.45)}
.dlg{display:flex;flex-direction:column;max-height:calc(100vh - 48px)}
.dlg-h{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:14px 16px;border-bottom:1px solid var(--rule)}
.dlg-h h2{margin:0;font-size:16px;font-weight:700}
.dlg-b{padding:12px 16px;overflow-y:auto;display:flex;flex-direction:column;gap:8px}
.dlg-f{display:flex;justify-content:flex-end;gap:8px;padding:12px 16px;border-top:1px solid var(--rule)}
.dlg-f button,.dlg-h button{border:0;border-radius:8px;padding:7px 14px;font-size:14px;font-weight:700;cursor:pointer;background:var(--chip)}
.dlg-f .pri{background:var(--accent);color:#fff}
.dlg-b input[type=search]{width:100%;font:inherit;font-size:14px;padding:8px 10px;border:1px solid var(--rule);border-radius:8px;background:var(--bg);color:var(--ink)}
.dlg-b .hint{margin:0;font-size:12.5px;color:var(--sub)}
.svcs{display:flex;flex-direction:column}
.svcs label{display:flex;align-items:center;gap:10px;padding:8px 2px;border-top:1px solid var(--rule);font-size:14px;cursor:pointer}
.svcs label .n{margin-left:auto;font-size:12px;color:var(--faint);font-variant-numeric:tabular-nums}
.svcs input{width:18px;height:18px;accent-color:var(--accent);flex:none}
.doc{margin:0;white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;line-height:1.7}
.doc-tabs{display:flex;gap:6px}
.doc-tabs .chip[aria-pressed="true"]{background:var(--accent);color:#fff}
@media (prefers-reduced-motion:no-preference){.tab,.chip{transition:background-color .15s,color .15s}}
</style>
</head>
<body>
<section class="mast"><div class="wrap"><h1>__TITLE__</h1><div class="meta"><span class="upd" id="upd"></span><button class="setbtn" id="setbtn" hidden>通知設定</button></div></div></section>

<header><div class="wrap">
  <nav class="tabs" role="tablist" aria-label="表示する記事"></nav>
</div></header>

<main><div class="wrap">
  <aside class="side" aria-label="絞り込み">
    <nav class="tabs" role="tablist" aria-label="表示する記事"></nav>
    <section class="watch watch-side" aria-label="ウォッチ"></section>
    <p class="side-h">サービス</p>
    <div class="tagbar" aria-label="サービスで絞り込む"></div>
  </aside>
  <div class="col">
    <div class="tagbar tagbar-m" aria-label="サービスで絞り込む"></div>
    <div id="feed"></div>
  </div>
</div></main>
<footer><div class="wrap">「通知」の印は Slack に通知する対象のサービスです。見出しと要約は AI による自動生成のため、原文もご確認ください。</div></footer>

<dialog id="dset" aria-labelledby="dset-h"><form method="dialog" class="dlg">
  <div class="dlg-h"><h2 id="dset-h">通知するサービス</h2></div>
  <div class="dlg-b">
    <p class="hint">チェックしたサービスの新着だけを Slack に送ります。一覧には全部の記事が出ます。</p>
    <input type="search" id="dset-q" placeholder="サービス名で絞り込む" autocomplete="off">
    <div class="svcs" id="dset-list"></div>
  </div>
  <div class="dlg-f"><button value="cancel">やめる</button><button class="pri" id="dset-save" value="save">保存</button></div>
</form></dialog>

<dialog id="ddoc" aria-labelledby="ddoc-h"><form method="dialog" class="dlg">
  <div class="dlg-h"><h2 id="ddoc-h"></h2><button value="close">閉じる</button></div>
  <div class="dlg-b"><div class="doc-tabs" id="ddoc-tabs"></div><pre class="doc" id="ddoc-body"></pre></div>
  <div class="dlg-f"><button type="button" id="ddoc-copy">コピー</button></div>
</form></dialog>

<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
  const D=JSON.parse(document.getElementById('data').textContent);
  // 情報源。ここに無いエージェントの記事（AWS に絞る前の LLM ベンダー分など）は出さない
  const SRC={'aws-whatsnew':{name:"What's New",tab:'新機能',c:'--c-new',k:'new'},'aws-ai':{name:'AI ブログ',tab:'AI ブログ',c:'--c-blog',k:'blog'}};
  const TABS=[['all','すべて','--c-all'],['aws-whatsnew','新機能','--c-new'],['aws-ai','AI ブログ','--c-blog'],['bell','通知対象','--c-bell'],['verify','検証','--c-verify']];
  const tz={timeZone:'Asia/Tokyo'};
  const fDay=new Intl.DateTimeFormat('ja-JP',{...tz,month:'long',day:'numeric',weekday:'short'});
  const fMd=new Intl.DateTimeFormat('ja-JP',{...tz,month:'numeric',day:'numeric'});
  const fUpd=new Intl.DateTimeFormat('ja-JP',{...tz,month:'numeric',day:'numeric',hour:'numeric',minute:'2-digit'});
  const dayKey=iso=>new Intl.DateTimeFormat('en-CA',tz).format(new Date(iso));
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const A=D.articles.filter(a=>SRC[a.agent_key]);
  document.getElementById('upd').textContent=fUpd.format(new Date(D.generated_at))+' 更新';

  const feed=document.getElementById('feed');
  let cur='all', curTags=[];
  try{const s=localStorage.getItem('awsnews-tab'); if(TABS.some(t=>t[0]===s)) cur=s;}catch(e){}
  const pub=a=>a.published_at||a.sort_at||D.generated_at;

  // 通知するサービス。ページに埋め込んだ値で描き、/api/settings で取り直す
  let notifySet=new Set((D.notify||[]).map(s=>s.toLowerCase()));
  const isBell=a=>(a.tags||[]).some(t=>notifySet.has(t.toLowerCase()));
  const hasTag=a=>curTags.every(t=>(a.tags||[]).includes(t));
  const inTab=a=>cur==='all'||(cur==='bell'?isBell(a):a.agent_key===cur);

  // 検証の状態。approved はボタンが書き、その先は agentcore-playground が書く
  const VS={approved:'承認済み',picked:'検証中',done:'検証済み','needs-real':'要実機',failed:'検証失敗'};
  // 初期表示はページに埋め込んだ状態から作り、/api/verify で取り直す
  let V=A.filter(a=>a.verify).map(a=>({url:a.url,title_ja:a.title_ja,source_label:a.source_label,status:a.verify}));
  const vOf=a=>V.find(r=>r.url===a.url);

  // ウォッチ: ウォッチ語がタグか題名に当たった記事。タブは問わない
  const W=(D.watch||[]).map(w=>({...w,re:new RegExp(w.pattern,'i')}));
  const watchOf=a=>W.filter(w=>[a.title_ja,a.title_original,...(a.tags||[])].some(x=>w.re.test(x||''))).map(w=>w.name);
  const watched=A.map(a=>({a,w:watchOf(a)})).filter(x=>x.w.length).sort((x,y)=>pub(y.a).localeCompare(pub(x.a)));
  // 新着は前回ひらいた時刻より後の記事。初めて開いたときは更新の 24 時間前を前回とみなす
  let seen=new Date(new Date(D.generated_at).getTime()-864e5).toISOString();
  try{const v=localStorage.getItem('awsnews-seen'); if(v) seen=v;}catch(e){}
  addEventListener('pagehide',()=>{try{localStorage.setItem('awsnews-seen',new Date().toISOString())}catch(e){}});
  const isNew=a=>new Date(pub(a))>new Date(seen);
  let wSel='', wOpen=false;
  function watchHtml(limit){
    const list=watched.filter(x=>!wSel||x.w.includes(wSel));
    const nNew=list.filter(x=>isNew(x.a)).length;
    const cnt=n=>watched.filter(x=>x.w.includes(n)).length;
    const show=wOpen?list:list.slice(0,limit);
    return `<div class="watch-h"><h2>ウォッチ</h2><span>${list.length} 件${nNew?` ・ 新着 <b>${nNew}</b>`:''}</span></div>
      <div class="wchips">${W.map(w=>`<button class="chip" data-watch="${esc(w.name)}" aria-pressed="${wSel===w.name}">${esc(w.name)}<span class="n">${cnt(w.name)}</span></button>`).join('')}</div>
      ${show.map(({a,w})=>`<div class="witem"><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title_ja)}</a>
        <p>${isNew(a)?'<span class="new">新</span>':''}<span>${fMd.format(new Date(pub(a)))}</span><span class="w">${w.join(' ・ ')}</span><span>${SRC[a.agent_key].name}</span></p></div>`).join('')}
      ${list.length>limit?`<button class="more" data-wmore>${wOpen?'閉じる':`残り ${list.length-limit} 件を表示`}</button>`:''}`;
  }
  function renderWatch(){
    document.querySelectorAll('.watch-side').forEach(el=>el.innerHTML=watched.length?watchHtml(8):'');
  }
  function renderTabs(){
    const tabsHtml=TABS.map(([k,label,c])=>{
      const n=k==='verify'?V.length:A.filter(a=>(k==='all'||(k==='bell'?isBell(a):a.agent_key===k))&&hasTag(a)).length;
      return `<button class="tab" role="tab" data-k="${k}" style="--c:var(${c})" aria-selected="${k===cur}">${label}<span class="n">${n}</span></button>`;
    }).join('');
    document.querySelectorAll('.tabs').forEach(el=>el.innerHTML=tabsHtml);
  }
  function renderTagbar(){
    const pool=cur==='verify'?[]:A.filter(a=>inTab(a)&&hasTag(a));
    const c=new Map(); pool.forEach(a=>(a.tags||[]).forEach(t=>c.set(t,(c.get(t)||0)+1)));
    let list=[...c].filter(([t,n])=>!curTags.includes(t)&&n>=(curTags.length?1:2)).sort((x,y)=>y[1]-x[1]||x[0].localeCompare(y[0],'ja')).slice(0,24);
    list=[...curTags.map(t=>[t,c.get(t)||0]),...list];
    const tagHtml=list.map(([t,n])=>`<button class="chip" data-tag="${esc(t)}" aria-pressed="${curTags.includes(t)}">${esc(t)}<span class="n">${n}</span></button>`).join('');
    document.querySelectorAll('.tagbar').forEach(el=>el.innerHTML=tagHtml);
  }
  const kicker=a=>`<p class="kicker"><span class="cat">${SRC[a.agent_key].name}</span>${isBell(a)?'<span class="bell">通知</span>':''}${isNew(a)?'<span class="bell" style="color:var(--new)">新着</span>':''}</p>`;
  const tagList=a=>`<div class="tags">${(a.tags||[]).slice(0,3).map(t=>`<button data-tag="${esc(t)}" aria-pressed="${curTags.includes(t)}">${esc(t)}</button>`).join('')}</div>`;
  const vbox=a=>{
    if(!D.api) return '';
    const r=vOf(a);
    return r?`<span class="vstat" data-s="${esc(r.status)}">${esc(VS[r.status]||r.status)}</span>`:`<button class="vbtn" data-verify="${A.indexOf(a)}">検証する</button>`;
  };
  const foot=a=>`<div class="foot">${tagList(a)}${vbox(a)}</div>`;
  const imp=a=>`<p class="imp"><b>効き目</b>${esc(a.impact)}</p>`;
  const col=a=>`--c:var(${SRC[a.agent_key].c})`;
  function lead(a){
    const k=cur==='all'?'all':cur==='bell'?'bell':SRC[a.agent_key].k;
    return `<article class="lead" style="${col(a)};--k:var(--k-${k})">
      <a class="cover" href="${esc(a.url)}" target="_blank" rel="noopener">
        <div class="top"><span>${SRC[a.agent_key].name}</span><span>${fDay.format(new Date(pub(a)))}</span></div>
        <div class="svc">${esc((a.tags||[]).slice(0,2).join(' / ')||SRC[a.agent_key].name)}${isBell(a)?'<small>通知対象</small>':''}</div>
      </a>
      <div class="body"><h2><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title_ja)}</a></h2>
        <p class="sum">${esc(a.summary)}</p>${imp(a)}${foot(a)}</div></article>`;
  }
  function row(a){
    return `<article class="row" style="${col(a)}">${kicker(a)}
      <h3><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title_ja)}</a></h3>
      <p class="sum">${esc(a.summary)}</p>${imp(a)}${foot(a)}</article>`;
  }
  function renderVerify(){
    if(!V.length) return `<p class="empty">まだ検証に回した記事はありません。記事の「検証する」から回せます。</p>`;
    return `<p class="vhead">承認すると agentcore-playground が AWS Emulator で検証し、記録と下書きを書き戻します。</p>`+V.map(r=>`<article class="vcard">
      <h3><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.title_ja)}</a></h3>
      <div class="st"><span class="vstat" data-s="${esc(r.status)}">${esc(VS[r.status]||r.status)}</span>${r.result?`<span class="res" data-r="${esc(r.result)}">${esc(r.result)}</span>`:''}${r.approved_at?`<span>${fMd.format(new Date(r.approved_at))} 承認</span>`:''}${r.done_at?`<span>${fMd.format(new Date(r.done_at))} 完了</span>`:''}</div>
      ${r.message?`<p class="msg">${esc(r.message)}</p>`:''}
      ${r.id&&(r.status==='done'||r.status==='needs-real'||r.status==='failed')?`<div class="acts"><button data-doc="${esc(r.id)}" data-part="note_md">記録を読む</button>${r.has_draft?`<button data-doc="${esc(r.id)}" data-part="draft_md">下書きを読む</button>`:''}</div>`:''}
    </article>`).join('');
  }
  function render(){
    if(cur==='verify'){ feed.innerHTML=renderVerify(); return; }
    const items=A.filter(a=>inTab(a)&&hasTag(a)).sort((x,y)=>pub(y).localeCompare(pub(x)));
    let h='';
    // スマホでは「すべて」の一番上に置く。PC では左の列に常に出す
    if(cur==='all'&&!curTags.length&&watched.length) h+=`<section class="watch watch-main" aria-label="ウォッチ">${watchHtml(5)}</section>`;
    const label=TABS.find(t=>t[0]===cur)[1];
    if(curTags.length) h+=`<div class="filter"><span><b>${label}</b> の中で ${curTags.map(t=>`#${esc(t)}`).join(' ')} ・ ${items.length} 件</span><button data-clear>解除</button></div>`;
    if(!items.length) h+=`<p class="empty">${cur==='bell'?'通知するサービスの記事はまだありません。右上の「通知設定」でサービスを選べます。':'この条件の記事はまだありません。'}</p>`;
    else{
      // トップ記事は通知対象の最新。無ければ全体の最新
      const top=items.find(isBell)||items[0];
      h+=lead(top);
      let last='',open=false;
      for(const a of items){ if(a===top) continue;
        const k=dayKey(pub(a));
        if(k!==last){ if(open) h+='</div>'; h+=`<h2 class="day">${fDay.format(new Date(pub(a)))}</h2><div class="group">`; last=k; open=true; }
        h+=row(a);
      }
      if(open) h+='</div>';
    }
    feed.innerHTML=h;
  }
  function renderAll(){renderTabs();renderWatch();renderTagbar();render();}

  // CloudFront の OAC 経由で Lambda に POST するときは、本文の SHA-256 をヘッダーで渡す決まり
  async function post(path,obj){
    const body=JSON.stringify(obj);
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(body));
    const hex=[...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');
    const res=await fetch(path,{method:'POST',headers:{'content-type':'application/json','x-amz-content-sha256':hex},body});
    if(res.status!==200&&res.status!==409) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }
  async function get(path){
    const res=await fetch(path,{cache:'no-store'});
    if(!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  // 通知設定
  const dset=document.getElementById('dset'), dlist=document.getElementById('dset-list'), dq=document.getElementById('dset-q');
  let draftSet=new Set();
  function renderSettings(){
    const c=new Map(); A.forEach(a=>(a.tags||[]).forEach(t=>c.set(t,(c.get(t)||0)+1)));
    // 保存済みで直近の記事に出てこないサービスも残す
    const names=new Map([...c.keys()].map(t=>[t.toLowerCase(),t]));
    draftSet.forEach(s=>{ if(!names.has(s)) names.set(s,(D.notify||[]).find(x=>x.toLowerCase()===s)||s); });
    const q=dq.value.trim().toLowerCase();
    const list=[...names].filter(([k])=>!q||k.includes(q))
      .sort((x,y)=>draftSet.has(y[0])-draftSet.has(x[0])||(c.get(y[1])||0)-(c.get(x[1])||0)||x[1].localeCompare(y[1],'ja'));
    dlist.innerHTML=list.map(([k,t])=>`<label><input type="checkbox" data-svc="${esc(k)}" data-name="${esc(t)}" ${draftSet.has(k)?'checked':''}>${esc(t)}<span class="n">${c.get(t)||0} 件</span></label>`).join('')||'<p class="hint">当てはまるサービスがありません。</p>';
  }
  document.getElementById('setbtn').addEventListener('click',()=>{draftSet=new Set(notifySet); dq.value=''; renderSettings(); dset.showModal();});
  dq.addEventListener('input',renderSettings);
  dlist.addEventListener('change',e=>{const k=e.target.dataset.svc; if(!k) return; e.target.checked?draftSet.add(k):draftSet.delete(k);});
  dset.addEventListener('close',async()=>{
    if(dset.returnValue!=='save') return;
    const named=new Map([...dlist.querySelectorAll('[data-svc]')].map(i=>[i.dataset.svc,i.dataset.name]));
    A.forEach(a=>(a.tags||[]).forEach(t=>named.has(t.toLowerCase())||named.set(t.toLowerCase(),t)));
    (D.notify||[]).forEach(t=>named.has(t.toLowerCase())||named.set(t.toLowerCase(),t));
    const services=[...draftSet].map(k=>named.get(k)||k);
    try{ const r=await post('/api/settings',{services}); D.notify=r.services; notifySet=new Set(r.services.map(s=>s.toLowerCase())); renderAll(); }
    catch(err){ alert(`保存できませんでした（${err.message}）`); }
  });

  // 検証の記録と下書き
  const ddoc=document.getElementById('ddoc'), dbody=document.getElementById('ddoc-body'), dtabs=document.getElementById('ddoc-tabs');
  let docItem=null, docPart='note_md';
  function renderDoc(){
    dtabs.innerHTML=[['note_md','検証の記録'],['draft_md','下書き']].filter(([p])=>docItem[p]).map(([p,l])=>`<button type="button" class="chip" data-part-sel="${p}" aria-pressed="${p===docPart}">${l}</button>`).join('');
    dbody.textContent=docItem[docPart]||'まだ書かれていません。';
  }
  async function openDoc(id,part){
    document.getElementById('ddoc-h').textContent='読み込み中';
    dbody.textContent=''; dtabs.innerHTML=''; ddoc.showModal();
    try{ docItem=await get(`/api/verify/${encodeURIComponent(id)}`); docPart=part; document.getElementById('ddoc-h').textContent=docItem.title_ja||''; renderDoc(); }
    catch(err){ dbody.textContent=`読み込めませんでした（${err.message}）`; }
  }
  dtabs.addEventListener('click',e=>{const b=e.target.closest('[data-part-sel]'); if(b){docPart=b.dataset.partSel; renderDoc();}});
  document.getElementById('ddoc-copy').addEventListener('click',e=>{
    navigator.clipboard.writeText(dbody.textContent).then(()=>{e.target.textContent='コピーしました'; setTimeout(()=>e.target.textContent='コピー',1500);});
  });

  document.addEventListener('click',e=>{
    const v=e.target.closest('[data-verify]');
    if(v){
      const a=A[+v.dataset.verify];
      if(!confirm(`「${a.title_ja}」を検証に回しますか？`)) return;
      v.disabled=true; v.textContent='送信中';
      post('/api/verify',{pk:a.agent_key,sk:a.url})
        .then(r=>{V=[{id:r.id,url:a.url,title_ja:a.title_ja,source_label:a.source_label,status:r.status,approved_at:new Date().toISOString()},...V.filter(x=>x.url!==a.url)]; renderTabs(); render();})
        .catch(err=>{v.disabled=false; v.textContent='検証する'; alert(`送れませんでした（${err.message}）`);});
      return;
    }
    const d=e.target.closest('[data-doc]');
    if(d){ openDoc(d.dataset.doc,d.dataset.part); return; }
    const tab=e.target.closest('.tab');
    if(tab){ cur=tab.dataset.k; try{localStorage.setItem('awsnews-tab',cur)}catch(err){} renderAll(); window.scrollTo({top:0}); return; }
    const t=e.target.closest('[data-tag]'), c=e.target.closest('[data-clear]');
    if(t||c){ if(c) curTags=[]; else {const v=t.dataset.tag; curTags=curTags.includes(v)?curTags.filter(x=>x!==v):[...curTags,v];} renderAll(); window.scrollTo({top:0}); return; }
    const w=e.target.closest('[data-watch]'), m=e.target.closest('[data-wmore]');
    if(w){ wSel=wSel===w.dataset.watch?'':w.dataset.watch; renderWatch(); render(); }
    else if(m){ wOpen=!wOpen; renderWatch(); render(); }
  });
  renderAll();
  // AWS 上のサイトでだけ、設定と検証の状態を取り直す
  if(D.api){
    document.getElementById('setbtn').hidden=false;
    get('/api/settings').then(r=>{D.notify=r.services; notifySet=new Set(r.services.map(s=>s.toLowerCase())); renderAll();}).catch(()=>{});
    get('/api/verify').then(r=>{V=r; renderAll();}).catch(()=>{});
  }
})();
</script>
</body>
</html>
"""
