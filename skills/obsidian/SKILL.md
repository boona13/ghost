---
name: obsidian
description: "Work with Obsidian vaults (plain Markdown notes) and automate via obsidian-cli"
triggers: ["obsidian", "vault", "markdown", "obsidian-cli", "wikilink"]
tools: ["shell_exec", "file_read", "file_write", "file_search"]
priority: 5
---
You are Ghost managing Obsidian vaults. Obsidian vaults are normal folders on disk with Markdown files.

## Vault Structure (typical)

- Notes: `*.md` (plain text Markdown; edit with any editor)
- Config: `.obsidian/` (workspace + plugin settings; usually don't touch from scripts)
- Canvases: `*.canvas` (JSON)
- Attachments: whatever folder configured in Obsidian settings (images/PDFs/etc.)

## Find the Active Vault(s)

Obsidian desktop tracks vaults here (source of truth):

- `~/Library/Application Support/obsidian/obsidian.json`

`obsidian-cli` resolves vaults from that file; vault name is typically the folder name.

### Fast vault lookup

- If default is set: `obsidian-cli print-default --path-only`
- Otherwise: read `~/Library/Application Support/obsidian/obsidian.json` and use the vault entry with `"open": true`.
- Multiple vaults are common (iCloud vs `~/Documents`, work/personal). Don't guess; read config.

## obsidian-cli Quick Start

Pick a default vault (once):

- `obsidian-cli set-default "<vault-folder-name>"`
- `obsidian-cli print-default` / `obsidian-cli print-default --path-only`

### Search

- `obsidian-cli search "query"` (note names)
- `obsidian-cli search-content "query"` (inside notes; shows snippets + lines)

### Create

- `obsidian-cli create "Folder/New note" --content "..." --open`
- Requires Obsidian URI handler (`obsidian://`) working.
- Avoid creating notes under hidden dot-folders.

### Move/Rename (safe refactor)

- `obsidian-cli move "old/path/note" "new/path/note"`
- Updates `[[wikilinks]]` and common Markdown links across the vault.

### Delete

- `obsidian-cli delete "path/note"`

## Direct File Editing

Since vault notes are plain `.md` files, you can also use Ghost's `file_read` and `file_write` tools to read and edit them directly. Obsidian will pick up changes automatically.

## Setup

- Install: `brew install yakitrak/yakitrak/obsidian-cli`

## Notes

- Avoid writing hardcoded vault paths; prefer reading the config or using `print-default`.
- Prefer `obsidian-cli move` over `mv` to keep wikilinks intact.
