#!/usr/bin/env python3
"""Library agent: the only part of crosspoint-check that touches a Calibre library.

    agent.py --library DIR list
    agent.py --library DIR get ID            > book.epub
    agent.py --library DIR put ID SIZE MTIME SHA256 < fixed.epub

Standard library only (Python 3.9+), so this one file can be copied to the
machine that holds the library and called over SSH, while the checks run
elsewhere. crosspoint-check also imports it for a library on the same machine.

It reads Calibre's metadata.db read-only and never writes to it. `put`
replaces one EPUB in place, and only if the file is still the one that was
checked (same size and modification time) and the upload arrived intact.
"""
import argparse
import hashlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import zipfile
from urllib.parse import quote

QUERY = """
SELECT b.id, b.title,
       (SELECT group_concat(a.name, ' & ') FROM books_authors_link l
          JOIN authors a ON a.id = l.author WHERE l.book = b.id),
       b.path, d.name
FROM books b JOIN data d ON d.book = b.id
WHERE d.format = 'EPUB' ORDER BY b.id
"""


class AgentError(Exception):
    pass


def _rows(library):
    db = os.path.join(library, 'metadata.db')
    if not os.path.isfile(db):
        raise AgentError('no Calibre library here (metadata.db missing): %s' % library)
    last = None
    # Plain read-only first; "immutable" as a fallback for a library on a
    # read-only mount or owned by another user (no -shm/-wal access).
    for mode in ('mode=ro', 'mode=ro&immutable=1'):
        try:
            con = sqlite3.connect('file:%s?%s' % (quote(db), mode), uri=True, timeout=30)
            try:
                return con.execute(QUERY).fetchall()
            finally:
                con.close()
        except sqlite3.Error as e:
            last = e
    raise AgentError('cannot read %s: %s' % (db, last))


def list_books(library):
    """Every book that has an EPUB: id, title, author, file (relative), size, mtime (ns)."""
    books = []
    for book_id, title, authors, path, name in _rows(library):
        rel = os.path.join(path, name + '.epub')
        try:
            st = os.stat(os.path.join(library, rel))
        except OSError:
            continue
        books.append({
            'id': book_id,
            'title': title or '',
            'author': (authors or '').replace('|', ','),
            'file': rel,
            'size': st.st_size,
            'mtime': st.st_mtime_ns,
        })
    return books


def find(library, book_id):
    for b in list_books(library):
        if b['id'] == int(book_id):
            return b
    raise AgentError('book %s has no EPUB in this library' % book_id)


def get(library, book_id, out):
    book = find(library, book_id)
    with open(os.path.join(library, book['file']), 'rb') as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    return book


def put(library, book_id, size, mtime, sha256, data):
    """Replace a book's EPUB with `data` if the file is unchanged since the check."""
    book = find(library, book_id)
    if book['size'] != int(size) or book['mtime'] != int(mtime):
        raise AgentError('book %s changed since it was checked, not replaced' % book_id)
    if hashlib.sha256(data).hexdigest() != sha256:
        raise AgentError('upload damaged (checksum differs), not replaced')
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        if z.testzip() is not None or 'META-INF/container.xml' not in z.namelist():
            raise AgentError('upload is not an EPUB, not replaced')
    except zipfile.BadZipFile:
        raise AgentError('upload is not an EPUB, not replaced') from None
    target = os.path.join(library, book['file'])
    st = os.stat(target)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix='.crosspoint-check-')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, st.st_mode & 0o7777)
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except OSError:
            pass
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return find(library, book_id)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--library', required=True, help='folder with metadata.db')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list')
    g = sub.add_parser('get')
    g.add_argument('id', type=int)
    p = sub.add_parser('put')
    p.add_argument('id', type=int)
    p.add_argument('size', type=int)
    p.add_argument('mtime', type=int)
    p.add_argument('sha256')
    a = ap.parse_args(argv)
    try:
        if a.cmd == 'list':
            json.dump(list_books(a.library), sys.stdout)
        elif a.cmd == 'get':
            get(a.library, a.id, sys.stdout.buffer)
        else:
            json.dump(put(a.library, a.id, a.size, a.mtime, a.sha256, sys.stdin.buffer.read()), sys.stdout)
    except AgentError as e:
        print('crosspoint-check agent: %s' % e, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
