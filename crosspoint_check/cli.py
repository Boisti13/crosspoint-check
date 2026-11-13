"""Command line: check and fix single files, or scan a whole Calibre library."""
import argparse
import os
import sys

from . import __version__, harness
from .config import ConfigError, load

USER_CACHE = os.path.join(os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache'), 'crosspoint-check')


def cmd_check(a):
    tag, note = harness.ensure(a.cache, a.crosspoint)
    if note:
        print(note)
    bad = 0
    for book in a.books:
        res = harness.check(a.cache, tag, book, a.large_kb)
        print('%s  %s  (CrossPoint %s, %d chapter files)' % ('OK  ' if res.ok else 'FAIL', book, tag, res.chapters))
        for p in res.problems:
            print('      %s: %s' % (p.file, p.detail))
        for p in res.warnings:
            print('      note: %s: %s' % (p.file, p.detail))
        bad += not res.ok
    return 1 if bad else 0


def cmd_fix(a):
    from . import fixer
    for line in fixer.fix(a.src, a.dst, images=a.images, max_kb=a.max_kb):
        print(line)
    tag, _ = harness.ensure(a.cache, a.crosspoint)
    res = harness.check(a.cache, tag, a.dst)
    print('%s  %s  (CrossPoint %s)' % ('OK  ' if res.ok else 'FAIL', a.dst, tag))
    for p in res.problems:
        print('      %s: %s' % (p.file, p.detail))
    return 0 if res.ok else 1


def cmd_scan(a):
    from . import service
    cfg = load(a.config)
    return service.scan(cfg, repair=False if a.no_repair else None, force=a.force, only=set(a.book) or None)


def cmd_page(a):
    from . import page
    from .store import Store
    cfg = load(a.config)
    store = Store(cfg.db)
    page.write(cfg, store)
    print(os.path.join(cfg.www, 'index.html'))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='crosspoint-check', description=__doc__)
    ap.add_argument('--version', action='version', version=__version__)
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p):
        p.add_argument('--cache', default=USER_CACHE, help='where the CrossPoint parser is built (%(default)s)')
        p.add_argument('--crosspoint', default='latest', help='CrossPoint release to check with (%(default)s)')

    c = sub.add_parser('check', help='test EPUB files with CrossPoint\'s own parser')
    c.add_argument('books', nargs='+')
    c.add_argument('--large-kb', type=int, default=300, help='note chapter files above this size (%(default)s)')
    common(c)
    c.set_defaults(fn=cmd_check)

    f = sub.add_parser('fix', help='write a repaired copy of an EPUB and test it')
    f.add_argument('src')
    f.add_argument('dst')
    f.add_argument('--max-kb', type=int, default=100, help='split chapter files above this size (%(default)s)')
    f.add_argument('--images', action='store_true', help='also rework pictures for a 480x800 e-paper screen')
    common(f)
    f.set_defaults(fn=cmd_fix)

    s = sub.add_parser('scan', help='check the library from the config file, repair what fails')
    s.add_argument('--config')
    s.add_argument('--no-repair', action='store_true', help='only report, change nothing in the library')
    s.add_argument('--force', action='store_true', help='check every book again, not only new and changed ones')
    s.add_argument('--book', type=int, action='append', default=[], help='only this library id (repeatable)')
    s.set_defaults(fn=cmd_scan)

    p = sub.add_parser('page', help='rewrite the status page')
    p.add_argument('--config')
    p.set_defaults(fn=cmd_page)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except (ConfigError, harness.HarnessError) as e:
        print('crosspoint-check: %s' % e, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
