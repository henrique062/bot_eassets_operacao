# Gemini Image API Notes

## Request shape

Use `POST /v1beta/models/{model}:generateContent?key=...` with:

```json
{
  "contents": [
    {
      "parts": [
        {"text": "Prompt aqui"},
        {
          "inline_data": {
            "mime_type": "image/jpeg",
            "data": "<base64 da imagem de entrada>"
          }
        }
      ]
    }
  ],
  "generationConfig": {
    "responseModalities": ["IMAGE", "TEXT"]
  }
}
```

For pure text-to-image, send only the `text` part.
For image editing/restyling, include `inline_data` plus text instructions.

## Response shape

Look for generated image in:

- `candidates[].content.parts[].inlineData`
- or `candidates[].content.parts[].inline_data`

The base64 bytes are in `data`.
MIME can arrive as `mimeType` or `mime_type`.

## Common failures

- `400 INVALID_ARGUMENT`: invalid payload or unsupported model.
- No image in response: model returned text only; inspect prompt and retry with clearer visual instruction.
- `403/401`: missing or invalid `GEMINI_API_KEY`.
