#!/usr/bin/env python3
"""Build a demo library with made-up copies of public-domain titles, scan it and
write the status page (for the README screenshot; never uses a real library).

    scripts/demo.py OUTDIR [--cache DIR]     # then open OUTDIR/state/www/index.html
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from crosspoint_check import config, service  # noqa: E402
from tests.conftest import BROKEN, GOOD, make_epub  # noqa: E402

BOOKS = [
    ('Alice\'s Adventures in Wonderland', 'Lewis Carroll', 'good'),
    ('Dracula', 'Bram Stoker', 'broken'),
    ('Frankenstein', 'Mary Shelley', 'good'),
    ('Moby-Dick', 'Herman Melville', 'large'),
    ('Pride and Prejudice', 'Jane Austen', 'good'),
    ('The Time Machine', 'H. G. Wells', 'broken'),
    ('Treasure Island', 'Robert Louis Stevenson', 'good'),
    ('Twenty Thousand Leagues Under the Seas', 'Jules Verne', 'good'),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--cache', default=os.path.expanduser('~/.cache/crosspoint-check'))
    a = ap.parse_args()
    lib = os.path.join(a.out, 'library')
    os.makedirs(lib)
    con = sqlite3.connect(os.path.join(lib, 'metadata.db'))
    con.executescript('CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, path TEXT);'
                      'CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT);'
                      'CREATE TABLE books_authors_link (book INTEGER, author INTEGER);'
                      'CREATE TABLE data (book INTEGER, format TEXT, name TEXT);')
    big = GOOD.replace('<p>Hello world</p>', '<p>%s</p>' % ('Call me Ishmael. ' * 60) * 400)
    for i, (title, author, kind) in enumerate(BOOKS, 1):
        folder, name = '%s/%s (%d)' % (author, title, i), '%s - %s' % (title, author)
        con.execute('INSERT INTO books VALUES (?, ?, ?)', (i, title, folder))
        con.execute('INSERT INTO authors VALUES (?, ?)', (i, author))
        con.execute('INSERT INTO books_authors_link VALUES (?, ?)', (i, i))
        con.execute("INSERT INTO data VALUES (?, 'EPUB', ?)", (i, name))
        os.makedirs(os.path.join(lib, folder))
        chapters = {'good': [GOOD] * 12, 'broken': [GOOD] + [BROKEN] * 11, 'large': [GOOD, big]}[kind]
        make_epub(os.path.join(lib, folder, name + '.epub'), chapters)
    con.commit()
    cfg = config.Config(library_path=lib, state=os.path.join(a.out, 'state'))
    os.makedirs(cfg.state)
    os.makedirs(a.cache, exist_ok=True)
    os.symlink(a.cache, cfg.cache)
    # One book stays unrepaired, to show what a refused book looks like.
    service.scan(cfg, repair=False, only={6})
    cfg.repair = False
    service.scan(cfg, repair=True, only={1, 2, 3, 4, 5, 7, 8})
    print(os.path.join(cfg.www, 'index.html'))


if __name__ == '__main__':
    main()
