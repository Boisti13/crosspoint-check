import zipfile
from xml.parsers import expat

from crosspoint_check import fixer

from .conftest import BROKEN, GOOD, make_epub

META = b'<meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>'


def chapters(path):
    z = zipfile.ZipFile(path)
    return {n: z.read(n) for n in z.namelist() if n.endswith('.xhtml')}


def test_mends_broken_chapters(tmp_path):
    src = make_epub(tmp_path / 'in.epub', [GOOD, BROKEN])
    report = fixer.fix(str(src), str(tmp_path / 'out.epub'))
    assert any('1 chapter files were not well-formed' in line for line in report)
    out = chapters(tmp_path / 'out.epub')
    assert len(out) == 2
    for data in out.values():
        expat.ParserCreate().Parse(data, True)
        assert META in data and b'<meta charset' not in data
        assert b'Hello world' in data


def test_mimetype_stays_first_and_stored(tmp_path):
    src = make_epub(tmp_path / 'in.epub', [GOOD])
    fixer.fix(str(src), str(tmp_path / 'out.epub'))
    first = zipfile.ZipFile(tmp_path / 'out.epub').infolist()[0]
    assert first.filename == 'mimetype' and first.compress_type == zipfile.ZIP_STORED


def test_splits_a_large_file_at_chapter_anchors(tmp_path):
    para = '<p>%s</p>' % ('word ' * 400)
    body = ''.join('<h1 id="ch%d">Chapter %d</h1>%s' % (i, i, para * 30) for i in range(4))
    big = GOOD.replace('<p>Hello world</p>', body + '<p><a href="#ch2">back to two</a></p>')
    ncx = ('<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>%s</navMap></ncx>'
           % ''.join('<navPoint id="n%d"><navLabel><text>%d</text></navLabel><content src="c0.xhtml#ch%d"/>'
                     '</navPoint>' % (i, i, i) for i in range(4)))
    src = make_epub(tmp_path / 'in.epub', [big], ncx=ncx)
    report = fixer.fix(str(src), str(tmp_path / 'out.epub'), max_kb=100)
    assert any('split into 4 files' in line for line in report)
    z = zipfile.ZipFile(tmp_path / 'out.epub')
    out = chapters(tmp_path / 'out.epub')
    assert sorted(out) == ['OEBPS/c0_%03d.xhtml' % i for i in range(4)]
    assert all(len(d) < 100 * 1024 for d in out.values())
    toc = z.read('OEBPS/toc.ncx').decode()
    assert 'src="c0_002.xhtml#ch2"' in toc and 'c0.xhtml' not in toc
    assert b'href="c0_002.xhtml#ch2"' in out['OEBPS/c0_003.xhtml']
    opf = z.read('OEBPS/content.opf').decode()
    assert opf.count('<itemref') == 4 and 'href="c0.xhtml"' not in opf
