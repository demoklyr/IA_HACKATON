# IA_HACKATON

## Discovery

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.discovery.cli "I want a high-protein creamy chicken pasta under 30 minutes"
```

The discovery boundary returns ranked `CandidateVideo` objects. When
`OPENAI_API_KEY` is configured, it uses the Responses API hosted web-search tool
to find public Instagram Reel pages. It never scrapes Instagram directly. Because
Instagram can block individual Reels from public search indexes, a real search can
legitimately return no candidates. Without an API key, discovery falls back to
deterministic mock data.

With `DISCOVERY_SEARCH_PROVIDER=google`, discovery searches Google with
`site:instagram.com/reel OR site:instagram.com/reels` and keeps only direct
Instagram Reel URLs. This does not spend OpenAI search credits, but Google can
still rate-limit or block automated requests.

The generated query variants are grouped into one billed web-search API request
only when `DISCOVERY_SEARCH_PROVIDER=web`.
To force offline mock data even when a key is configured, set:

```dotenv
DISCOVERY_SEARCH_PROVIDER=mock
```

To search Google for indexed Instagram Reels, set:

```dotenv
DISCOVERY_SEARCH_PROVIDER=google
```

To try Instagram directly without spending search credits, set:

```dotenv
DISCOVERY_SEARCH_PROVIDER=instagram
```

This opens Instagram's public keyword-search URL and keeps only direct
`/reel/...` links. It may still return no result if Instagram serves a login
wall or hides Reel data from the initial HTML response.

### Intent agent

Without an API key, discovery uses the local rule-based parser. To enable the LangChain intent agent, copy `.env.example` to `.env` and set:

```dotenv
OPENAI_API_KEY=your-key
DISCOVERY_MODEL=openai:gpt-4.1-mini
DISCOVERY_SEARCH_PROVIDER=instagram
DISCOVERY_SEARCH_MODEL=gpt-5.5
```

The agent instructions live in `app/discovery/skills/intent_parser.md`, so they can evolve without changing Python code. LangChain is intentionally limited to intent parsing; URL deduplication and ranking remain deterministic.
