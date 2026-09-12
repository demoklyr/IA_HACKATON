# IA_HACKATON

## Discovery

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.discovery.cli "I want a high-protein creamy chicken pasta under 30 minutes"
```

The discovery boundary returns ranked `CandidateVideo` objects. It uses deterministic mock social-search data; `WebSearchProvider` is a non-scraping stub for a future search API.

### Intent agent

Without an API key, discovery uses the local rule-based parser. To enable the LangChain intent agent, copy `.env.example` to `.env` and set:

```dotenv
OPENAI_API_KEY=your-key
DISCOVERY_MODEL=openai:gpt-4.1-mini
```

The agent instructions live in `app/discovery/skills/intent_parser.md`, so they can evolve without changing Python code. LangChain is intentionally limited to intent parsing; URL deduplication and ranking remain deterministic.
