import os
import zipfile

import pytest

from crosspoint_check import config, notify, page, service
from crosspoint_check.store import Store

from .conftest import BROKEN, GOOD, make_epub


@pytest.fixture
def cfg(tmp_path, library):
    return config.Config(library_path=library, state=str(tmp_path / 'state'))


def statuses(cfg):
    store = Store(cfg.db)
    try:
        return {b['id']: b for b in store.books()}
    finally:
        store.close()


def test_scan_repairs_the_broken_book_and_keeps_the_original(cfg, library, fake_harness):
    broken = os.path.join(library, 'Smith, John/Broken Book (2)/Broken Book - John Smith.epub')
    before = open(broken, 'rb').read()
    assert service.scan(cfg, log=lambda m: None) == 0
    books = statuses(cfg)
    assert books[1]['status'] == 'ok' and books[2]['status'] == 'repaired'
    assert open(broken, 'rb').read() != before
    assert open(books[2]['original'], 'rb').read() == before
    assert books[2]['problems'][0]['file'] == 'OEBPS/c1.xhtml'
    assert b'<meta charset' not in zipfile.ZipFile(broken).read('OEBPS/c1.xhtml')
    html = open(os.path.join(cfg.www, 'index.html')).read()
    assert 'Broken &lt;Book&gt;' in html and '<Book>' not in html


def test_second_scan_checks_nothing_and_changes_nothing(cfg, library, fake_harness):
    service.scan(cfg, log=lambda m: None)
    lines = []
    service.scan(cfg, log=lines.append)
    assert lines == []
    assert statuses(cfg)[2]['status'] == 'repaired'
    assert len(os.listdir(cfg.originals)) == 1


def test_forced_scan_keeps_saying_repaired(cfg, fake_harness):
    service.scan(cfg, log=lambda m: None)
    service.scan(cfg, force=True, log=lambda m: None)
    book = statuses(cfg)[2]
    assert book['status'] == 'repaired' and book['original'] and book['problems']
    assert len(os.listdir(cfg.originals)) == 1


def test_no_repair_only_reports(cfg, library, fake_harness):
    broken = os.path.join(library, 'Smith, John/Broken Book (2)/Broken Book - John Smith.epub')
    before = open(broken, 'rb').read()
    service.scan(cfg, repair=False, log=lambda m: None)
    assert statuses(cfg)[2]['status'] == 'failed'
    assert open(broken, 'rb').read() == before
    assert not os.path.exists(cfg.originals)
    # ... and a later scan with repair on picks it up, though the file did not change.
    service.scan(cfg, log=lambda m: None)
    assert statuses(cfg)[2]['status'] == 'repaired'


def test_changed_book_is_checked_again(cfg, library, fake_harness):
    service.scan(cfg, log=lambda m: None)
    good = os.path.join(library, 'Ann Author/Good Book (1)/Good Book - Ann Author.epub')
    make_epub(good, [GOOD, GOOD, BROKEN])
    lines = []
    service.scan(cfg, log=lines.append)
    assert len(lines) == 1 and lines[0].startswith('repaired')


def test_removed_book_is_forgotten(cfg, library, fake_harness):
    service.scan(cfg, log=lambda m: None)
    os.unlink(os.path.join(library, 'Ann Author/Good Book (1)/Good Book - Ann Author.epub'))
    service.scan(cfg, log=lambda m: None)
    assert list(statuses(cfg)) == [2]


def test_large_chapter_is_a_note_unless_split_large(cfg, library, fake_harness):
    good = os.path.join(library, 'Ann Author/Good Book (1)/Good Book - Ann Author.epub')
    big = GOOD.replace('<p>Hello world</p>', '<p>%s</p>' % ('word ' * 300) * 300)
    make_epub(good, [big])
    cfg.large_kb = 100
    service.scan(cfg, log=lambda m: None)
    assert statuses(cfg)[1]['status'] == 'warning'
    cfg.split_large = True
    service.scan(cfg, log=lambda m: None)
    book = statuses(cfg)[1]
    assert book['status'] == 'repaired' and not book['warnings']


def test_unreachable_library_is_reported_on_the_page(tmp_path, fake_harness):
    cfg = config.Config(library_command='false', state=str(tmp_path / 'state'))
    assert service.scan(cfg, log=lambda m: None) == 1
    assert 'The last scan stopped' in open(os.path.join(cfg.www, 'index.html')).read()


def test_one_notification_per_scan(cfg, fake_harness, monkeypatch):
    sent = []
    monkeypatch.setattr(notify, 'send', lambda url, repaired, failed, page_url, log: sent.append((repaired, failed)))
    service.scan(cfg, log=lambda m: None)
    service.scan(cfg, log=lambda m: None)
    assert [b['title'] for b in sent[0][0]] == ['Broken <Book>'] and sent[0][1] == []
    assert sent[1] == ([], [])
    assert notify.summary(sent[0][0], []) == 'repaired Broken <Book>'


def test_empty_page(tmp_path):
    store = Store(str(tmp_path / 's.db'))
    html = page.render(store)
    assert 'No books checked yet' in html
    assert '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,' in html
