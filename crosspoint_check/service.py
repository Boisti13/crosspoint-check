"""One pass over the library: check what is new or changed, repair what fails."""
import fcntl
import os
import shutil
import tempfile
import time
from dataclasses import asdict

from . import fixer, harness, notify, page
from .library import Library, LibraryError
from .store import Store


def process(cfg, lib, tag, book, old, repair):
    """Check one book (and repair it); returns its new row."""
    row = dict(book, tag=tag, changes=[], original=None, note=None)
    with tempfile.TemporaryDirectory(prefix='crosspoint-check-') as work:
        src = os.path.join(work, 'in.epub')
        lib.get(book['id'], src)
        res = harness.check(cfg.cache, tag, src, cfg.large_kb)
        row.update(chapters=res.chapters, problems=[asdict(p) for p in res.problems],
                   warnings=[asdict(p) for p in res.warnings])
        wanted = not res.ok or (cfg.split_large and bool(res.warnings))
        if not wanted:
            row['status'] = 'warning' if res.warnings else 'ok'
            # Still the copy we repaired earlier: keep saying so.
            if old and old.get('original') and (old['size'], old['mtime']) == (book['size'], book['mtime']):
                row.update(status='repaired', original=old['original'], changes=old['changes'],
                           problems=old['problems'])
            return row
        row['status'] = 'failed' if not res.ok else 'warning'
        if not repair:
            return row
        out = os.path.join(work, 'out.epub')
        try:
            changes = fixer.fix(src, out, images=cfg.images, max_kb=cfg.max_kb)
        except Exception as e:  # a book odd enough to break the repair must not stop the scan
            row['note'] = 'repair did not work: %s' % (str(e) or type(e).__name__)
            return row
        again = harness.check(cfg.cache, tag, out, cfg.large_kb)
        if not again.ok:
            row['note'] = 'still refused after the repair (%d files)' % len(again.problems)
            return row
        os.makedirs(cfg.originals, exist_ok=True)
        original = os.path.join(cfg.originals, '%d-%s-%s' % (
            book['id'], time.strftime('%Y%m%d%H%M%S'), os.path.basename(book['file'])))
        shutil.copyfile(src, original)
        try:
            new = lib.put(book, out)
        except LibraryError:
            os.unlink(original)
            raise
        row.update(size=new['size'], mtime=new['mtime'], status='repaired', changes=changes,
                   original=original, warnings=[asdict(p) for p in again.warnings])
    return row


def scan(cfg, repair=None, force=False, only=None, log=print):
    """Returns 0, or 1 when the library or the parser build could not be used."""
    repair = cfg.repair if repair is None else repair
    for d in (cfg.state, cfg.www):
        os.makedirs(d, exist_ok=True)
    lock = open(os.path.join(cfg.state, 'lock'), 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log('another scan is running')
        return 0
    store = Store(cfg.db)
    last = {'at': time.time(), 'checked': 0, 'error': None, 'note': None, 'tag': None}
    repaired, failed = [], []
    try:
        lib = Library(cfg.library_path, cfg.library_command)
        books = lib.list()
        tag, last['note'] = harness.ensure(cfg.cache, cfg.crosspoint, log)
        last['tag'] = tag
        if last['note']:
            log(last['note'])
        for book in books:
            if only and book['id'] not in only:
                continue
            old = store.book(book['id'])
            if old and not force and (old['size'], old['mtime'], old['tag']) == (book['size'], book['mtime'], tag):
                continue
            try:
                row = process(cfg, lib, tag, book, old, repair)
            except harness.HarnessError as e:
                row = dict(book, tag=tag, status='error', note=str(e), size=-1, chapters=0)
            last['checked'] += 1
            store.save(row)
            log('%-8s %s%s' % (row['status'], book['title'], ' (%s)' % row['note'] if row.get('note') else ''))
            if row['status'] == 'repaired' and not (old and old['status'] == 'repaired' and old['mtime'] == row['mtime']):
                store.event(row, 'repaired', '; '.join(row['changes']))
                repaired.append(row)
            elif row['status'] == 'failed' and not (old and old['status'] == 'failed'):
                store.event(row, 'failed', row.get('note') or '%d files refused' % len(row['problems']))
                failed.append(row)
        if not only:
            store.forget({b['id'] for b in books})
    except (LibraryError, harness.HarnessError) as e:
        last['error'] = str(e)
        log('scan stopped: %s' % e)
    notify.send(cfg.webhook, repaired, failed, cfg.page_url, log)
    store.set('last_scan', last)
    page.write(cfg, store)
    store.close()
    return 1 if last['error'] else 0
