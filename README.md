# AI Newsletter Pipeline - Stage 1

This project implements Stage 1 of an AI newsletter pipeline: source ingestion. It collects AI and tech news articles from configured RSS feeds, NewsAPI keyword queries, and Google News RSS, attempts full-text retrieval for snippet-only entries, deduplicates results by normalized URL, and writes a flat JSON output ready for downstream processing.

## Setup

1. Clone or copy this project.
2. Create a `.env` file from the template:
   - `cp .env.example .env`
3. Install dependencies:
   - `pip install -r requirements.txt`

## Quick Start

Run RSS-only mode for immediate testing (no API key required):

```bash
python run_stage1.py --rss-only
```

## Full Run

Add your NewsAPI key to `.env` and run:

```bash
python run_stage1.py
```

## Output

Results are saved to:

`data/output/stage1_articles.json`
