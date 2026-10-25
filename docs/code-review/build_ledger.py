"""Builds ledger.html (the published page) from LEDGER.md and UNVERIFIED.md (two tabs). Run after every edit to the ledger:

    python3 docs/code-review/build_ledger.py

Then republish ledger.html to the same artifact. The page renders the Markdown in the browser.
"""
from pathlib import Path

here = Path(__file__).parent
md = (here / "LEDGER.md").read_text()
unv_path = here / "UNVERIFIED.md"
unv = unv_path.read_text() if unv_path.exists() else "# Unverified\n\nNothing here yet.\n"
# The Markdown sits inside <script> tags, so it must not be able to close them.
safe = md.replace("</script", "<\\/script")
safe_unv = unv.replace("</script", "<\\/script")

PAGE = r"""<title>Orchard Sentinel Ledger</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;700&family=JetBrains+Mono:wght@400;600&display=swap">
<style>
/* Layout: one reading column with a sticky filter bar; wide tables scroll inside their own box. */
:root{
  --bg:#f6f7f4; --surface:#ffffff; --fg:#1d2420; --muted:#5d6a62; --line:#dde3dc;
  --accent:#2f6b3f; --apple:#b3362b; --chip:#e8efe7;
  --ok:#2f6b3f; --warn:#9a6a00; --bad:#b3362b;
  --body:"Public Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#121614; --surface:#1a201c; --fg:#e4ebe5; --muted:#9aa89f; --line:#2c352f;
  --accent:#7cc48e; --apple:#ef7d6f; --chip:#223027; --ok:#7cc48e; --warn:#e2b24c; --bad:#ef7d6f; color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#121614; --surface:#1a201c; --fg:#e4ebe5; --muted:#9aa89f; --line:#2c352f;
  --accent:#7cc48e; --apple:#ef7d6f; --chip:#223027; --ok:#7cc48e; --warn:#e2b24c; --bad:#ef7d6f; color-scheme:dark}
body{background:var(--bg);color:var(--fg);font:15px/1.6 var(--body);
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:0 48px}
.wrap{max-width:1100px;margin:0 auto}
.bar{position:sticky;top:env(safe-area-inset-top,0px);z-index:2;background:var(--bg);border-bottom:1px solid var(--line);
  display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;padding-block:10px}
.bar strong{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--accent)}
.bar input{flex:1 1 220px;min-width:0;font:inherit;padding:6px 10px;border:1px solid var(--line);border-radius:6px;background:var(--surface);color:var(--fg)}
.bar input:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.stats{display:flex;gap:8px;flex-wrap:wrap;font-size:13px;color:var(--muted)}
.stats b{color:var(--fg);font-variant-numeric:tabular-nums}
h1{font-size:28px;line-height:1.2;margin:28px 0 8px;text-wrap:balance}
h2{font-size:20px;margin:36px 0 10px;padding-top:8px;border-top:2px solid var(--fg);text-wrap:balance}
h3{font-size:16px;margin:24px 0 8px;color:var(--accent)}
p,li{max-width:72ch}
code{font:13px var(--mono);background:var(--chip);padding:1px 5px;border-radius:4px;overflow-wrap:anywhere}
hr{border:0;border-top:1px solid var(--line);margin:32px 0}
.tbl{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:8px;margin:10px 0 18px}
table{border-collapse:collapse;width:100%;font-size:13.5px;line-height:1.5}
th{text-align:left;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);background:var(--bg);position:sticky;top:0}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
td:first-child{font:600 12.5px var(--mono);white-space:nowrap}
tr:last-child td{border-bottom:0}
tr.done td{color:var(--muted)}
tr.done td:first-child{text-decoration:line-through}
.st{display:inline-block;font:600 11.5px var(--mono);padding:2px 7px;border-radius:999px;white-space:nowrap}
.st.open{background:var(--chip);color:var(--apple)}
.st.done{background:var(--chip);color:var(--ok)}
.hidden-row{display:none}
.tabs{display:flex;gap:4px;margin-top:14px;border-bottom:1px solid var(--line)}
.tabs button{font:600 14px var(--body);color:var(--muted);background:none;border:0;border-bottom:3px solid transparent;padding:8px 14px;cursor:pointer;margin-bottom:-1px}
.tabs button[aria-selected="true"]{color:var(--fg);border-bottom-color:var(--accent)}
.tabs button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.st.unv{background:var(--chip);color:var(--warn)}
#fallback{white-space:pre-wrap;font:13px var(--mono)}
@media (prefers-reduced-motion: no-preference){tr{transition:background .15s}}
tr:hover td{background:color-mix(in srgb,var(--chip) 60%,transparent)}
</style>
<div class="wrap">
  <div class="bar">
    <strong>Ledger</strong>
    <input id="q" type="search" placeholder="Filter rows (e.g. firmware, P0, open, L-12)" aria-label="Filter table rows">
    <div class="stats" id="stats"></div>
  </div>
  <nav class="tabs" role="tablist">
    <button id="tab-ledger" role="tab" aria-selected="true" data-pane="doc">Ledger</button>
    <button id="tab-unverified" role="tab" aria-selected="false" data-pane="unv">Unverified</button>
  </nav>
  <main id="doc"><pre id="fallback"></pre></main>
  <main id="unv" hidden></main>
</div>
<script type="text/markdown" id="src">__MD__</script>
<script type="text/markdown" id="src-unv">__UNV__</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/4.3.0/marked.min.js"></script>
<script>
(function(){
  var doc=document.getElementById('doc'), unv=document.getElementById('unv');
  if (!window.marked) { document.getElementById('fallback').textContent = document.getElementById('src').textContent; return; }
  function render(el, srcId){
    el.innerHTML = marked.parse(document.getElementById(srcId).textContent);
    el.querySelectorAll('table').forEach(function(t){ var w=document.createElement('div'); w.className='tbl'; t.parentNode.insertBefore(w,t); w.appendChild(t); });
    var c={open:0,done:0,unv:0};
    el.querySelectorAll('table').forEach(function(t){
      var heads=[].map.call(t.querySelectorAll('th'),function(h){return h.textContent.trim().toLowerCase();});
      var si=heads.indexOf('status'); if(si<0) return;
      t.querySelectorAll('tbody tr').forEach(function(r){
        var cell=r.children[si]; if(!cell) return; var v=cell.textContent.trim().toLowerCase();
        var k=v.indexOf('done')===0?'done':v.indexOf('unverified')===0?'unv':'open'; c[k]++;
        if(k==='done') r.classList.add('done');
        cell.innerHTML='<span class="st '+k+'">'+cell.innerHTML+'</span>';
      });
    });
    return c;
  }
  var a=render(doc,'src'), b=render(unv,'src-unv');
  document.getElementById('stats').innerHTML='<span><b>'+a.open+'</b> open</span><span><b>'+a.done+'</b> done</span><span><b>'+b.unv+'</b> unverified</span>';
  var tabs=[].slice.call(document.querySelectorAll('.tabs button'));
  function show(id){
    tabs.forEach(function(t){ var on=t.dataset.pane===id; t.setAttribute('aria-selected',on); document.getElementById(t.dataset.pane).hidden=!on; });
    try{ localStorage.setItem('ledger-tab',id); }catch(e){}
  }
  tabs.forEach(function(t){ t.addEventListener('click',function(){ show(t.dataset.pane); }); });
  var start = location.hash==='#unverified' ? 'unv' : null;
  if(!start){ try{ start=localStorage.getItem('ledger-tab'); }catch(e){} }
  if(start==='unv') show('unv');
  var q=document.getElementById('q');
  q.addEventListener('input',function(){
    var s=q.value.trim().toLowerCase();
    document.querySelectorAll('main tbody tr').forEach(function(r){ r.classList.toggle('hidden-row', !!s && r.textContent.toLowerCase().indexOf(s)<0); });
  });
})();
</script>
"""

(here / "ledger.html").write_text(PAGE.replace("__MD__", safe).replace("__UNV__", safe_unv))
print(f"wrote {here / 'ledger.html'} ({len(md)} chars of Markdown)")
