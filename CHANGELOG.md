# Changelog

## Unreleased

## v0.1.0 — 2026-11-13

First version.

### Added

- Check EPUBs with CrossPoint's own ZIP reader and chapter parser, built from
  the latest CrossPoint release (or a pinned one) on the machine itself.
- Scan a Calibre library for new and changed books every five minutes; a
  first pass covers the whole library.
- Repair books the reader refuses: chapters rewritten as well-formed XHTML
  with a charset line Calibre-Web-Automated's fixer leaves alone, oversized
  chapter files split at chapter starts. The repaired copy is tested before
  it replaces the book, and the original is kept.
- Report-only mode (`repair = false`, `scan --no-repair`); books reported
  that way are repaired once repairs are switched on.
- Status page with every book as *opens*, *repaired*, *cannot open* or
  *large chapter*, with chapter and reason, a short history and a browser
  tab icon.
- Webhook notification, one per scan that repaired a book or couldn't.
- Library on another machine through a single-file agent and a restricted
  SSH key (`deploy/ssh-gate.sh`, `docs/remote-library.md`).
- Command line: `check`, `fix` (optionally reworking pictures for a 480x800
  e-paper screen), `scan`, `page`.
- Installer and systemd units for Debian/Ubuntu, `scripts/deploy.sh` for a
  Proxmox container.
- README with two example setups: service next to the library, and service
  on another machine.

### Under the hood

- The library is only touched by `agent.py`: Calibre's `metadata.db` is read
  read-only, and a book is replaced only if it is still the file that was
  checked and the upload's checksum matches.
- If GitHub can't be reached or a new CrossPoint release doesn't build, the
  last built release is used and the page says so.
