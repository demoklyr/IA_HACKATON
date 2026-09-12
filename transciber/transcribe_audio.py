#!/usr/bin/env python3
"""Transcribe an audio file with OpenAI Whisper."""

import argparse
from pathlib import Path

from openai import OpenAI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe an audio file using OpenAI's whisper-1 model."
    )
    parser.add_argument("audio_file", type=Path, help="Path to the input audio file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional path where the transcript should be saved",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audio_path = args.audio_file.expanduser().resolve()

    if not audio_path.is_file():
        raise SystemExit(f"Audio file not found: {audio_path}")

    client = OpenAI()
    with audio_path.open("rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text",
        )

    text = transcript if isinstance(transcript, str) else transcript.text
    print(text)

    if args.output:
        output_path = args.output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
