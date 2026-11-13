import os
import sqlite3
import zipfile
from xml.parsers import expat

import pytest

from crosspoint_check import harness

GOOD = ('<?xml version="1.0"?>\n<html xmlns="http://www.w3.org/1999/xhtml"><head><title>t</title></head>'
        '<body><p>Hello world</p></body></html>')
# What Calibre-Web-Automated's fixer leaves behind: a meta tag that is never closed.
BROKEN = GOOD.replace('<title>', '<meta charset="utf-8"><title>')


def make_epub(path, chapters, ncx=None):
    z = zipfile.ZipFile(path, 'w')
    z.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip')
    z.writestr('META-INF/container.xml',
               '<?xml version="1.0"?><container version="1.0" '
               'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
               '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
               '</rootfiles></container>')
    items = ''.join('<item id="c%d" href="c%d.xhtml" media-type="application/xhtml+xml"/>' % (i, i)
                    for i in range(len(chapters)))
    if ncx:
        items += '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        z.writestr('OEBPS/toc.ncx', ncx)
    refs = ''.join('<itemref idref="c%d"/>' % i for i in range(len(chapters)))
    z.writestr('OEBPS/content.opf',
               '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0" '
               'unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               '<dc:title>T</dc:title><dc:identifier id="id">x</dc:identifier><dc:language>en</dc:language>'
               '</metadata><manifest>%s</manifest><spine>%s</spine></package>' % (items, refs))
    for i, c in enumerate(chapters):
        z.writestr('OEBPS/c%d.xhtml' % i, c, zipfile.ZIP_DEFLATED)
    z.close()
    return path


@pytest.fixture
def library(tmp_path):
    """A small Calibre library: book 1 opens, book 2 has a broken chapter, book 3 has no EPUB."""
    lib = tmp_path / 'library'
    lib.mkdir()
    con = sqlite3.connect(lib / 'metadata.db')
    con.executescript("""
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, path TEXT);
        CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_authors_link (book INTEGER, author INTEGER);
        CREATE TABLE data (book INTEGER, format TEXT, name TEXT);
        INSERT INTO authors VALUES (1, 'Ann Author'), (2, 'Smith| John');
        INSERT INTO books VALUES (1, 'Good Book', 'Ann Author/Good Book (1)'),
                                 (2, 'Broken <Book>', 'Smith, John/Broken Book (2)'),
                                 (3, 'Paper Only', 'Ann Author/Paper Only (3)');
        INSERT INTO books_authors_link VALUES (1, 1), (2, 2), (2, 1), (3, 1);
        INSERT INTO data VALUES (1, 'EPUB', 'Good Book - Ann Author'), (2, 'EPUB', 'Broken Book - John Smith'),
                                (2, 'KEPUB', 'Broken Book - John Smith'), (3, 'PDF', 'Paper Only - Ann Author');
    """)
    con.commit()
    con.close()
    for folder, name, chapters in (('Ann Author/Good Book (1)', 'Good Book - Ann Author', [GOOD, GOOD]),
                                   ('Smith, John/Broken Book (2)', 'Broken Book - John Smith', [GOOD, BROKEN])):
        os.makedirs(lib / folder)
        make_epub(lib / folder / (name + '.epub'), chapters)
    return str(lib)


@pytest.fixture
def fake_harness(monkeypatch):
    """Stand-in for the CrossPoint build: a chapter fails when it is not well-formed XML."""
    def ensure(cache, tag='latest', log=print):
        return 'test', None

    def check(cache, tag, epub, large_kb=0, timeout=600):
        res = harness.Result(tag=tag)
        z = zipfile.ZipFile(epub)
        for name in z.namelist():
            if not name.lower().endswith(harness.HTML_EXT):
                continue
            res.chapters += 1
            data = z.read(name)
            try:
                expat.ParserCreate().Parse(data, True)
            except expat.ExpatError as e:
                res.problems.append(harness.Problem(name, 'chapter', 'not well-formed XML: %s' % e))
            if large_kb and len(data) > large_kb * 1024:
                res.warnings.append(harness.Problem(name, 'large', '%d KB in one chapter file' % (len(data) // 1024)))
        return res

    monkeypatch.setattr(harness, 'ensure', ensure)
    monkeypatch.setattr(harness, 'check', check)
