"""What crosspoint-check remembers: one row per book, a short history, the last scan."""
import json
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
  id INTEGER PRIMARY KEY, title TEXT, author TEXT, file TEXT,
  size INTEGER, mtime INTEGER, status TEXT, tag TEXT, checked_at REAL,
  chapters INTEGER, problems TEXT, warnings TEXT, changes TEXT, original TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, book_id INTEGER, title TEXT, kind TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""
JSON_COLS = ('problems', 'warnings', 'changes')


class Store:
    def __init__(self, path):
        self.con = sqlite3.connect(path, timeout=30)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)

    def close(self):
        self.con.close()

    @staticmethod
    def _book(row):
        book = dict(row)
        for col in JSON_COLS:
            book[col] = json.loads(book[col] or '[]')
        return book

    def book(self, book_id):
        row = self.con.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
        return self._book(row) if row else None

    def books(self):
        return [self._book(r) for r in self.con.execute('SELECT * FROM books ORDER BY title COLLATE NOCASE')]

    def save(self, book):
        row = dict(book)
        for col in JSON_COLS:
            row[col] = json.dumps(row.get(col) or [])
        row.setdefault('original', None)
        row.setdefault('note', None)
        row['checked_at'] = time.time()
        cols = ['id', 'title', 'author', 'file', 'size', 'mtime', 'status', 'tag', 'checked_at',
                'chapters', 'problems', 'warnings', 'changes', 'original', 'note']
        self.con.execute('INSERT OR REPLACE INTO books (%s) VALUES (%s)' % (
            ', '.join(cols), ', '.join(':' + c for c in cols)), row)
        self.con.commit()

    def forget(self, keep_ids):
        gone = [r['id'] for r in self.con.execute('SELECT id FROM books') if r['id'] not in keep_ids]
        self.con.executemany('DELETE FROM books WHERE id = ?', [(i,) for i in gone])
        self.con.commit()
        return gone

    def event(self, book, kind, text):
        self.con.execute('INSERT INTO events (at, book_id, title, kind, text) VALUES (?, ?, ?, ?, ?)',
                         (time.time(), book['id'], book['title'], kind, text))
        self.con.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 200)')
        self.con.commit()

    def events(self, limit=30):
        return [dict(r) for r in self.con.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?', (limit,))]

    def set(self, key, value):
        self.con.execute('INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)', (key, json.dumps(value)))
        self.con.commit()

    def get(self, key, default=None):
        row = self.con.execute('SELECT value FROM meta WHERE key = ?', (key,)).fetchone()
        return json.loads(row['value']) if row else default
