"""保管した記事からニュースサイトの HTML を組み立てる。

1 ファイルで完結する静的ページにする。記事データはページに埋め込み、
タブ・タグ・見張りの切り替えはブラウザ側の JavaScript で行う。
サーバー側の処理が要らないので、S3 に置くだけで配信できる。
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import SiteConfig


def render(articles: list[dict], site: SiteConfig, *,
           generated_at: datetime | None = None) -> str:
    """記事の一覧（store.to_record の形）からページ全体の HTML を返す。"""
    generated = (generated_at or datetime.now(timezone.utc)).isoformat()
    payload = {
        "generated_at": generated,
        "min_score": site.min_score,
        "watch": [{"name": w.name, "pattern": w.pattern} for w in site.watch],
        "articles": [{**a, "tags": site.normalize_tags(a.get("tags") or [])} for a in articles],
    }
    # </script> で埋め込みが途切れないようにする
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(site.title)
    return (
        _TEMPLATE.replace("__TITLE__", title)
        .replace("__MIN__", str(site.min_score))
        .replace("__DATA__", data)
    )


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
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Shippori+Mincho+B1:wght@700;800&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap">
<style>
:root{
  --bg:#EEF2F6; --card:#FBFCFD; --ink:#16213A; --sub:#4E5A70; --faint:#808A9C; --rule:#DCE3EB;
  --accent:#1A7F86; --new:#A93A4E; --chip:#E3E9F0;
  --c-all:#16213A; --c-impl:#2F6E9E; --c-aws:#A8781E; --c-case:#3C7D66; --c-trend:#6C5CA6; --c-model:#A93A4E;
  /* トップ記事の地。文字を白で載せるので、明暗どちらのモードでも濃い色に固定する */
  --k-all:#1D2A47; --k-impl:#22527A; --k-aws:#7A5612; --k-case:#2B5E4C; --k-trend:#4E4287; --k-model:#7E2A3B;
  --f-head:"Shippori Mincho B1","Hiragino Mincho ProN","Yu Mincho",serif;
  --f:"Zen Kaku Gothic New","Hiragino Sans","Hiragino Kaku Gothic ProN",system-ui,sans-serif;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#0B1120; --card:#121A2C; --ink:#E8EEF6; --sub:#A5B1C4; --faint:#76829A; --rule:#222D44;
  --accent:#62C7CC; --new:#E07A8C; --chip:#1A2438;
  --c-all:#E8EEF6; --c-impl:#7DB8E4; --c-aws:#E0B45E; --c-case:#72BFA2; --c-trend:#A898E0; --c-model:#E07A8C;
  color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0B1120; --card:#121A2C; --ink:#E8EEF6; --sub:#A5B1C4; --faint:#76829A; --rule:#222D44;
  --accent:#62C7CC; --new:#E07A8C; --chip:#1A2438;
  --c-all:#E8EEF6; --c-impl:#7DB8E4; --c-aws:#E0B45E; --c-case:#72BFA2; --c-trend:#A898E0; --c-model:#E07A8C;
  color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--f);font-size:15px;line-height:1.7;-webkit-text-size-adjust:100%;-webkit-font-smoothing:antialiased}
.wrap{max-width:600px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
button{font:inherit;color:inherit}

.mast{background:var(--card);border-bottom:1px solid var(--rule);padding-top:env(safe-area-inset-top,0px)}
.mast .wrap{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding-block:14px 12px}
.mast h1{margin:0;font-family:var(--f-head);font-weight:800;font-size:26px;letter-spacing:.12em;line-height:1.1}
.upd{font-size:12px;color:var(--sub);font-variant-numeric:tabular-nums;white-space:nowrap}

header{position:sticky;top:0;z-index:5;background:var(--card);box-shadow:0 1px 0 var(--rule)}
header .wrap{padding-block:10px}
.tabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}
.tab{--c:var(--c-all);min-width:0;border:1px solid color-mix(in srgb,var(--c) 35%,transparent);border-radius:8px;padding:8px 4px;font-size:13.5px;font-weight:700;line-height:1.2;cursor:pointer;white-space:nowrap;display:flex;align-items:center;justify-content:center;gap:6px;color:var(--c);background:transparent}
.tab .n{font-size:11.5px;font-weight:500;opacity:.75;font-variant-numeric:tabular-nums}
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
.lead .big{align-self:flex-end;font-family:var(--f-head);font-size:58px;font-weight:800;line-height:.9;font-variant-numeric:tabular-nums;text-align:right}
.lead .big small{display:block;font-family:var(--f);font-size:11.5px;font-weight:700;letter-spacing:.14em;margin-top:8px;color:rgba(242,246,251,.8)}
.lead .big small.must{display:inline-block;background:#fff;color:#16213A;padding:1px 8px;border-radius:4px;letter-spacing:.2em}
.lead h2{font-family:var(--f-head);font-size:21px;font-weight:800;line-height:1.5;margin:0;text-wrap:balance}
.lead .body{padding:14px 18px 16px;display:flex;flex-direction:column;gap:8px}

.day{font-family:var(--f-head);font-size:15px;font-weight:800;margin:10px 2px -4px;letter-spacing:.08em;display:flex;align-items:center;gap:10px}
.day::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--rule),transparent)}
.group{background:var(--card);border-radius:14px;overflow:hidden;box-shadow:0 1px 0 var(--rule)}
.row{--c:var(--c-all);display:grid;grid-template-columns:minmax(0,1fr) 58px;gap:14px;padding:15px 16px}
.row + .row{border-top:1px solid var(--rule)}
.kicker{display:flex;flex-wrap:wrap;gap:2px 8px;font-size:11.5px;line-height:1.5;color:var(--faint);margin:0;letter-spacing:.03em}
.kicker .cat{color:var(--c);font-weight:700}
.row h3{font-family:var(--f-head);font-size:16.5px;font-weight:800;line-height:1.5;margin:3px 0 5px;text-wrap:pretty}
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
.score{width:58px;height:58px;margin-top:4px;border:1.5px solid var(--c);border-radius:8px;color:var(--c);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;background:color-mix(in srgb,var(--c) 8%,transparent)}
.score b{font-family:var(--f-head);font-size:23px;font-weight:800;line-height:1;font-variant-numeric:tabular-nums}
.score span{font-size:9.5px;font-weight:700;letter-spacing:.08em}
.score.must{background:var(--c);color:var(--card);box-shadow:0 0 0 3px color-mix(in srgb,var(--c) 22%,transparent)}

details.skipped{background:var(--card);border-radius:14px;overflow:hidden;box-shadow:0 1px 0 var(--rule)}
details.skipped summary{cursor:pointer;list-style:none;padding:14px 16px;display:flex;justify-content:space-between;align-items:baseline;gap:10px;font-family:var(--f-head);font-size:15px;font-weight:800}
details.skipped summary::-webkit-details-marker{display:none}
details.skipped summary span{font-family:var(--f);color:var(--faint);font-weight:500;font-size:12px}
details.skipped summary:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.skip{--c:var(--c-all);display:grid;grid-template-columns:30px minmax(0,1fr);gap:10px;padding:11px 16px;border-top:1px solid var(--rule)}
.skip b{font-family:var(--f-head);font-size:15px;font-weight:800;color:var(--faint);font-variant-numeric:tabular-nums;text-align:right;line-height:1.5}
.skip a{color:var(--ink);text-decoration:none;font-size:14px;line-height:1.55;display:block}
.skip p{margin:2px 0 0;font-size:12px;color:var(--faint)}
.skip .cat{color:var(--c);font-weight:700}
.empty{background:var(--card);border-radius:14px;padding:22px 16px;color:var(--sub);font-size:14px;margin:0}
footer{font-size:12px;color:var(--faint);text-align:center;padding-block:0 28px;letter-spacing:.04em}

/* 見張り: 点数とタブを問わず、見張る言葉に当たった記事の見出しだけを新しい順に並べる */
.watch{background:var(--card);border-radius:14px;overflow:hidden;box-shadow:0 1px 0 var(--rule);border-top:3px solid var(--accent)}
.watch-h{display:flex;align-items:baseline;justify-content:space-between;gap:10px;padding:12px 16px 4px}
.watch-h h2{margin:0;font-family:var(--f-head);font-size:16px;font-weight:800;letter-spacing:.12em}
.watch-h span{font-size:12px;color:var(--faint);font-variant-numeric:tabular-nums}
.watch-h span b{color:var(--accent)}
.wchips{display:flex;gap:6px;flex-wrap:wrap;padding:6px 16px 8px}
.wchips .chip{padding:4px 10px;font-size:12px}
.witem{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:10px;align-items:start;padding:9px 16px;border-top:1px solid var(--rule)}
.witem a{color:var(--ink);text-decoration:none;font-size:14px;font-weight:500;line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.witem a:hover{text-decoration:underline;text-underline-offset:3px}
.witem p{margin:1px 0 0;font-size:11.5px;color:var(--faint);display:flex;flex-wrap:wrap;gap:0 8px}
.witem p .w{color:var(--accent);font-weight:700}
.witem p .new{color:var(--card);background:var(--new);border-radius:3px;padding:0 5px;font-weight:700;letter-spacing:.1em}
.witem .sc{font-family:var(--f-head);font-size:15px;font-weight:800;font-variant-numeric:tabular-nums;color:var(--sub);line-height:1.5}
.witem.low a{color:var(--sub)}
.witem.low .sc{color:var(--faint);font-weight:700}
.witem.low .sc::after{content:"未満";font-family:var(--f);font-size:9.5px;margin-left:2px}
.watch .more{display:block;width:100%;border:0;border-top:1px solid var(--rule);background:none;color:var(--accent);font-weight:700;font-size:13px;padding:10px;cursor:pointer}
.watch-side{display:none}

.side{display:none}
.side-h{margin:6px 2px 0;font-family:var(--f-head);font-weight:800;font-size:14px;letter-spacing:.1em;color:var(--sub)}
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
  .lead .big{font-size:72px}
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
@media (prefers-reduced-motion:no-preference){.tab,.chip{transition:background-color .15s,color .15s}}
</style>
</head>
<body>
<section class="mast"><div class="wrap"><h1>__TITLE__</h1><span class="upd" id="upd"></span></div></section>

<header><div class="wrap">
  <nav class="tabs" role="tablist" aria-label="記事の種類"></nav>
</div></header>

<main><div class="wrap">
  <aside class="side" aria-label="絞り込み">
    <nav class="tabs" role="tablist" aria-label="記事の種類"></nav>
    <section class="watch watch-side" aria-label="見張り"></section>
    <p class="side-h">タグ</p>
    <div class="tagbar" aria-label="タグで絞り込む"></div>
  </aside>
  <div class="col">
    <div class="tagbar tagbar-m" aria-label="タグで絞り込む"></div>
    <div id="feed"></div>
  </div>
</div></main>
<footer><div class="wrap">__MIN__ 点に満たない記事は一番下に畳んでいる。見張りの欄だけは点数を問わない。見出し・要約は自動生成のため、原文で確かめること。</div></footer>

<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
  const D=JSON.parse(document.getElementById('data').textContent);
  const AG={
    impl:{name:'実装・設計',c:'--c-impl'},
    aws:{name:'AWS 新機能',c:'--c-aws'},
    case:{name:'事例',c:'--c-case'},
    trend:{name:'動向',c:'--c-trend'},
    model:{name:'新モデル・製品',short:'新モデル',c:'--c-model'}
  };
  const TIERS=[[90,'必読'],[80,'要注目'],[55,'実装向け'],[30,'限定的'],[0,'参考']];
  const tier=s=>TIERS.find(t=>s>=t[0])[1];
  const tz={timeZone:'Asia/Tokyo'};
  const fDay=new Intl.DateTimeFormat('ja-JP',{...tz,month:'long',day:'numeric',weekday:'short'});
  const fMd=new Intl.DateTimeFormat('ja-JP',{...tz,month:'numeric',day:'numeric'});
  const fUpd=new Intl.DateTimeFormat('ja-JP',{...tz,month:'numeric',day:'numeric',hour:'numeric',minute:'2-digit'});
  const dayKey=iso=>new Intl.DateTimeFormat('en-CA',tz).format(new Date(iso));
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const col=k=>`--c:var(${k==='all'?'--c-all':AG[k].c})`;
  // 種類が未知の記事（古いデータ等）は実装・設計に寄せる
  D.articles.forEach(a=>{ if(!AG[a.category]) a.category='impl'; });
  document.getElementById('upd').textContent=fUpd.format(new Date(D.generated_at))+' 更新';

  const feed=document.getElementById('feed');
  const keys=['all',...Object.keys(AG)];
  let cur='all', curTags=[];
  try{const s=localStorage.getItem('awsnews-cat'); if(keys.includes(s)) cur=s;}catch(e){}
  const hasTag=a=>curTags.every(t=>(a.tags||[]).includes(t));
  const inTab=a=>cur==='all'||a.category===cur;
  const pub=a=>a.published_at||a.sort_at||D.generated_at;

  // 見張り: 見張る言葉がタグか題名に当たった記事。点数とタブは問わない
  const W=(D.watch||[]).map(w=>({...w,re:new RegExp(w.pattern,'i')}));
  const watchOf=a=>W.filter(w=>[a.title_ja,a.title_original,...(a.tags||[])].some(x=>w.re.test(x||''))).map(w=>w.name);
  const watched=D.articles.map(a=>({a,w:watchOf(a)})).filter(x=>x.w.length).sort((x,y)=>pub(y.a).localeCompare(pub(x.a))||y.a.score-x.a.score);
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
    return `<div class="watch-h"><h2>見張り</h2><span>${list.length} 件${nNew?` ・ 新着 <b>${nNew}</b>`:''}</span></div>
      <div class="wchips">${W.map(w=>`<button class="chip" data-watch="${esc(w.name)}" aria-pressed="${wSel===w.name}">${esc(w.name)}<span class="n">${cnt(w.name)}</span></button>`).join('')}</div>
      ${show.map(({a,w})=>`<div class="witem${a.score<D.min_score?' low':''}"><div style="min-width:0"><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title_ja)}</a>
        <p>${isNew(a)?'<span class="new">新</span>':''}<span>${fMd.format(new Date(pub(a)))}</span><span class="w">${w.join(' ・ ')}</span><span>${AG[a.category].short||AG[a.category].name}</span></p></div>
        <b class="sc" aria-label="${a.score} 点">${a.score}</b></div>`).join('')}
      ${list.length>limit?`<button class="more" data-wmore>${wOpen?'たたむ':`残り ${list.length-limit} 件も見る`}</button>`:''}`;
  }
  function renderWatch(){
    document.querySelectorAll('.watch-side').forEach(el=>el.innerHTML=watched.length?watchHtml(8):'');
  }
  function renderTabs(){
    const tabsHtml=keys.map(k=>{
      const n=D.articles.filter(a=>(k==='all'||a.category===k)&&hasTag(a)&&a.score>=D.min_score).length;
      const label=k==='all'?'すべて':(AG[k].short||AG[k].name);
      return `<button class="tab" role="tab" data-k="${k}" style="${col(k)}" aria-selected="${k===cur}">${label}<span class="n">${n}</span></button>`;
    }).join('');
    document.querySelectorAll('.tabs').forEach(el=>el.innerHTML=tabsHtml);
  }
  function renderTagbar(){
    const pool=D.articles.filter(a=>inTab(a)&&hasTag(a));
    const c=new Map(); pool.forEach(a=>(a.tags||[]).forEach(t=>c.set(t,(c.get(t)||0)+1)));
    let list=[...c].filter(([t,n])=>!curTags.includes(t)&&n>=(curTags.length?1:2)).sort((x,y)=>y[1]-x[1]||x[0].localeCompare(y[0],'ja')).slice(0,24);
    list=[...curTags.map(t=>[t,c.get(t)||0]),...list];
    const tagHtml=list.map(([t,n])=>`<button class="chip" data-tag="${esc(t)}" aria-pressed="${curTags.includes(t)}">${esc(t)}<span class="n">${n}</span></button>`).join('');
    document.querySelectorAll('.tagbar').forEach(el=>el.innerHTML=tagHtml);
  }
  const kicker=a=>`<p class="kicker"><span class="cat">${AG[a.category].name}</span><span>${esc(a.source_label)}</span></p>`;
  const tags=a=>`<div class="tags">${(a.tags||[]).slice(0,3).map(t=>`<button data-tag="${esc(t)}" aria-pressed="${curTags.includes(t)}">${esc(t)}</button>`).join('')}</div>`;
  const imp=a=>`<p class="imp"><b>効き目</b>${esc(a.impact)}</p>`;
  function lead(a){
    return `<article class="lead" style="${col(a.category)};--k:var(--k-${cur==='all'?'all':a.category})">
      <a class="cover" href="${esc(a.url)}" target="_blank" rel="noopener">
        <div class="top"><span>${AG[a.category].name} ・ ${esc(a.source_label)}</span><span>${fDay.format(new Date(pub(a)))}</span></div>
        <div class="big">${a.score}<small class="${a.score>=90?'must':''}">${tier(a.score)}</small></div>
      </a>
      <div class="body"><h2><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title_ja)}</a></h2>
        <p class="sum">${esc(a.summary)}</p>${imp(a)}${tags(a)}</div></article>`;
  }
  function row(a){
    return `<article class="row" style="${col(a.category)}"><div style="min-width:0">${kicker(a)}
      <h3><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title_ja)}</a></h3>
      <p class="sum">${esc(a.summary)}</p>${imp(a)}${tags(a)}</div>
      <div class="score${a.score>=90?' must':''}" aria-label="${a.score} 点 ${tier(a.score)}"><b>${a.score}</b><span>${tier(a.score)}</span></div></article>`;
  }
  function render(){
    const items=D.articles.filter(a=>inTab(a)&&hasTag(a));
    const shown=items.filter(a=>a.score>=D.min_score).sort((x,y)=>pub(y).localeCompare(pub(x))||y.score-x.score);
    const skipped=items.filter(a=>a.score<D.min_score).sort((x,y)=>y.score-x.score);
    let h='';
    // スマホでは「すべて」の一番上に置く。PC では左の列に常に出す
    if(cur==='all'&&!curTags.length&&watched.length) h+=`<section class="watch watch-main" aria-label="見張り">${watchHtml(5)}</section>`;
    if(curTags.length) h+=`<div class="filter"><span><b>${cur==='all'?'すべて':AG[cur].name}</b> の中で ${curTags.map(t=>`#${esc(t)}`).join(' ')} ・ ${items.length} 件</span><button data-clear>解除</button></div>`;
    if(!shown.length) h+=`<p class="empty">この条件で ${D.min_score} 点に届く記事は、まだない。</p>`;
    else{
      // トップ記事はタブの並び順（読む優先度）で選ぶ。点数だけで選ぶと新モデルの発表が上に来てしまう
      const rank=Object.keys(AG);
      const top=[...shown].sort((x,y)=>(y.score>=90)-(x.score>=90)||rank.indexOf(x.category)-rank.indexOf(y.category)||y.score-x.score||pub(y).localeCompare(pub(x)))[0];
      h+=lead(top);
      let last='',open=false;
      for(const a of shown){ if(a===top) continue;
        const k=dayKey(pub(a));
        if(k!==last){ if(open) h+='</div>'; h+=`<h2 class="day">${fDay.format(new Date(pub(a)))}</h2><div class="group">`; last=k; open=true; }
        h+=row(a);
      }
      if(open) h+='</div>';
    }
    if(skipped.length){
      h+=`<details class="skipped"><summary>見送った記事 ${skipped.length} 件<span>${D.min_score} 点未満 ・ 開く</span></summary>`+
        skipped.map(a=>`<div class="skip" style="${col(a.category)}"><b>${a.score}</b><div style="min-width:0"><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title_ja)}</a><p><span class="cat">${AG[a.category].name}</span> ・ ${esc(a.reason)}</p></div></div>`).join('')+'</details>';
    }
    feed.innerHTML=h;
  }
  function renderAll(){renderTabs();renderWatch();renderTagbar();render();}
  document.addEventListener('click',e=>{
    const tab=e.target.closest('.tab');
    if(tab){ cur=tab.dataset.k; try{localStorage.setItem('awsnews-cat',cur)}catch(err){} renderAll(); window.scrollTo({top:0}); return; }
    const t=e.target.closest('[data-tag]'), c=e.target.closest('[data-clear]');
    if(t||c){ if(c) curTags=[]; else {const v=t.dataset.tag; curTags=curTags.includes(v)?curTags.filter(x=>x!==v):[...curTags,v];} renderAll(); window.scrollTo({top:0}); return; }
    const w=e.target.closest('[data-watch]'), m=e.target.closest('[data-wmore]');
    if(w){ wSel=wSel===w.dataset.watch?'':w.dataset.watch; renderWatch(); render(); }
    else if(m){ wOpen=!wOpen; renderWatch(); render(); }
  });
  renderAll();
})();
</script>
</body>
</html>
"""
