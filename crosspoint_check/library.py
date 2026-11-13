"""The Calibre library, on this machine or behind a command (usually SSH)."""
import hashlib
import json
import shlex
import subprocess

from . import agent


class LibraryError(Exception):
    pass


class Library:
    """`path` for a library on this machine, or `command` for a remote one.

    `command` is run with the agent's arguments appended (`list`, `get ID`,
    `put ID SIZE MTIME SHA256`); the other side decides which library it
    serves. See docs/remote-library.md.
    """

    def __init__(self, path=None, command=None, timeout=300):
        if bool(path) == bool(command):
            raise LibraryError('set exactly one of library.path and library.command')
        self.path = path
        self.command = shlex.split(command) if command else None
        self.timeout = timeout

    def _run(self, args, data=None):
        try:
            r = subprocess.run(self.command + [str(a) for a in args], input=data, capture_output=True,
                               timeout=self.timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise LibraryError('library not reachable: %s' % e) from None
        if r.returncode != 0:
            msg = r.stderr.decode('utf-8', 'replace').strip().splitlines()
            raise LibraryError(msg[-1] if msg else 'library command failed (exit %d)' % r.returncode)
        return r.stdout

    def list(self):
        try:
            if self.path:
                return agent.list_books(self.path)
            return json.loads(self._run(['list']))
        except agent.AgentError as e:
            raise LibraryError(str(e)) from None
        except ValueError:
            raise LibraryError('library command returned no book list') from None

    def get(self, book_id, dest):
        try:
            with open(dest, 'wb') as f:
                if self.path:
                    agent.get(self.path, book_id, f)
                else:
                    f.write(self._run(['get', book_id]))
        except agent.AgentError as e:
            raise LibraryError(str(e)) from None

    def put(self, book, src):
        """Replace `book` (an entry from list()) with the file `src`; returns the new entry."""
        with open(src, 'rb') as f:
            data = f.read()
        sha = hashlib.sha256(data).hexdigest()
        try:
            if self.path:
                return agent.put(self.path, book['id'], book['size'], book['mtime'], sha, data)
            return json.loads(self._run(['put', book['id'], book['size'], book['mtime'], sha], data))
        except agent.AgentError as e:
            raise LibraryError(str(e)) from None
        except ValueError:
            raise LibraryError('library command returned no answer to put') from None
