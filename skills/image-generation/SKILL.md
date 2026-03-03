---
name: image-generation
description: AI image generation for social media content, AR/VR concept art, thumbnails, and visual assets using DALL-E, Stable Diffusion, and other providers via OpenRouter
triggers:
  - generate image
  - create image
  - make image
  - image generation
  - ai image
  - generate a picture
  - create thumbnail
  - social media graphic
  - concept art
  - ar concept
  - vr visualization
  - profile picture
  - banner image
  - illustration
  - digital art
  - photorealistic image
tools:
  - generate_image
priority: 60
content_types:
  - image_generation
  - visual_content
---

# AI Image Generation Guide

Generate images for social media, AR/VR concepts, marketing materials, and creative projects using AI.

## When to Use This Skill

- Creating thumbnails for X/Twitter posts or YouTube videos
- Generating concept art for AR lens ideas
- Making social media graphics and banners
- Creating profile pictures or avatars
- Visualizing ideas before building them
- Producing illustrations for blog posts or presentations

## Best Practices

### Prompt Engineering

**Be specific and descriptive:**
- Good: "A futuristic AR glasses interface floating in a dark room, holographic blue UI elements, cinematic lighting, 4K render"
- Weak: "AR glasses"

**Include key details:**
- Subject: What is the main focus?
- Style: Photorealistic, illustration, 3D render, watercolor?
- Lighting: Cinematic, studio, natural, neon?
- Mood/Atmosphere: Dreamy, professional, dramatic, minimal?
- Technical: 4K, highly detailed, sharp focus

**Add style modifiers for better results:**
- Photorealistic: "DSLR photo", "8K resolution", "professional photography"
- Illustration: "vector art", "flat design", "minimalist illustration"
- Concept art: "Unreal Engine render", "Octane render", "cinematic"

### Aspect Ratio Guide

| Use Case | Ratio | Size Parameter |
|----------|-------|----------------|
| X/Twitter posts | 16:9 landscape | `landscape` |
| Instagram Stories | 9:16 portrait | `portrait` |
| Profile pictures | 1:1 square | `square` |
| LinkedIn/X banners | 16:9 landscape | `landscape` |
| Pinterest | 2:3 portrait | `portrait` |

### Style Selection

| Style | Best For | Keywords to Include |
|-------|----------|---------------------|
| `photorealistic` | Product shots, realistic scenes | "photorealistic", "DSLR", "8K" |
| `illustration` | Blog headers, explainer graphics | "vector illustration", "flat design" |
| `digital art` | Concept art, creative projects | "digital art", "ArtStation", "trending" |
| `watercolor` | Soft, artistic visuals | "watercolor painting", "soft textures" |
| `minimalist` | Clean, modern designs | "minimalist", "clean lines", "simple" |

## Common Workflows

### 1. Social Media Thumbnail
```
Prompt: "Eye-catching thumbnail for tech video, neon circuit board background, floating holographic AI brain, bold cinematic lighting, 8K render, photorealistic"
Size: landscape (16:9)
```

### 2. AR Lens Concept Art
```
Prompt: "AR face filter concept, glowing digital mask overlay on face, cyberpunk aesthetic, neon accents, dark background, Unreal Engine render"
Size: portrait (9:16)
```

### 3. X Profile Banner
```
Prompt: "Professional tech banner, abstract neural network visualization, gradient from purple to blue, futuristic minimal design, wide format"
Size: landscape (16:9)
```

### 4. Product Mockup
```
Prompt: "Sleek smartphone displaying AR app, floating in clean white studio, soft shadows, product photography style, highly detailed"
Size: square (1:1)
```

## Examples

- "Generate a thumbnail for my AR tutorial video showing holographic UI"
- "Create a concept image of AR glasses showing navigation directions"
- "Make a square profile picture of a robot in watercolor style"
- "Generate a landscape banner for my X profile about AI and AR"
- "Create an illustration of a developer working with AI tools"

## Tips

1. **Iterate on prompts**: If the first result isn't perfect, refine your description
2. **Use negative prompts implicitly**: Avoid describing what you don't want
3. **Reference artists/styles**: "in the style of Syd Mead" or "Studio Ghibli aesthetic"
4. **Consider the platform**: X favors bold, high-contrast images; LinkedIn prefers professional looks
5. **File management**: Generated images are saved to `~/.ghost/generated_images/`

## Tool Usage

```python
# Basic usage
path = generate_image(
    prompt="Your detailed prompt here",
    size="landscape",  # or "portrait", "square"
    style="photorealistic"  # optional
)

# Returns: path to the saved PNG file
```
