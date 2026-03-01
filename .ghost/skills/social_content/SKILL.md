---
name: social_content
description: Create X/Twitter content, threads, and optimize posts for engagement. Use when the user wants to write tweets, create thread structures, generate images for social media, or improve content for their X account.
triggers:
  - write tweet
  - create tweet
  - twitter thread
  - x thread
  - social media post
  - tweet idea
  - thread ideas
  - content for x
  - content for twitter
  - viral tweet
  - engagement tweet
  - tweet hook
  - call to action
  - tweet with image
  - "@boona11"
  - my x account
  - my twitter
tools:
  - generate_image
  - web_search
  - browser
  - x_log_action
  - x_check_action
priority: 6
---

# Social Content Creation Skill

Create engaging X/Twitter content, threads, and optimize posts for maximum engagement. Tailored for tech/AI/ARVR creators like @boona11.

## When to Use

**✅ USE this skill when:**
- User asks to "write a tweet about..."
- Creating Twitter/X threads (multi-post stories)
- "I need content for my X account"
- "Help me post about..."
- Generating images for tweets
- Finding trending topics to tweet about
- Optimizing tweet hooks and CTAs
- Scheduling content ideas

**❌ DON'T use this skill when:**
- Replying to existing tweets (use browser automation)
- Automated liking/retweeting (use X growth tools)
- Analytics and stats review (use x_action_stats)
- Direct message automation

## Tweet Structure Best Practices

### The Hook (First Line)
- Lead with curiosity, controversy, or value
- Use numbers: "7 things I learned..."
- Ask questions: "Why do 90% of startups fail?"
- Bold statements: "AI agents are overhyped."
- Personal story: "I wasted 2 years on..."

### The Body
- Short lines (easy to read on mobile)
- One idea per line
- Use whitespace for breathing room
- Add specific details/examples
- Build tension or curiosity

### The CTA (Call to Action)
- Ask a question to drive replies
- "What's your experience?"
- "Drop a 🚀 if you agree"
- "Follow for more threads like this"
- Link to resource/thread continuation

## Thread Structure

**Thread Formula (5-7 posts):**

1. **Hook tweet** - The scroll-stopper (standalone value)
2. **Context** - Why this matters
3. **Point 1** - First key insight
4. **Point 2** - Second key insight
5. **Point 3** - Third key insight
6. **Summary/Action** - Wrap it up
7. **CTA** - Engagement prompt + follow CTA

**Thread Best Practices:**
- Number tweets: "1/7", "2/7", etc.
- Each tweet should standalone (people see random ones)
- Consistent formatting
- Save the best insight for the middle
- End with clear next step

## Content Types by Goal

### Thought Leadership (AI/ARVR Focus)
```
Hot take format:
"[Controversial opinion about AI/AR/tech]

Everyone thinks [common belief]

But actually [contrarian insight]

Here's why [brief explanation]

What's your take?"
```

### Educational Threads
```
"I spent [time] studying [topic]

Here are [number] lessons that will save you [benefit]:"
```

### Behind the Scenes
```
"Building [project] in public:

Day [X]: [What happened]

[Visual/description]

[Lesson learned]"
```

### Storytelling
```
"[Timeframe] ago, I was [struggling state]

[The turning point/inciting incident]

[The journey/struggle]

[The transformation/result]

[The lesson for reader]"
```

## Hashtag Strategy

**For @boona11's niche (AI/ARVR):**
- Primary: #AI #ARVR #MachineLearning
- Community: #LensStudio #SnapSpectacles #VFX
- Growth: #BuildingInPublic #IndieDev
- Limit: 1-2 hashtags max (looks cleaner)
- Better: Use keywords naturally in text

## Tools in Practice

This skill has access to several tools for content creation and X management:

### `generate_image` - Create Tweet Images
**When to use:**
- User asks for "tweet with image" or "visual content"
- Creating infographics, diagrams, or illustrations for threads
- Generating meme-style content
- Creating carousel/thread preview images

**Best practices:**
- Use `size: "landscape"` for tweet images (1200x675 optimal)
- Include key text from the tweet in the image prompt for consistency
- For tech/AI content: specify "clean design", "minimalist", or "tech aesthetic"
- Always generate images BEFORE composing the tweet text (so you can reference them)

**Example workflow:**
```
1. generate_image(prompt="Minimalist illustration of AI agent loop: prompt → LLM → action → evaluate → repair. Clean tech aesthetic, blue and white color scheme, diagram style", size="landscape")
2. Compose tweet referencing the generated image
```

### `x_log_action` - Track Posted Content
**When to use:**
- AFTER successfully posting a tweet via browser automation
- Logging manual posts the user confirms they made
- Tracking thread posts as a batch (log the first tweet URL)

**Why it matters:** Prevents duplicate posting if the user asks similar content later. The x_check_action tool references this log.

**Example:**
```python
x_log_action(
    action="post",
    target_id="https://x.com/boona11/status/1234567890",
    target_type="tweet",
    content="Just shipped a new AR lens..."
)
```

### `x_check_action` - Avoid Duplicates
**When to use:**
- BEFORE posting content similar to previous tweets
- User asks to "post about [topic]" — check if already posted recently
- Creating follow-up content (check if original was posted)

**Example workflow:**
```python
# Check if already posted about this topic today
already_posted = x_check_action(
    action="post",
    target_id="@boona11",
    hours=24
)
# If similar content found, suggest a different angle instead
```

### `browser` - Post to X
**When to use:**
- User explicitly asks to "post this tweet" or "publish to X"
- Scheduling content for immediate publication
- Replying to existing tweets

**Note:** Always confirm the exact tweet text with the user before posting via browser automation.

### `web_search` - Find Trending Topics
**When to use:**
- User asks "what's trending in AI/ARVR?"
- Finding timely hooks for content
- Researching competitor/industry tweets for inspiration

## Character Limits & Formatting

**X Character Limits (2026):**
- Standard: 280 characters per post
- X Premium: 500 characters per post
- @boona11 likely has Premium (tech creator account)

**Formatting tips:**
- Use line breaks for readability (counts as 1 char each)
- Links count as 23 characters (t.co wrapping)
- Unicode emojis count as 2 characters
- Thread numbering: "1/7 " at start = 4 characters

**Quick check:** If drafting a tweet, verify length before suggesting final version.

## Examples

**"Write a tweet about my new AR project"**
```
Just shipped a new Lens Studio effect that lets you paint in 3D space with hand tracking

The weird part? It runs at 60fps on Snap Spectacles

Building for AR glasses hits different when you can literally see your code come to life

Demo below 👇
```

**"Create a thread about AI agents"**
```
1/7 Everyone's building AI agents right now

But 90% of them will fail for the same reason

Here's what nobody's talking about 🧵

2/7 We keep building agents that NEED human supervision

That's not autonomy—that's automation with extra steps

True agents should handle edge cases without waking you up at 3am

3/7 The real breakthrough isn't better LLMs

It's giving agents the ability to:
- Self-diagnose failures
- Repair their own code
- Learn from mistakes without human labeling

4/7 Ghost has crashed 47 times this month

Each time, it read the error, fixed itself, and deployed the fix

I woke up to 47 "repair complete" notifications

That's what I call autonomous

5/7 Most "agents" are just:
Prompt → LLM → Action

Real agents need:
Prompt → LLM → Action → Evaluate → Repair → Retry

The loop matters more than the model

6/7 If your agent can't survive a weekend without you,
it's not an agent—it's a chatbot with ambitions

Build the loop first. Add intelligence second.

7/7 I'm documenting everything I'm learning about truly autonomous agents

Follow @boona11 for weekly breakdowns

What capability would YOU want in an autonomous agent?
```

**"Generate an image for my tweet about AI"**
```python
generate_image(
    prompt="Futuristic AI agent neural network visualization, dark background with glowing blue and purple connections, minimalist style, digital art",
    size="landscape",
    style="digital art"
)
```

## Content Research

**Find trending topics:**
```python
# Search for current AI/ARVR discussions
web_search(query="AR VR trends 2026", freshness="week")
web_search(query="AI agents latest developments 2026", freshness="day")
```

**Check what @boona11 recently posted:**
```python
x_action_history(hours=168, limit=20)  # Last 7 days
```

## Engagement Optimization

**Post Timing (Ibrahim's timezone UTC-5):**
- Best: 9-11am EST (tech Twitter is active)
- Good: 1-3pm EST (lunch scroll)
- Avoid: Late night EST (unless targeting EU)

**Engagement Tactics:**
- Reply to every comment in first 30 min (boosts algorithm)
- Quote tweet > Retweet (adds value)
- Threads > Long tweets (more impressions)
- Images/video = 2-3x engagement
- Questions in final tweet = more replies

## Image Guidelines

**Use generate_image when:**
- Explaining concepts (diagrams, workflows)
- Tweet needs visual hook
- Creating infographics/data viz
- Meme-style content

**Image specs for X:**
- Aspect: 16:9 (landscape) for tweets
- Style: Consistent with personal brand
- Text: Minimal, large fonts if any

## Notes

- @boona11 focuses on AR/VR, AI agents, and Lens Studio content
- Authenticity > Virality (build trust first)
- Consistency beats perfection (post regularly)
- Engage before broadcasting (reply to others first)
- Track what works via x_action_stats weekly
