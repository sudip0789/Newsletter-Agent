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
python3 newsletter_pipeline --date YYYY-MM-DD
```
Runs every stage end to end for that issue date — ingestion, filtering, deduplication, scoring, summarization, title rewriting, headline selection, and publishing.

If headline images were regenerated after publishing and the Drive folder should
be refreshed too:

```bash
python3 scripts/build_public_site.py --date YYYY-MM-DD --refresh-drive-images
```
### Run Individual Stages

All stage entrypoints live in `scripts/` and can be run separately.

### Build the Deployable Site

To regenerate the static site bundle locally:

```bash
python3 scripts/build_public_site.py
```

This command syncs `assets/` into `public/assets/`, renders `public/index.html`, and generates `public/newsletter.pdf` for the latest issue.

PDF generation uses Playwright + Chromium. After installing Python dependencies, run:

```bash
python -m playwright install chromium
```

### Add Audio/Video After Publishing

The full pipeline already publishes the issue — it snapshots into `issue_snapshots/YYYY-MM-DD/`, uploads headline images to Google Drive (when configured), and rebuilds the public site. The podcast and video are produced from the finished newsletter using notebookLM

Once the podcast and video exist, drop the audio at `data/output/audio.m4a` and add the video's Google Drive link to `data/output/media_inputs.json`:

```json
{ "video_url": "https://drive.google.com/file/d/FILE_ID/view" }
```

Then rebuild:

```bash
python3 scripts/build_public_site.py --date YYYY-MM-DD
```

The build converts the audio to MP3 for browser playback, syncs the media into the issue snapshot, and regenerates the site.

### Deployment

1. Commit your changes (the snapshot and rebuilt static files).
2. Push to `main` — this triggers the Vercel deployment.

The site is also embedded into the Google Site for Stanford's Learning Hub.

## Tech Stack

| Component | Tool |
|---|---|
| Language | Python 3.11+ & HTML |
| Scoring | OpenAI GPT-5.5 |
| Summaries, Headline blurbs | Anthropic Claude Opus 4.8 |
| Headline selection | OpenAI GPT-5.5 |
| Embeddings | OpenAI text-embedding-3 |
| Image generation | OpenAI GPT Image 2 |
| Article extraction | Trafilatura |
| RSS parsing | Feedparser |
| News search | NewsAPI.org |
| Clustering | scikit-learn (agglomerative clustering) |
| Templating | Jinja2 |
| Review UI | Streamlit |
| Data models | Pydantic v2 |
| Deployment | Vercel |
