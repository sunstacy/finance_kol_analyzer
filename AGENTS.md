# AGENTS.md

## Cursor Cloud specific instructions

### Overview

This is a Python library and CLI tool (`finance-kol-analyzer`) for fetching YouTube video transcripts and metadata. It has no web server, no database, and no background services.

### Running tests

```bash
pytest -v
```

All tests use mocks/fakes and require no network access. They complete in under 1 second.

### Running the CLI

```bash
python src/run_transcript.py --input youtube_links.txt --output-dir transcripts/
```

**Important**: YouTube blocks requests from datacenter/cloud IPs. In a cloud VM the CLI will report `RequestBlocked` or "Sign in to confirm you're not a bot" errors. This is expected and does not indicate a code bug. To fetch real transcripts, configure a proxy via environment variables (see README.md) or run from a residential IP.

### Building

```bash
python -m build
```

### Key environment note

The package is installed in user site-packages (`~/.local/lib/python3.12/`). Ensure `~/.local/bin` is on `PATH` for `pytest` and other script entry points:

```bash
export PATH="$HOME/.local/bin:$PATH"
```
