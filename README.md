# IA_HACKATON

## Discovery

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.discovery.cli "I want a high-protein creamy chicken pasta under 30 minutes"
```

The discovery boundary returns ranked `CandidateVideo` objects. It uses deterministic mock social-search data; `WebSearchProvider` is a non-scraping stub for a future search API.
