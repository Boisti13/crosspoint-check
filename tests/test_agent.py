import hashlib
import io
import json
import os

import pytest

from crosspoint_check import agent
from crosspoint_check.library import Library, LibraryError

from .conftest import GOOD, make_epub


def test_list_only_books_with_an_epub(library):
    books = agent.list_books(library)
    assert [b['id'] for b in books] == [1, 2]
    assert books[1]['author'] == 'Smith, John & Ann Author'
    assert books[0]['file'] == 'Ann Author/Good Book (1)/Good Book - Ann Author.epub'
    assert books[0]['size'] == os.path.getsize(os.path.join(library, books[0]['file']))


def test_get_returns_the_file(library):
    out = io.BytesIO()
    book = agent.get(library, 2, out)
    with open(os.path.join(library, book['file']), 'rb') as f:
        assert out.getvalue() == f.read()


def put_args(book, data):
    return book['size'], book['mtime'], hashlib.sha256(data).hexdigest(), data


def test_put_replaces_in_place(library, tmp_path):
    book = agent.find(library, 2)
    data = open(make_epub(tmp_path / 'new.epub', [GOOD]), 'rb').read()
    new = agent.put(library, 2, *put_args(book, data))
    assert new['file'] == book['file'] and new['size'] == len(data)
    assert open(os.path.join(library, new['file']), 'rb').read() == data
    assert not [n for n in os.listdir(os.path.dirname(os.path.join(library, new['file']))) if n.startswith('.')]


def test_put_refuses_a_book_that_changed(library, tmp_path):
    book = agent.find(library, 2)
    data = open(make_epub(tmp_path / 'new.epub', [GOOD]), 'rb').read()
    with pytest.raises(agent.AgentError, match='changed'):
        agent.put(library, 2, book['size'] + 1, book['mtime'], hashlib.sha256(data).hexdigest(), data)


def test_put_refuses_damaged_and_foreign_uploads(library, tmp_path):
    book = agent.find(library, 2)
    data = open(make_epub(tmp_path / 'new.epub', [GOOD]), 'rb').read()
    with pytest.raises(agent.AgentError, match='checksum'):
        agent.put(library, 2, book['size'], book['mtime'], '0' * 64, data)
    with pytest.raises(agent.AgentError, match='not an EPUB'):
        agent.put(library, 2, *put_args(book, b'hello'))
    assert agent.find(library, 2) == book


def test_not_a_library(tmp_path):
    with pytest.raises(agent.AgentError, match='metadata.db'):
        agent.list_books(str(tmp_path))


def test_command_line(library, capsysbinary):
    assert agent.main(['--library', library, 'list']) == 0
    assert len(json.loads(capsysbinary.readouterr().out)) == 2
    assert agent.main(['--library', library, 'get', '99']) == 1


def test_remote_library_through_a_command(library, tmp_path):
    import sys
    lib = Library(command='%s %s --library "%s"' % (sys.executable, agent.__file__, library))
    books = lib.list()
    assert len(books) == 2
    dest = tmp_path / 'got.epub'
    lib.get(2, str(dest))
    assert dest.stat().st_size == books[1]['size']
    new = lib.put(books[1], str(make_epub(tmp_path / 'new.epub', [GOOD])))
    assert new['size'] == (tmp_path / 'new.epub').stat().st_size
    with pytest.raises(LibraryError, match='changed'):
        lib.put(books[1], str(tmp_path / 'new.epub'))


def test_library_needs_exactly_one_source():
    with pytest.raises(LibraryError):
        Library()
    with pytest.raises(LibraryError):
        Library(path='/a', command='b')
