# Video frame extraction and analysis

This module has two stages:

1. `framer.py` uses FFmpeg to sample the video, detect scene changes, remove near-duplicate images, and create `frames.json`.
2. `analyze_frames.py` sends batches of four frames to GPT-5 nano, with up to five API calls in flight, and writes structured visual descriptions.

## Install

From the project root:

```bash
brew install ffmpeg
source .venv/bin/activate
pip install -r framer/requirements.txt
```

The OpenAI script reads `OPENAI_API_KEY` from the project-root `.env` file.

## Extract representative frames

```bash
python framer/framer.py \
  insta_scraper/downloads/DU3Rmy5Dvqf/video.mp4
```

By default, the images and manifest are written to a `frames` directory beside the video. Use `--overwrite` to replace a previous extraction:

```bash
python framer/framer.py \
  insta_scraper/downloads/DU3Rmy5Dvqf/video.mp4 \
  --overwrite
```

Useful tuning options:

```bash
python framer/framer.py VIDEO \
  --interval 1.0 \
  --scene-threshold 0.35 \
  --duplicate-distance 6 \
  --duplicate-color-distance 30 \
  --max-frames 120
```

A lower scene threshold keeps more scene changes. Higher duplicate hash and color distances remove more visually similar frames.

## Analyze frames with OpenAI

First, test with three frames:

```bash
python framer/analyze_frames.py \
  insta_scraper/downloads/DU3Rmy5Dvqf/frames/frames.json \
  --limit 3
```

Then analyze the complete manifest. Choose a different output path from the test run:

```bash
python framer/analyze_frames.py \
  insta_scraper/downloads/DU3Rmy5Dvqf/frames/frames.json \
  -o insta_scraper/downloads/DU3Rmy5Dvqf/frames/full_frame_analysis.json
```

The analysis is saved after every successful four-frame batch. If a run is interrupted, continue it with:

```bash
python framer/analyze_frames.py \
  insta_scraper/downloads/DU3Rmy5Dvqf/frames/frames.json \
  --resume
```
