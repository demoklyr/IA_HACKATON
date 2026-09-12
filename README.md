# IA_HACKATON

## Discovery

```bash
brew install python
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.discovery.cli "I want a high-protein creamy chicken pasta under 30 minutes"
```

The discovery boundary returns ranked `CandidateVideo` objects. Search is isolated
behind `SocialSearchProvider`, so a real SERP provider can be plugged in without
changing the agent pipeline.

For now, the only bundled provider is deterministic offline mock data:

```dotenv
DISCOVERY_SEARCH_PROVIDER=mock
```

### Intent agent

Without an API key, discovery uses the local rule-based parser. To enable the LangChain intent agent, copy `.env.example` to `.env` and set:

```dotenv
OPENAI_API_KEY=your-key
DISCOVERY_MODEL=openai:gpt-4.1-mini
DISCOVERY_SEARCH_PROVIDER=mock
```

The agent instructions live in `app/discovery/skills/intent_parser.md`, so they can evolve without changing Python code. LangChain is intentionally limited to intent parsing; URL deduplication and ranking remain deterministic.
