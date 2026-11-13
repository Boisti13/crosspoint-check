"""The status page: one static HTML file, rewritten after every scan."""
import os
import time
from html import escape
from urllib.parse import quote

from . import __version__

# Browser tab icon: an open book with a check mark, inline so the page stays one file.
ICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
            '<rect width="64" height="64" rx="14" fill="#1f5fa8"/>'
            '<path d="M32 20c-5-4-12-5-19-4v29c7-1 14 0 19 4 5-4 12-5 19-4V16c-7-1-14 0-19 4z" fill="#fff"/>'
            '<path d="M32 20v29" stroke="#1f5fa8" stroke-width="2.5"/>'
            '<circle cx="46" cy="46" r="13" fill="#2e7d4f" stroke="#fff" stroke-width="3"/>'
            '<path d="M40 46l4.5 4.5L53 42" fill="none" stroke="#fff" stroke-width="3.5" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>')
ICON = 'data:image/svg+xml,' + quote(ICON_SVG)

ORDER = {'failed': 0, 'error': 1, 'repaired': 2, 'warning': 3, 'ok': 4}
LABEL = {'failed': 'Cannot open', 'error': 'Not checked', 'repaired': 'Repaired', 'warning': 'Opens, large chapter',
         'ok': 'Opens'}

CSS = """
:root{--bg:#f6f5f1;--card:#fff;--ink:#1d1d1b;--dim:#6b6a65;--line:#e2e0d8;--ok:#2e7d4f;--bad:#b3261e;
--fix:#1f5fa8;--warn:#9a6700}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--card:#201f1d;--ink:#ecebe6;--dim:#a09f98;
--line:#35332f;--ok:#6cc08b;--bad:#f2867d;--fix:#7fb2ee;--warn:#e0b050}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:60rem;margin:0 auto;padding:1.5rem 1rem 3rem}
h1{font-size:1.5rem;margin:0}h2{font-size:1.05rem;margin:2rem 0 .5rem}
.sub{color:var(--dim);margin:.2rem 0 1.2rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(8.5rem,1fr));gap:.6rem}
.tile{background:var(--card);border:1px solid var(--line);border-radius:.6rem;padding:.7rem .9rem}
.tile b{display:block;font-size:1.6rem;font-variant-numeric:tabular-nums;line-height:1.2}
.tile span{color:var(--dim);font-size:.85rem}
.alert{border:1px solid var(--bad);color:var(--bad);border-radius:.6rem;padding:.6rem .9rem;margin:1rem 0}
.note{border:1px solid var(--line);color:var(--dim);border-radius:.6rem;padding:.6rem .9rem;margin:1rem 0}
.book{background:var(--card);border:1px solid var(--line);border-radius:.6rem;margin:.4rem 0;padding:.55rem .9rem}
.book summary{cursor:pointer;display:flex;gap:.6rem;align-items:baseline;flex-wrap:wrap;list-style:none}
.book summary::-webkit-details-marker{display:none}
.t{font-weight:600;overflow-wrap:anywhere}.a{color:var(--dim);overflow-wrap:anywhere}
.s{margin-left:auto;font-size:.85rem;font-weight:600;white-space:nowrap}
.failed .s,.error .s{color:var(--bad)}.repaired .s{color:var(--fix)}.warning .s{color:var(--warn)}.ok .s{color:var(--ok)}
.book ul{margin:.5rem 0 .2rem;padding-left:1.2rem;color:var(--dim);font-size:.9rem;overflow-wrap:anywhere}
.book p{margin:.5rem 0 0;font-size:.9rem;overflow-wrap:anywhere}
.plain{color:var(--dim);font-size:.9rem;overflow-wrap:anywhere}
footer{color:var(--dim);font-size:.85rem;margin-top:2.5rem}
"""


def _when(ts):
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(ts)) if ts else 'never'


def _problems(items, limit=8):
    out = ['<li><code>%s</code>: %s</li>' % (escape(p['file']), escape(p['detail'])) for p in items[:limit]]
    if len(items) > limit:
        out.append('<li>and %d more</li>' % (len(items) - limit))
    return '<ul>%s</ul>' % ''.join(out)


def _book(b):
    body = []
    if b.get('note'):
        body.append('<p>%s</p>' % escape(b['note']))
    if b['status'] == 'repaired':
        body.append('<p>What was wrong:</p>' + _problems(b['problems']))
        body.append('<p>What the repair changed:</p><ul>%s</ul>' % ''.join(
            '<li>%s</li>' % escape(c) for c in b['changes']))
        body.append('<p>Original kept as <code>%s</code>. If the reader still shows the old error, '
                    'delete the book on the reader and download it again.</p>' % escape(b['original'] or ''))
    elif b['problems']:
        body.append('<p>Files the reader refuses:</p>' + _problems(b['problems']))
    if b['warnings']:
        body.append('<p>Large chapter files (may be slow or run out of memory on the reader):</p>'
                    + _problems(b['warnings']))
    body.append('<p class="plain">Library id %d, %d chapter files, checked %s with CrossPoint %s</p>' % (
        b['id'], b['chapters'] or 0, _when(b['checked_at']), escape(b['tag'] or '?')))
    return ('<details class="book %s"><summary><span class="t">%s</span><span class="a">%s</span>'
            '<span class="s">%s</span></summary>%s</details>') % (
        b['status'], escape(b['title']), escape(b['author']), LABEL[b['status']], ''.join(body))


def render(store):
    books = store.books()
    last = store.get('last_scan', {})
    count = {k: sum(1 for b in books if b['status'] == k) for k in ORDER}
    attention = [b for b in books if b['status'] in ('failed', 'error')]
    repaired = [b for b in books if b['status'] == 'repaired']
    rest = sorted((b for b in books if b['status'] in ('warning', 'ok')), key=lambda b: ORDER[b['status']])
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<link rel="icon" type="image/svg+xml" href="%s">' % ICON,
             '<title>crosspoint-check</title><style>%s</style></head><body><main>' % CSS,
             '<h1>crosspoint-check</h1>',
             '<p class="sub">Last scan %s%s</p>' % (
                 _when(last.get('at')), ', CrossPoint %s' % escape(last['tag']) if last.get('tag') else '')]
    if last.get('error'):
        parts.append('<div class="alert">The last scan stopped: %s</div>' % escape(last['error']))
    if last.get('note'):
        parts.append('<div class="note">%s</div>' % escape(last['note']))
    parts.append('<div class="tiles">')
    for key, label in (('ok', 'open fine'), ('repaired', 'repaired'), ('failed', 'cannot open'),
                       ('warning', 'large chapter')):
        n = count[key] + (count['error'] if key == 'failed' else 0)
        parts.append('<div class="tile"><b>%d</b><span>%s</span></div>' % (n, label))
    parts.append('</div>')
    for title, group in (('Needs attention', attention), ('Repaired', repaired), ('All other books', rest)):
        if group:
            parts.append('<h2>%s</h2>' % title)
            parts.extend(_book(b) for b in group)
    if not books:
        parts.append('<p class="sub">No books checked yet.</p>')
    events = store.events(15)
    if events:
        parts.append('<h2>History</h2>')
        parts.extend('<p class="plain">%s: %s <b>%s</b>%s</p>' % (
            _when(e['at']), escape(e['kind']), escape(e['title']),
            ' (%s)' % escape(e['text']) if e['text'] else '') for e in events)
    parts.append('<footer>crosspoint-check %s</footer></main></body></html>' % __version__)
    return '\n'.join(parts)


def write(cfg, store):
    os.makedirs(cfg.www, exist_ok=True)
    tmp = os.path.join(cfg.www, 'index.html.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(render(store))
    os.replace(tmp, os.path.join(cfg.www, 'index.html'))
