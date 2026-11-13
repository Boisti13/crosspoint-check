# crosspoint-check — working rules

Public repo (MIT). Finds and repairs the EPUBs a CrossPoint e-reader refuses,
using the firmware's own parser. Read the README first.

- **Branches**: `dev` for work, `main` for releases. Push to `dev`. Merges to
  `main`, tags and GitHub releases only when the owner asks.
- **Public**: no private addresses, host names, book titles from a real
  library or paths of the owner's setup in code, docs, tests or screenshots.
  The screenshot comes from `scripts/demo.py` (made-up copies of
  public-domain titles), never from a real library. Where and how the
  owner's instance runs is in his private notes, not here.
- **Nothing copied from upstream.** CrossPoint's code is cloned and built at
  run time (`harness.py` appends two tests to its test files). Don't vendor
  CrossPoint or Calibre-Web-Automated code.
- **The library is someone's books.** Only `agent.py` touches it. It must
  stay standard-library-only and run on Python 3.9 (it is copied alone to
  other machines), never write to `metadata.db`, and replace a book only
  after the size/mtime and checksum checks. A repaired copy must pass the
  check before it is put back, and the original is kept. New behaviour that
  changes books needs a test.
- **Working books stay untouched** unless a setting says otherwise
  (`split_large`, off by default). Pictures are only changed with
  `images = true`.
- **Tests**: `ruff check .` and `python -m pytest -q` before every push. The
  suite uses a stand-in for the CrossPoint build; `tests/test_harness.py`
  runs against a real one when `CROSSPOINT_CHECK_TEST_CACHE` points at a
  cache folder with a build. Run those too after touching `harness.py`.
- **When CrossPoint changes its tests** and the build breaks: the service
  keeps using the last built release and says so on the page. Fix the
  appended test code in `harness.py` (`PARSER_TEST`, `ZIP_TEST`) against the
  new release and keep it working with the previous one where possible.
- **Docs**: README (house style: badges, intro, Highlights, tables, worked
  example, layout) and CHANGELOG (*Unreleased* on top) change with every
  user-visible change. Plain language: say what the reader does, not how the
  code is built.
- Version in `crosspoint_check/__init__.py`.
