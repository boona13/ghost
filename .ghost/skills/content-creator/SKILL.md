---
name: content-creator
description: Expert guidance for research-backed content creation using AI tools. Use this skill when the user wants to create social media posts, blog articles, threads, newsletters, or any content that requires research and AI assistance. Covers research, writing, image generation, and publishing workflows.
triggers:
  - create content
  - write a post
  - research and write
  - social media content
  - blog post
  - thread
  - newsletter
  - content idea
  - generate content
  - draft post
  - write article
  - X post
  - twitter content
  - linkedin post
  - medium article
  - content strategy
priority: 8
tools:
  - web_search
  - grok_api
  - generate_image
  - file_read
  - file_write
  - browser
  - memory_save
  - memory_search
---

# Content Creator Guide

This skill provides expert guidance for creating high-quality, research-backed content using Ghost's AI tools. From quick social posts to long-form articles.

## Content Creation Workflow

### 1. Research Phase

Always start with research to ground your content in facts and current information:

```
Use web_search to find:
- Current news and trends on your topic
- Statistics and data points
- Expert opinions and quotes
- Competitor content (for differentiation)
- Recent developments (last 30 days for news)
```

**Research Strategy:**
- Search for "[topic] 2026" to get current information
- Look for 3-5 key sources to cite or reference
- Note any surprising stats or counter-intuitive findings
- Check what angles competitors have already covered

### 2. Ideation & Angle Selection

Use research to find a unique angle:

```
Questions to ask yourself:
- What surprised me in the research?
- What's the contrarian take here?
- What practical advice is missing?
- Can I connect this to a personal story?
- Is there a data-driven insight to highlight?
```

### 3. Drafting with AI Assistance

Use grok_api for writing assistance:

**For Social Media Posts:**
- Prompt: "Write a [tone] post about [topic] based on this research: [summary]. Include hook, 2-3 key points, and CTA. Keep under [X] characters."
- Review and edit for voice consistency
- Add line breaks for readability

**For Threads:**
- Prompt: "Create a [N]-post thread about [topic]. First post must hook. Each post should flow logically. Include data point in post 3. End with engagement question."
- Check: Does each post stand alone while connecting to the next?

**For Blog Articles:**
- Prompt: "Write a [length] article on [topic] with: compelling intro, 3-4 H2 sections, practical takeaways, conclusion with CTA. Target audience: [description]."
- Use file_write to save drafts for iteration

### 4. Visual Content Creation

Generate images to boost engagement (posts with images get 2-3x more engagement):

```
Use generate_image with:
- Detailed description of scene/subject
- Style hint (illustration, photorealistic, minimalist, etc.)
- Landscape for posts/tweets
- Portrait for stories
- Square for profile images
```

**Image Prompt Tips:**
- Be specific about composition, colors, mood
- Mention lighting (natural, studio, dramatic)
- Include style references ("digital art style", "corporate illustration")
- Specify aspect ratio needs

### 5. Publishing & Scheduling

**For X/Twitter:**
- Use browser to navigate to x.com
- Use paste_image to attach generated images
- Schedule via x.com or third-party tools
- Log your post with x_log_action to prevent duplicates

**For LinkedIn:**
- Longer-form performs better
- Use browser automation for posting
- Tag relevant people (manually, not automated)

**For Blogs:**
- Save drafts to files for review
- Use browser to publish to Medium/Substack
- Cross-post with canonical links

## Platform-Specific Best Practices

### X/Twitter
- Optimal length: 200-280 characters (allows room for quote RTs)
- Hooks: Start with unexpected statement or question
- Format: Use line breaks, bullet points, emoji sparingly
- Engagement: End with question or controversial take
- Images: 1200x675 (16:9) for horizontal, 1080x1350 for vertical

### LinkedIn
- Length: 1,200-1,500 characters performs best
- Structure: Hook → Story/Insight → Lesson → CTA
- Personal stories outperform pure advice
- Use 3-5 hashtags maximum
- Native video and documents (PDFs) get priority in algorithm

### Threads (X)
- First tweet: Pure hook, no context needed
- Number tweets: 5-12 is the sweet spot
- Each tweet should add value individually
- Connect tweets with "→" or "(1/10)" format
- Save the best insight for the middle
- Final tweet: CTA or thought-provoking question

### Blog/Medium
- Length: 1,500-3,000 words for SEO
- Structure: Hook intro → H2 sections → Summary
- Use data, quotes, and examples
- Include table of contents for long posts
- End with email signup or related content CTA

## Content Templates

### The Contrarian Take
```
"Everyone says [common belief].

They're wrong.

Here's what actually matters:

1. [Counterpoint with data]
2. [Practical alternative]
3. [Framework for thinking differently]

[CTA to engage]"
```

### The "How I Did It" Story
```
"In [year], I was [relatable struggle].

Today, I [impressive outcome].

Here's the exact [process/system/framework] I used:

[Step-by-step breakdown]

[Lesson learned + CTA]"
```

### The Data-Driven Insight
```
"[Surprising stat] changed how I think about [topic].

Here's the data:

[Chart/graph description or key numbers]

The implication:
[What this means practically]

[CTA to learn more/discuss]"
```

### The Curiosity Gap
```
"[Bold statement that creates mystery]

Most people don't know that:

• [Unexpected fact 1]
• [Unexpected fact 2]
• [Unexpected fact 3]

Here's why this matters:
[Explanation]

[Thread/link for more]"
```

## Research-to-Content Mapping

| Research Finding | Content Angle |
|-----------------|---------------|
| New tool/release | "How to use [X] for [outcome]" |
| Industry trend | "The future of [field]: 5 predictions" |
| Surprising stat | "Why [X]% of [thing] fails (and how to fix it)" |
| Expert quote | "[Name] on [topic]: What everyone misses" |
| Competitor success | "What [Company] did differently" |
| Common mistake | "Stop doing [X]. Do this instead." |

## Engagement Optimization

### Timing
- X: Tuesday-Thursday, 9am-12pm EST
- LinkedIn: Tuesday-Thursday, 8-10am EST
- Blog: Any day, but Tuesday/Wednesday for email newsletters

### Frequency
- X: 1-3 posts/day + occasional threads
- LinkedIn: 3-5 posts/week
- Blog: 1-2 posts/week minimum

### Engagement Tactics
- Reply to every comment in first 30 minutes
- Quote tweet yourself to add context
- Cross-post with slight modifications per platform
- Create content series (Part 1, Part 2, etc.)

## Quality Checklist

Before publishing, verify:
- [ ] Hook grabs attention in first 5 words
- [ ] Every sentence earns its place
- [ ] Value is clear within first 2 sentences
- [ ] Data/sources are cited where used
- [ ] Tone matches platform norms
- [ ] CTA is clear and easy to act on
- [ ] Image is relevant and high quality
- [ ] No spelling/grammar errors
- [ ] Would I share this if someone else posted it?

## Content Calendar Framework

**Weekly Rhythm:**
- Monday: Educational/how-to content
- Tuesday: Industry insight/trend analysis
- Wednesday: Personal story/behind-the-scenes
- Thursday: Contrarian take/debate starter
- Friday: Community engagement/question post

**Monthly Themes:**
- Week 1: Educational content
- Week 2: Trend analysis and predictions
- Week 3: Case studies and examples
- Week 4: Community and personal content

## Common Pitfalls

1. **Writing without researching** → Results in generic content
2. **No clear hook** → Readers scroll past
3. **Too many CTAs** → No action taken
4. **Ignoring platform norms** → Poor engagement
5. **Posting and ghosting** → Algorithm deprioritizes
6. **No visual element** → 2-3x lower engagement
7. **Copying competitor angles** → Gets lost in noise

## Tools Integration Examples

### Research + Draft a Thread
```
1. web_search: "AI agents 2026 trends" → Find 3 key developments
2. grok_api: "Write a 7-tweet thread about [key finding]"
3. generate_image: "Illustration of AI agents working together, futuristic, blue tones, landscape"
4. browser: Navigate to x.com and post
5. x_log_action: Log the post to prevent duplicates
```

### Create a Blog Post
```
1. web_search: Latest data on topic
2. grok_api: Generate outline
3. grok_api: Write full draft section by section
4. file_write: Save draft for review
5. generate_image: Create featured image
6. browser: Publish to Medium/Substack
```

## Saving Content Ideas

Use memory_save to store content ideas for later:
```
memory_save:
  content: "Content idea: [topic] - Angle: [approach] - Sources found: [links]"
  tags: "content-idea, [topic], [platform]"
```

Retrieve ideas later:
```
memory_search: "content idea [topic]"
```

## Performance Tracking

Track these metrics per platform:
- **X**: Impressions, engagement rate, profile clicks, follower growth
- **LinkedIn**: Post views, reactions, comments, shares
- **Blog**: Page views, time on page, bounce rate, email signups

Use x_action_stats for X-specific analytics.
