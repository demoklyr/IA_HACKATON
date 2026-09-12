# Recipe extractor

Creates a structured recipe from three sources:

- the Instagram caption;
- the audio transcript;
- the structured frame analysis produced by `framer/analyze_frames.py`.

The frame-analysis input is optional so the previous caption-and-transcript workflow still works.

## Complete the frame analysis

If `frame_analysis.json` currently contains only the three-frame test, continue it first:

```bash
python framer/analyze_frames.py \
  insta_scraper/downloads/DU3Rmy5Dvqf/frames/frames.json \
  --resume
```

## Create the recipe

From the project root:

```bash
source .venv/bin/activate

python recipe_extractor/extract_recipe.py \
  insta_scraper/downloads/DU3Rmy5Dvqf/caption.txt \
  insta_scraper/downloads/DU3Rmy5Dvqf/transcript.txt \
  insta_scraper/downloads/DU3Rmy5Dvqf/frames/frame_analysis.json \
  --output insta_scraper/downloads/DU3Rmy5Dvqf/recipe.json
```

Without visual analysis:

```bash
python recipe_extractor/extract_recipe.py CAPTION.txt TRANSCRIPT.txt
```

The script reads `OPENAI_API_KEY` from the project-root `.env` file and uses `gpt-5-nano` by default.
