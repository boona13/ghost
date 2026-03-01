---
name: email-creator
description: "Create free email accounts instantly via API and manage inbox — no browser needed"
triggers:
  - create email
  - email account
  - new email
  - sign up email
  - register email
  - make email
  - make me an email
  - create an email
  - i need an email
  - email registration
  - check email
  - check inbox
  - read email
  - email inbox
tools:
  - email_create
  - email_inbox
  - email_read
  - credential_save
  - credential_get
  - credential_list
priority: 9
---

# Email Account Manager

You create and manage free email accounts using the **mail.tm API**. No browser needed, no captcha, no phone verification, works instantly.

## Creating a New Email Account

Use the `email_create` tool. It handles everything automatically:

```
email_create(username="desired_name", notes="for social media growth")
```

- If no username is given, one is auto-generated
- A strong password is auto-generated
- The account is created via API (no browser)
- Credentials are saved automatically to the credential store
- The email is immediately ready to receive messages

If the username is taken, the tool retries with a random one.

**After creating**, tell the user:
- The full email address (e.g. `ghostuser42@dollicons.com`)
- That credentials are saved securely
- That they can check the inbox anytime with `email_inbox`

Do NOT paste the password in your response — it's stored securely and retrievable via `credential_get`.

## Checking the Inbox

```
email_inbox(email="user@domain.com")
```

Shows all messages with sender, subject, date, and message IDs. Useful for:
- Finding verification emails after signing up for social media
- Checking for confirmation links
- Monitoring incoming mail

## Reading a Specific Email

```
email_read(email="user@domain.com", message_id="abc123")
```

Returns the full email body. Use this to extract:
- Verification codes
- Confirmation links
- Password reset links

## Retrieving Saved Credentials

```
credential_get(service="mail.tm")
```

Or list all accounts:

```
credential_list()
```

## Important Rules

- **Always use `email_create`** — never try to create emails via browser, it will fail
- The email domain changes periodically (mail.tm rotates domains) — always let the tool pick the current active domain
- These accounts are real and persistent — they can receive emails from any service
- Perfect for signing up on social media platforms that need email verification
- If the user asks to create multiple accounts, create them one at a time
