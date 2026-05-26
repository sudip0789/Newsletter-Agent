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
python3 scripts/pipeline_runner.py
```
### Run Individual Stages

All stage entrypoints live in `scripts/` and can be run separately.

### Build the Deployable Site

To regenerate the static site bundle locally:

```bash
python3 scripts/build_public_site.py
```

This command syncs `assets/` into `public/assets/` and renders `public/index.html`.


### Publish an Issue and Update the Archive

When an issue is approved and ready to go live:

1. Upload that week's `.m4a` and `.mp4` files to Google Drive.
2. Paste their Google Drive share links into `data/output/media_inputs.json`.
3. Run:

```bash
python3 scripts/publish_issue.py --date 2026-05-06
```

This workflow:

- snapshots the current issue into `issue_snapshots/YYYY-MM-DD/`
- copies generated headline images into that dated snapshot
- reads weekly audio/video links from `data/output/media_inputs.json`
- rebuilds `public/index.html` for the latest issue
- rebuilds `public/issues/index.html` plus dated archive pages for older issues

`data/output/media_inputs.json` is the weekly handoff file for media links. It accepts either full Google Drive share URLs such as `https://drive.google.com/file/d/.../view?...` or already-normalized `/preview` URLs. The publisher converts those into the embed URLs used by the newsletter.

After that, commit the snapshot and rebuilt static files, then trigger a manual production deployment on Vercel.

# Tech Stack

| Component | Tool |
|---|---|
| Language | Python 3.11+ & HTML |
| Scoring | OpenAI GPT-5.4 |
| Summaries, Headline blurbs | Anthropic Claude Sonnet 4.6 |
| Headline selection | OpenAI GPT-5.4 |
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
