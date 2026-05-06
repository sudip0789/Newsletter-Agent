# AI Newsletter Agent

An automated agent that discovers, filters, ranks, reviews and summarizes AI news into a ready-to-publish weekly newsletter. It replaces a manual workflow that took 4–6 hours per issue with a pipeline that runs in minutes.

## What It Does

The pipeline collects 500+ articles per week from RSS feeds and news APIs, filters them for AI relevance, removes duplicates, clusters overlapping coverage, scores and ranks stories based on set conditions, generates editorial summaries, selects headline features, creates infographic, and assembles everything into a website style formatted newsletter.

## Quick Start

### Prerequisites

- Python 3.11+
- API keys: OpenAI, Anthropic, NewsAPI (free tier)


### Setup

```bash
git clone https://github.com/sudip0789/newsletter-agent.git
cd newsletter-agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:

```
OPENAI_API_KEY=your_key
NEWS_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
```
### Run the Full Pipeline

```bash
python run_pipeline.py
```
### Run Individual Stages

All src files have their own runner and can be run separately

### Build the Deployable Site

To regenerate the static site bundle locally:

```bash
python build_public_site.py
```

This command syncs `assets/` into `public/assets/` and renders `public/index.html`.

### Vercel Deploys

Vercel is configured to rebuild the deployable static site on each deployment:

- `vercel.json` runs `python3 build_public_site.py` as the build command
- the deploy output stays `public/`

That means you can push source changes and data/template changes without manually updating `public/index.html` first.

# Tech Stack

| Component | Tool |
|---|---|
| Language | Python 3.11+ & HTML |
| Scoring | OpenAI GPT-5.4 |
| Summaries, Headlines | Anthropic Claude Sonnet 4.6 |
| Embeddings | OpenAI text-embedding-3 |
| Image generation | OpenAI GPT Image 1.5 |
| Article extraction | Trafilatura |
| RSS parsing | Feedparser |
| News search | NewsAPI.org |
| Clustering | scikit-learn (agglomerative clustering) |
| Templating | Jinja2 |
| Review UI | Streamlit |
| Data models | Pydantic v2 |
| Deployment | Vercel |
