---
name: gemini-image-generator
description: Generate and edit images with Google's Gemini image model (`gemini-2.5-flash-image`) through the REST API and local helper script. Use this skill when the user asks to create new images, transform or restyle an existing image, iterate prompt variations, or save generated image files (PNG/JPEG/WebP) to disk.
---

# Gemini Image Generator

## Overview

Generate an image from text, or edit an existing image, using `gemini-2.5-flash-image`.
Run the helper script to save the binary output to a local file and return the saved path.

## Workflow

1. Capture the request constraints: subject, style, framing, mood, and exclusions.
2. Write a concrete prompt in the user language, including required visual details.
3. Run `scripts/generate_image.py` with `--prompt` and `--output`.
4. Add `--reference-image` when the user asks to transform an existing image.
5. Inspect result quality and iterate with a single prompt change per retry.
6. Return the file path and a short summary of what was generated.

## Quick Commands

Generate from text:

```bash
python3 scripts/generate_image.py \
  --prompt "Ilustração isométrica de uma cidade litorânea futurista ao amanhecer, sem texto." \
  --output /tmp/cidade-futurista.png
```

Edit from reference image:

```bash
python3 scripts/generate_image.py \
  --prompt "Transforme para estilo aquarela, mantendo composição e iluminação originais." \
  --reference-image /tmp/input.jpg \
  --output /tmp/input-aquarela.png
```

## Prompt Rules

- Declare the main subject first, then setting, style, and lighting.
- Explicitly state constraints such as "sem texto", "sem marca d'agua", or "fundo transparente".
- For edits, state what must remain unchanged (pose, framing, colors) and what must change.
- Prefer one precise prompt over many vague instructions.

## Operational Rules

- Require `GEMINI_API_KEY` in environment or pass `--api-key`.
- Default to model `gemini-2.5-flash-image`; only change when user requests another model.
- Save one output file per request unless the user asks for multiple variants.
- Use `.png` by default when the user does not specify extension.

## Troubleshooting

- If API returns `400`, simplify the prompt and check model name.
- If response has no image part, inspect returned text with `--print-text`.
- If more payload detail is needed, read [references/gemini-image-api.md](references/gemini-image-api.md).
