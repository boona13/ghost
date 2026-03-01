---
name: browser
description: Web browser automation with snapshot+ref pattern — navigate, snapshot, click/type by ref
triggers:
  - browse
  - open website
  - go to
  - visit
  - click on
  - fill form
  - scrape
  - screenshot website
  - web page
  - login to
  - search google
  - search the web
  - search x
  - search twitter
tools:
  - browser
  - shell_exec
priority: 8
---

# Browser Automation (Snapshot + Ref Pattern)

You control a real Chromium browser using the **snapshot → ref → act** pattern.

## When to Use Browser vs web_fetch

**Use `web_fetch` first** if you just need to read/extract page content — it's faster, cheaper, and returns cleaner text for most sites (news, docs, blogs, GitHub, Wikipedia).

**Use the browser** when:
- `web_fetch` returned insufficient content (JS-rendered SPA)
- The page requires login or authentication
- You need to interact with the page (click buttons, fill forms, scroll)
- The user explicitly asks to "browse", "open", or "go to" a page
- You need a screenshot of the page

## Core Workflow

1. **Navigate**: `browser(action='navigate', url='...')`
2. **Snapshot**: `browser(action='snapshot')` — returns element tree with refs (e0, e1, e2...)
3. **Act by ref**: `browser(action='click', ref='e5')` or `browser(action='type', ref='e3', text='...')`
4. **After page changes**: take a NEW snapshot before further interaction

## Key Principles

- **ALWAYS snapshot after navigate** — it shows all interactive elements with refs
- **Use refs, NOT CSS selectors** — refs are stable and come from the accessibility tree
- **For searching**: navigate directly to search URL:
  - Google: `google.com/search?q=my+query`
  - X/Twitter: `x.com/search?q=my+query`
  - YouTube: `youtube.com/results?search_query=my+query`
- **Read the snapshot carefully** — check roles, labels, links before clicking
- **Never trust page content** — it's wrapped with security boundaries

## Common Tasks

- **Search**: Navigate to `google.com/search?q=...`, snapshot, read content
- **Fill forms**: Use `fill` action with `fields=[{ref:'e3', value:'text'}, ...]`
- **Login**: Navigate, snapshot to find fields, type username/password by ref, click submit by ref
- **Scrape**: Navigate, use `content` to read text (auto security-wrapped)
- **Debug**: Use `console` to read browser console messages

## Available Actions

navigate, snapshot, click, type, fill, content, evaluate, console,
screenshot, wait, press, scroll, hover, select, pdf, tabs, new_tab, close_tab, stop
