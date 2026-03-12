---
name: google_workspace
description: Manage Gmail, Google Calendar, Drive, Docs, and Sheets. Use when the user wants to read/send emails, check/create calendar events, manage files in Drive, edit documents, or work with spreadsheets.
triggers:
  - email
  - gmail
  - inbox
  - send email
  - read email
  - check email
  - unread messages
  - calendar
  - schedule
  - meeting
  - event
  - appointment
  - google drive
  - drive files
  - upload file
  - download file
  - share file
  - google docs
  - document
  - write document
  - google sheets
  - spreadsheet
  - create spreadsheet
  - what's on my calendar
  - any meetings
  - draft email
  - reply to
  - upcoming events
  - schedule a meeting
  - create event
  - find file
  - search drive
tools:
  - google_gmail
  - google_calendar
  - google_drive
  - google_docs
  - google_sheets
  - web_search
priority: 7
content_types:
  - email
  - calendar
  - document
  - spreadsheet
---

# Google Workspace Skill

Manage Gmail, Google Calendar, Google Drive, Google Docs, and Google Sheets through natural language. Handle email triage, calendar management, document creation, and spreadsheet operations.

## When to Use

**✅ USE this skill when:**
- User asks about email: "Check my inbox", "Send an email to...", "Any unread messages?"
- Calendar queries: "What's on my calendar?", "Schedule a meeting", "Am I free tomorrow?"
- Drive operations: "Find that PDF", "Upload this file", "Share with..."
- Document work: "Create a doc about...", "Update the meeting notes"
- Spreadsheet tasks: "Create a spreadsheet", "Add data to the sheet", "Read the budget"

**❌ DON'T use this skill when:**
- User wants to compose social media posts (use social_content)
- General web research not related to their workspace (use web_research)
- Code analysis or development tasks (use code_analysis)

## Gmail

### Reading Email

**Check inbox for unread messages:**
```python
google_gmail(action="list_messages", label_ids=["INBOX", "UNREAD"], max_results=10)
```

**Read a specific message:**
```python
google_gmail(action="get_message", message_id="msg_id_here")
```

**Search for specific emails:**
```python
# By sender
google_gmail(action="search", query="from:alice@example.com")

# By subject
google_gmail(action="search", query="subject:invoice is:unread")

# Recent important emails
google_gmail(action="search", query="is:important newer_than:7d")

# With attachments
google_gmail(action="search", query="has:attachment from:boss@company.com")
```

### Sending Email

**Send a new email:**
```python
google_gmail(
    action="send_message",
    to="recipient@example.com",
    subject="Meeting Follow-up",
    body="Hi, just following up on our discussion..."
)
```

**Send with CC/BCC:**
```python
google_gmail(
    action="send_message",
    to="main@example.com",
    cc="team@example.com",
    bcc="manager@example.com",
    subject="Project Update",
    body="Here's the latest update..."
)
```

**Create a draft (for review before sending):**
```python
google_gmail(
    action="create_draft",
    to="recipient@example.com",
    subject="Draft: Proposal",
    body="Draft content here..."
)
```

### Email Management

**Label/organize messages:**
```python
google_gmail(action="modify_message", message_id="msg_id", add_labels=["STARRED"])
google_gmail(action="modify_message", message_id="msg_id", remove_labels=["UNREAD"])
```

**Trash a message:**
```python
google_gmail(action="trash_message", message_id="msg_id")
```

**List available labels:**
```python
google_gmail(action="list_labels")
```

### Email Best Practices

- **Never store email content verbatim in memory** — summarize only
- **Always confirm before sending** — especially for new contacts
- **Use create_draft for important emails** — let the user review first
- **Search before listing** — targeted queries are faster than scanning inbox
- **Respect privacy** — don't read emails unless explicitly asked

## Google Calendar

### Viewing Events

**Today's schedule:**
```python
google_calendar(
    action="list_events",
    time_min="2026-02-27T00:00:00-05:00",
    time_max="2026-02-27T23:59:59-05:00",
    max_results=20
)
```

**This week's events:**
```python
google_calendar(
    action="list_events",
    time_min="2026-02-27T00:00:00-05:00",
    time_max="2026-03-06T23:59:59-05:00"
)
```

**Check a specific event:**
```python
google_calendar(action="get_event", event_id="event_id_here")
```

### Creating Events

**Quick add (recommended for most cases):**
```python
google_calendar(action="quick_add", text="Lunch with Bob tomorrow at noon")
```

**Create a structured event (timed):**
```python
google_calendar(
    action="create_event",
    summary="Team Standup",
    start={"dateTime": "2026-03-12T10:00:00", "timeZone": "America/New_York"},
    end={"dateTime": "2026-03-12T10:30:00", "timeZone": "America/New_York"},
    description="Weekly sync",
    location="Zoom"
)
```

**Create on a specific calendar:**
```python
google_calendar(
    action="create_event",
    calendar_id="primary",
    summary="Design Review",
    start={"dateTime": "2026-03-13T14:00:00", "timeZone": "America/New_York"},
    end={"dateTime": "2026-03-13T15:00:00", "timeZone": "America/New_York"},
    description="Review updated mocks",
    location="Conference Room B"
)
```

### Managing Events

**Update an event:**
```python
google_calendar(
    action="update_event",
    event_id="event_id_here",
    summary="Updated: Team Standup",
    location="Conference Room B"
)
```

**Delete an event:**
```python
google_calendar(action="delete_event", event_id="event_id_here")
```

### Calendar Best Practices

- **Use the user's timezone** (check USER.md for timezone preference)
- **Prefer `quick_add` for date/time-specific requests** (natural language parsing is robust)
- **Use ISO 8601 for `time_min` / `time_max` in list queries**
- **If attendees/invites are required, confirm capability first** (do not assume unsupported fields)
- **Check for conflicts** before scheduling — list events for that time window first

## Google Drive

### Finding Files

**List recent files:**
```python
google_drive(action="list_files", page_size=10)
```

**Search by name:**
```python
google_drive(action="search", query="project proposal")
```

**Filter by type:**
```python
# PDFs only
google_drive(action="list_files", query="mimeType='application/pdf'")

# Google Docs only
google_drive(action="list_files", query="mimeType='application/vnd.google-apps.document'")

# Spreadsheets only
google_drive(action="list_files", query="mimeType='application/vnd.google-apps.spreadsheet'")
```

### File Operations

**Get file details:**
```python
google_drive(action="get_file", file_id="file_id_here")
```

**Download a file:**
```python
google_drive(action="download_file", file_id="file_id_here")
```

**Upload a text file:**
```python
google_drive(
    action="upload_file",
    name="notes.txt",
    content="Meeting notes from today...",
    mime_type="text/plain"
)
```

**Upload to a specific folder:**
```python
google_drive(
    action="upload_file",
    name="report.csv",
    content="Name,Score\nAlice,95\nBob,87",
    mime_type="text/csv",
    folder_id="folder_id_here"
)
```

### Folders and Sharing

**Create a folder:**
```python
google_drive(action="create_folder", name="Q1 Reports")
```

**Create a subfolder:**
```python
google_drive(action="create_folder", name="February", parent_id="parent_folder_id")
```

**Share a file:**
```python
# Read-only access
google_drive(action="share_file", file_id="file_id", email="colleague@example.com", role="reader")

# Edit access
google_drive(action="share_file", file_id="file_id", email="collaborator@example.com", role="writer")
```

## Google Docs

### Creating Documents

**Create a new document:**
```python
google_docs(action="create_document", title="Meeting Notes - Feb 27")
```

### Reading Documents

**Get document content:**
```python
google_docs(action="get_document", document_id="doc_id_here")
```

### Editing Documents

**Insert text at the beginning:**
```python
google_docs(
    action="insert_text",
    document_id="doc_id",
    text="# Project Update\n\nHere are the latest developments...\n",
    index=1
)
```

**Find and replace text:**
```python
google_docs(
    action="replace_text",
    document_id="doc_id",
    old_text="DRAFT",
    new_text="FINAL"
)
```

**Advanced formatting (raw API):**
```python
google_docs(
    action="update_document",
    document_id="doc_id",
    requests=[
        {
            "insertText": {
                "location": {"index": 1},
                "text": "Bold Title\n"
            }
        },
        {
            "updateTextStyle": {
                "range": {"startIndex": 1, "endIndex": 11},
                "textStyle": {"bold": True},
                "fields": "bold"
            }
        }
    ]
)
```

## Google Sheets

### Creating Spreadsheets

**Create with custom sheets:**
```python
google_sheets(
    action="create_spreadsheet",
    title="Budget Tracker",
    sheet_titles=["Income", "Expenses", "Summary"]
)
```

### Reading Data

**Read a range:**
```python
google_sheets(action="get_values", spreadsheet_id="sheet_id", range="Sheet1!A1:D10")
```

**Read entire sheet:**
```python
google_sheets(action="get_values", spreadsheet_id="sheet_id", range="Sheet1")
```

**Get spreadsheet metadata:**
```python
google_sheets(action="get_spreadsheet", spreadsheet_id="sheet_id")
```

### Writing Data

**Update specific cells:**
```python
google_sheets(
    action="update_values",
    spreadsheet_id="sheet_id",
    range="Sheet1!A1:C2",
    values=[
        ["Name", "Email", "Role"],
        ["Alice", "alice@example.com", "Developer"]
    ]
)
```

**Append rows (add to end):**
```python
google_sheets(
    action="append_values",
    spreadsheet_id="sheet_id",
    range="Sheet1!A:C",
    values=[
        ["New Entry", "data@example.com", "Designer"],
        ["Another", "more@example.com", "PM"]
    ]
)
```

**Clear a range:**
```python
google_sheets(action="clear_values", spreadsheet_id="sheet_id", range="Sheet1!A2:C100")
```

**Add a new sheet tab:**
```python
google_sheets(action="add_sheet", spreadsheet_id="sheet_id", title="Q2 Data")
```

## Common Workflows

### Morning Briefing
```python
# 1. Check today's calendar window (ISO timestamps)
events = google_calendar(
    action="list_events",
    time_min="2026-03-12T00:00:00-05:00",
    time_max="2026-03-12T23:59:59-05:00",
    order_by="startTime",
    max_results=20
)

# 2. Check unread emails
emails = google_gmail(action="list_messages", label_ids=["INBOX", "UNREAD"], max_results=5)

# 3. Summarize for the user (never store verbatim)
```

### Email Triage
```python
# 1. List unread
unread = google_gmail(action="list_messages", label_ids=["INBOX", "UNREAD"], max_results=20)

# 2. Read each and categorize
for msg in unread:
    content = google_gmail(action="get_message", message_id=msg["id"])
    # Summarize: urgent, FYI, promotional, etc.

# 3. Present summary to user with recommended actions
```

### Meeting Prep
```python
# 1. Get event details
event = google_calendar(action="get_event", event_id="event_id")

# 2. Search for related emails (replace with a concrete topic string)
emails = google_gmail(action="search", query="subject:Design Review newer_than:30d")

# 3. Find related Drive files
files = google_drive(action="search", query="Design Review")

# 4. Create prep doc
google_docs(action="create_document", title="Prep: Design Review")
```

### Data Collection to Sheets
```python
# 1. Create or find spreadsheet
sheet = google_sheets(action="create_spreadsheet", title="Research Data")

# 2. Add headers
google_sheets(action="update_values", spreadsheet_id=sheet_id, range="Sheet1!A1:D1",
    values=[["Date", "Source", "Finding", "Relevance"]])

# 3. Append data rows as collected
google_sheets(action="append_values", spreadsheet_id=sheet_id, range="Sheet1!A:D",
    values=[["2026-02-27", "TechCrunch", "New AI model released", "High"]])
```

## Security & Privacy Rules

- **Never store email body text in memory** — save summaries only
- **Never log calendar event details** with attendee emails in growth logs
- **Always confirm before sending emails** — use create_draft when unsure
- **Always confirm before creating events with attendees** — sends real invites
- **Never share files without explicit user permission**
- **Don't read emails proactively** — only when the user asks or during authorized context routines
- **Summarize, don't quote** — when reporting email content, paraphrase

## Notes

- Check USER.md for the user's timezone — always use it for calendar operations
- Gmail search uses the same query syntax as the Gmail web interface
- Drive file IDs can be extracted from Google URLs: `docs.google.com/document/d/{ID}/edit`
- Sheets ranges use A1 notation: `Sheet1!A1:C10`
- Calendar `quick_add` is the fastest way to create simple events
- Calendar examples in this skill intentionally use currently supported `google_calendar` parameters.
- If calendar tool schema expands, update examples in this file to match the tool definition.
