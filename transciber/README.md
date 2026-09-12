# Audio Transcriber

Transcribes an audio file with OpenAI's `whisper-1` model. The transcript is
printed in the terminal and can optionally be saved to a text file.

## Requirements

- Python 3.9 or newer
- An [OpenAI API key](https://platform.openai.com/api-keys)

## Installation

From this folder, create a virtual environment and install the OpenAI package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install openai
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

Set your API key. Do not put the key directly in the Python file or commit it to
Git.

macOS/Linux:

```bash
export OPENAI_API_KEY="your-api-key"
```

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY="your-api-key"
```

## Usage

Print a transcript in the terminal:

```bash
python transcribe_audio.py ../insta_scraper/downloads/DU3Rmy5Dvqf/audio-only.m4a
```

Print it and save it to a file:

```bash
python transcribe_audio.py ../insta_scraper/downloads/DU3Rmy5Dvqf/audio-only.m4a --output transcript.txt
```

M4A, MP3, MP4, WAV, FLAC, OGG, MPEG, MPGA, and WebM inputs are supported.
