"""Runs against a real CrossPoint build. Needs CROSSPOINT_CHECK_TEST_CACHE (a cache
folder with a built release; `crosspoint-check check --cache DIR book.epub` makes one)."""
import os

import pytest

from crosspoint_check import harness

from .conftest import BROKEN, GOOD, make_epub

CACHE = os.environ.get('CROSSPOINT_CHECK_TEST_CACHE', '')
pytestmark = pytest.mark.skipif(not harness.built_tags(CACHE), reason='no CrossPoint build (CROSSPOINT_CHECK_TEST_CACHE)')


@pytest.fixture
def tag():
    return harness.built_tags(CACHE)[0]


def test_good_book_passes(tmp_path, tag):
    res = harness.check(CACHE, tag, str(make_epub(tmp_path / 'a.epub', [GOOD, GOOD])))
    assert res.ok and res.chapters == 2 and not res.warnings


def test_unclosed_meta_is_refused(tmp_path, tag):
    res = harness.check(CACHE, tag, str(make_epub(tmp_path / 'a.epub', [GOOD, BROKEN])))
    assert [(p.file, p.kind) for p in res.problems] == [('OEBPS/c1.xhtml', 'chapter')]
    assert 'mismatched tag' in res.problems[0].detail


def test_large_chapter_is_noted(tmp_path, tag):
    big = GOOD.replace('<p>Hello world</p>', '<p>%s</p>' % ('word ' * 300) * 100)
    res = harness.check(CACHE, tag, str(make_epub(tmp_path / 'a.epub', [big])), large_kb=100)
    assert res.ok and [p.kind for p in res.warnings] == ['large']


def test_not_a_zip(tmp_path, tag):
    p = tmp_path / 'a.epub'
    p.write_text('hello')
    res = harness.check(CACHE, tag, str(p))
    assert not res.ok and res.problems[0].kind == 'zip'
