#!/usr/bin/env python3
"""Generate or edit images with Gemini image models via REST API."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from urllib import error, parse, request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate/edit an image using Gemini and save it to disk."
    )
    parser.add_argument(
        "--prompt",
        required=True,
        help="Prompt describing what to generate or how to edit.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path. If extension is missing, infer from response MIME type.",
    )
    parser.add_argument(
        "--reference-image",
        help="Optional path to a source image for edit/transform tasks.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"),
        help="Gemini model name (default: GEMINI_IMAGE_MODEL or gemini-2.5-flash-image).",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("GEMINI_API_KEY"),
        help="Google API key (default: GEMINI_API_KEY env var).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Optional sampling temperature.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=90,
        help="HTTP timeout in seconds (default: 90).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output file if it already exists.",
    )
    parser.add_argument(
        "--print-text",
        action="store_true",
        help="Print text parts returned by the model.",
    )
    return parser.parse_args()


def get_mime_type(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(str(path))
    return mime_type or "application/octet-stream"


def build_parts(prompt: str, reference_image_path: str | None) -> list[dict]:
    parts: list[dict] = []
    if reference_image_path:
        image_path = Path(reference_image_path).expanduser().resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Reference image not found: {image_path}")
        parts.append(
            {
                "inline_data": {
                    "mime_type": get_mime_type(image_path),
                    "data": base64.b64encode(image_path.read_bytes()).decode("utf-8"),
                }
            }
        )
    parts.append({"text": prompt})
    return parts


def call_gemini(
    *,
    api_key: str,
    model: str,
    parts: list[dict],
    temperature: float | None,
    timeout: int,
) -> dict:
    payload: dict = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }
    if temperature is not None:
        payload["generationConfig"]["temperature"] = temperature

    encoded_key = parse.quote(api_key, safe="")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={encoded_key}"
    )
    req = request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API error {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error calling Gemini API: {exc.reason}") from exc


def extract_image_and_text(response_data: dict) -> tuple[bytes, str | None, list[str]]:
    candidates = response_data.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")

    texts: list[str] = []
    image_data_b64: str | None = None
    image_mime: str | None = None

    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())

            inline_data = part.get("inlineData") or part.get("inline_data")
            if inline_data and image_data_b64 is None:
                image_data_b64 = inline_data.get("data")
                image_mime = inline_data.get("mimeType") or inline_data.get("mime_type")

    if image_data_b64 is None:
        msg = "Gemini response did not contain an image part."
        if texts:
            msg = f"{msg} Text returned: {texts[0]}"
        raise RuntimeError(msg)

    try:
        raw_image = base64.b64decode(image_data_b64)
    except Exception as exc:
        raise RuntimeError("Failed to decode image base64 from Gemini response.") from exc

    return raw_image, image_mime, texts


def extension_from_mime(mime: str | None) -> str:
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }
    return mapping.get((mime or "").lower(), ".png")


def resolve_output_path(output: str, mime: str | None) -> Path:
    path = Path(output).expanduser().resolve()
    if not path.suffix:
        path = path.with_suffix(extension_from_mime(mime))
    return path


def main() -> int:
    args = parse_args()

    if not args.api_key:
        print("Error: missing API key. Set GEMINI_API_KEY or pass --api-key.", file=sys.stderr)
        return 2

    try:
        parts = build_parts(args.prompt, args.reference_image)
        response_data = call_gemini(
            api_key=args.api_key,
            model=args.model,
            parts=parts,
            temperature=args.temperature,
            timeout=args.timeout,
        )
        raw_image, mime_type, texts = extract_image_and_text(response_data)
        output_path = resolve_output_path(args.output, mime_type)

        if output_path.exists() and not args.overwrite:
            print(
                f"Error: output file already exists: {output_path} "
                "(use --overwrite to replace).",
                file=sys.stderr,
            )
            return 2

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(raw_image)

        print(f"Saved image: {output_path}")
        if mime_type:
            print(f"MIME type: {mime_type}")
        if args.print_text and texts:
            print("Model text:")
            for item in texts:
                print(f"- {item}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
