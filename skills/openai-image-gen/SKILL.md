---
name: openai-image-gen
description: "Generate images using AI — powered by Gemini 3 Pro Image via the native generate_image tool"
triggers:
  - generate image
  - create image
  - make image
  - draw
  - image generation
  - make a picture
  - create a visual
  - design graphic
  - generate art
  - ai image
  - generate photo
  - make a graphic
tools:
  - generate_image
  - file_read
  - browser
priority: 5
---

# Image Generation

You have a native `generate_image` tool powered by Gemini 3 Pro Image Preview via OpenRouter. Use it for ALL image generation tasks.

## Usage

```
generate_image(prompt='Your detailed image description', style='photorealistic', size='landscape')
```

### Parameters

- **prompt** (required): Detailed description of the image. Be specific about subject, composition, colors, lighting, and mood.
- **style** (optional): Style hint — `photorealistic`, `illustration`, `digital art`, `watercolor`, `minimalist`, `3d render`, `pixel art`, etc.
- **size** (optional): Aspect ratio — `landscape` (16:9, best for tweets/banners), `portrait` (9:16, best for stories), `square` (1:1, best for profiles/icons).
- **filename** (optional): Custom filename. Auto-generated with timestamp if omitted.

### Output

The tool saves the image as PNG to `~/.ghost/generated_images/` and returns:
- `path`: Full file path to the saved image
- `size_kb`: File size in KB
- `filename`: The generated filename

## Examples

**Social media graphic:**
```
generate_image(prompt='Modern minimalist tech banner with gradient blue to purple background, subtle circuit board patterns, text area on the left side', style='digital art', size='landscape')
```

**Product showcase:**
```
generate_image(prompt='Clean product photography of a sleek wireless earbuds case on a white marble surface with soft studio lighting', style='photorealistic', size='square')
```

**Illustration:**
```
generate_image(prompt='Whimsical watercolor illustration of a robot reading a book in a cozy library, warm golden lighting', style='watercolor', size='portrait')
```

## Prompt Tips

1. **Be specific** — "A golden retriever sitting in a sunlit meadow" beats "a dog"
2. **Describe composition** — "centered subject with blurred background" or "wide shot from above"
3. **Mention lighting** — "soft golden hour light", "dramatic studio lighting", "neon glow"
4. **Specify colors** — "muted earth tones", "vibrant neon palette", "black and white with a single red accent"
5. **Add mood/atmosphere** — "peaceful", "energetic", "mysterious", "professional"

## After Generation

- The image path is returned — you can reference it, attach it to tweets, or tell the user where to find it
- To show the user: provide the file path so they can open it
- To attach to a tweet: use the browser tool to upload it on X's compose page
- Images persist in `~/.ghost/generated_images/` until manually cleaned up
