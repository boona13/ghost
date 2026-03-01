---
name: x-account-creator
description: "Help users set up X/Twitter accounts — open signup page and guide them through"
triggers:
  - create x account
  - create twitter account
  - sign up x
  - sign up twitter
  - register x
  - register twitter
  - new x account
  - new twitter account
  - x account
  - twitter account
  - make x account
  - make twitter account
tools:
  - browser
  - email_create
  - email_inbox
  - email_read
  - credential_save
  - credential_get
  - credential_list
  - memory_save
priority: 10
---

# X/Twitter Account Setup

X signup requires CAPTCHAs and phone verification that cannot be automated. Your role is to **prepare everything and guide the user** through manual signup.

## Workflow

### Step 1: Prepare an email

Check for existing emails first:
```
credential_get(service="mail.tm")
```

If none exist, or all are used, create one:
```
email_create(notes="for X/Twitter account")
```

Tell the user the email address they should use for signup.

### Step 2: Open the signup page

```
browser(action='navigate', url='https://x.com/i/flow/signup')
```

Tell the user: "I've opened the X signup page in the Ghost browser. Please complete the signup using this email: **[the email]**. I can check for any verification emails that X sends."

### Step 3: Help with email verification

When the user reaches the email verification step, check the inbox:
```
email_inbox(email='the_email@domain.com')
```

If a verification email arrived, read it and give the user the code:
```
email_read(email='the_email@domain.com', message_id='the_id')
```

### Step 4: Save credentials after signup

Once the user confirms they've completed signup, ask for their chosen username and save:
```
credential_save(
  service="x.com",
  username="their_username",
  email="the_email@domain.com",
  password="their_password",
  notes="X/Twitter account"
)
```

Note: Only save the password if the user explicitly provides it. Otherwise save without it.

Also record the account creation for reference:
```
memory_save(
  content="Created X/Twitter account @their_username using email the_email@domain.com on YYYY-MM-DD",
  type="note",
  tags=["x-account", "social-media", "signup"]
)
```

### Step 5: Confirm

Tell the user:
- Their X account is set up
- Credentials are saved
- The Ghost browser preserves the login session, so Ghost can now perform actions (post, like, etc.) on their behalf using the x-growth skill

## Important

- **Never attempt to automate X signup** — CAPTCHAs and phone verification will block it
- **Do automate email verification** — use email_inbox/email_read to fetch codes for the user
- The Ghost browser session persists, so once logged in, Ghost can use the account going forward
