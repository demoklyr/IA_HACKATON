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

For offline development, use the deterministic mock provider:

```dotenv
DISCOVERY_SEARCH_PROVIDER=mock
```

### Minimal ReAct agent

To run the LangChain ReAct agent, copy `.env.example` to `.env` and set:

```dotenv
OPENAI_API_KEY=your-key
DISCOVERY_MODEL=openai:gpt-4.1-mini
DISCOVERY_SEARCH_PROVIDER=serper
SERPER_API_KEY=your-key
```

Then run:

```bash
python main.py --langchain-react "I want an easy vegetarian Mexican recipe"
```

The agent has two tools: `search_videos`, which sends the model's query to the configured search provider, and `rank_candidates`, which ranks the returned URLs. There is no separate intent parser or query planner.

## Serper web-search tool

`app.web_search_tool.web_search` is a LangChain tool for general Google web
searches through Serper. Add the key to `.env` before invoking it:

```dotenv
SERPER_API_KEY=your-key
```

The tool accepts a `query` and an optional `limit` (1–100), and returns the
JSON response from Serper without scraping result pages.

The discovery agents use this tool automatically when `SERPER_API_KEY` is set.
You can also select it explicitly:

```dotenv
DISCOVERY_SEARCH_PROVIDER=serper
SERPER_API_KEY=your-key
```

The agent's query is sent directly to Serper with an Instagram site filter.
Only direct Instagram Reel URLs continue into ranking.
