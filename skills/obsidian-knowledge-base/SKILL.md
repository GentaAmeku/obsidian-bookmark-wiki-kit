---
name: obsidian-knowledge-base
description: Use this skill to initialize and maintain an Obsidian bookmark wiki, including installing the skill from this repository, creating vaults, ingesting Chrome AI Inbox bookmarks into Source Notes, querying notes, creating Knowledge Notes, and generating daily reviews.
---

# Obsidian Knowledge Base

Use this skill when the user wants to set up or operate an Obsidian bookmark wiki from this repository.

## Repository Layout

The skill is intentionally bundled in the repository:

```txt
skills/obsidian-knowledge-base/
├── SKILL.md
├── agents/openai.yaml
└── scripts/obsidian_kb.py
```

## Initial Setup Workflow

When the user asks to initialize a wiki from this repo:

1. Ask only for missing critical values:
   - vault path
   - bookmark folder name, default `AI Inbox`
   - optional Chrome profile
   - whether to initialize Git / GitHub
2. Install the skill into `$CODEX_HOME/skills`:

```bash
python3 skills/obsidian-knowledge-base/scripts/obsidian_kb.py install-skill
```

3. Create the vault:

```bash
python3 skills/obsidian-knowledge-base/scripts/obsidian_kb.py init-vault --root /path/to/vault --bookmark-folder "AI Inbox"
```

4. If requested, initialize Git in the created vault.

## Operating Commands

Installed skill command:

```bash
python3 ~/.codex/skills/obsidian-knowledge-base/scripts/obsidian_kb.py --help
```

Ingest bookmarks:

```bash
python3 ~/.codex/skills/obsidian-knowledge-base/scripts/obsidian_kb.py --root /path/to/vault ingest-bookmarks
```

Ingest one URL, including PDF / Excel / Office document URLs:

```bash
python3 ~/.codex/skills/obsidian-knowledge-base/scripts/obsidian_kb.py --root /path/to/vault ingest-url "https://example.com/article"
```

Query:

```bash
python3 ~/.codex/skills/obsidian-knowledge-base/scripts/obsidian_kb.py --root /path/to/vault query "react compiler"
```

Daily review:

```bash
python3 ~/.codex/skills/obsidian-knowledge-base/scripts/obsidian_kb.py --root /path/to/vault daily
```

## Rules

- Prefer Japanese output if the user writes Japanese.
- The bookmark folder default is `AI Inbox`, but it must be configurable.
- Do not store full article text in Source Notes; store summary, key points, short quotes, memo, and related links.
- File slugs should be ASCII.
- Internal links use Wikilink syntax.
- X/Twitter ingestion may use Hermes if available; otherwise create a metadata-only note.
- YouTube ingestion may use `yt-dlp` if available; otherwise mark `asr_required`.
- PDF / Excel / Word / PowerPoint document URLs should use MarkItDown when available and store extracted Markdown under `assets/extracted/`.
