#!/usr/bin/env python3
"""Extract a structured recipe from an Instagram caption and transcript."""

import argparse
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class RecipeStep(BaseModel):
    stepNumber: int = Field(ge=1)
    description: str


class Ingredient(BaseModel):
    name: str
    quantity: str


class Recipe(BaseModel):
    steps: list[RecipeStep]
    ingredients: list[Ingredient]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract structured recipe data from a caption and transcript."
    )
    parser.add_argument("description_file", type=Path, help="Post caption text file")
    parser.add_argument("transcript_file", type=Path, help="Audio transcript text file")
    parser.add_argument("-o", "--output", type=Path, help="Optional output JSON file")
    return parser.parse_args()


def read_text_file(path: Path) -> str:
    resolved_path = path.expanduser().resolve()
    if not resolved_path.is_file():
        raise SystemExit(f"File not found: {resolved_path}")
    return resolved_path.read_text(encoding="utf-8")


def main() -> None:
    args = parse_args()
    post_description = read_text_file(args.description_file)
    audio_transcript = read_text_file(args.transcript_file)

    client = OpenAI()
    response = client.responses.parse(
        model="gpt-5-nano",
        input=[
            {
                "role": "system",
                "content": (
                    "Extract a cooking recipe from the supplied Instagram post description "
                    "and audio transcript. Combine complementary information from both sources. "
                    "Do not invent ingredients, quantities, or instructions. Keep steps in "
                    "chronological order and number them sequentially starting at 1. If an "
                    "ingredient has no stated quantity, use 'unspecified'. Return empty arrays "
                    "when the sources do not contain a recipe."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"POST DESCRIPTION:\n{post_description}\n\n"
                    f"AUDIO TRANSCRIPT:\n{audio_transcript}"
                ),
            },
        ],
        text_format=Recipe,
    )

    recipe = response.output_parsed
    if recipe is None:
        raise SystemExit("The model did not return a recipe.")

    json_output = recipe.model_dump_json(indent=2)
    print(json_output)

    if args.output:
        output_path = args.output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"{json_output}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
