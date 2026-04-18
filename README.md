# Web Crawler & Search Engine

A concurrent web crawling and search engine platform built with Python and Flask. Features real-time monitoring, three-layer backpressure control, intelligent relevance-based search, and resumable crawl jobs — all powered by SQLite with WAL mode for concurrent read/write access.

## Features

- **Concurrent Web Crawler** — Multi-threaded BFS crawling via `ThreadPoolExecutor` with configurable depth limits
- **Three-Layer Backpressure** — Token bucket rate limiter (10 req/s) + bounded queue (10K max) + worker pool (5 threads)
- **Live Search During Indexing** — SQLite WAL mode enables non-blocking search queries while the crawler writes new data
- **Relevance Scoring Engine** — Dual search: keyword matching (SQL) and exact-word frequency scoring via inverted index files
- **Resumable Crawl Jobs** — Periodic frontier checkpoints allow interrupted jobs to resume from where they left off
- **Real-time Dashboard** — Auto-updating status page with backpressure gauges, job progress, and system metrics
- **Premium Dark Mode UI** — Glassmorphism design with micro-animations, toast notifications, and responsive layout

---

## Quick Start

### Prerequisites
- Python 3.8+
- Web browser (Chrome, Firefox, Safari, Edge)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/web-crawler.git
cd web-crawler

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate
# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Run

```bash
python app.py
```

Open `http://localhost:3600` in your browser.

---

## Usage

### 1. Start a Crawl Job

Navigate to the **Index** tab. Enter an origin URL (e.g., `https://books.toscrape.com/`) and a max depth (k). Click **Start Indexing**.

The crawler will run in the background — you can navigate to other tabs while it works.

### 2. Monitor Progress

Switch to the **Status** tab. The dashboard auto-refreshes every 2 seconds showing:

| Metric | Description |
|--------|-------------|
| Pages Indexed | Total pages stored in the database |
| Active Jobs | Number of currently running crawl jobs |
| Available Tokens | Rate limiter tokens available for requests |
| Queue Depth | Current BFS frontier size across all jobs |

The **Queue Utilization** gauge visualizes how close the queue is to the backpressure limit (green → amber → red).

### 3. Search

Switch to the **Search** tab. Two modes are available:

- **Keyword**: Broad search across page titles and content (SQL LIKE)
- **Relevance**: Exact word match with frequency-based scoring: `score = (freq × 10) + 1000 − (depth × 5)`

Results show the relevant URL, origin URL, depth, and (in relevance mode) a visual score bar.

If indexing is active, a **"Live — indexing active"** indicator appears, meaning results may update as new pages are discovered.

### 4. Resume Interrupted Jobs

If the server is stopped while a crawl is running, the job is automatically marked as **interrupted** on next startup. Click the **▶ Resume** button in the Status tab to continue from the last checkpoint.

---

## API Reference

| Method | Endpoint | Description | Body/Params |
|--------|----------|-------------|-------------|
| `POST` | `/api/index` | Start crawl job | `{"origin": "https://...", "k": 2}` |
| `POST` | `/api/resume/<id>` | Resume interrupted job | — |
| `GET` | `/api/search` | Search pages | `?query=term&sortBy=relevance` |
| `GET` | `/api/status` | System status | — |

### Search Response Format

```json
{
  "results": [
    {
      "relevant_url": "https://example.com/page",
      "origin_url": "https://example.com",
      "depth": 1,
      "title": "Page Title"
    }
  ],
  "query": "example",
  "count": 1,
  "indexing_active": true
}
```

### Status Response Format

```json
{
  "total_pages_indexed": 245,
  "active_jobs_count": 1,
  "backpressure": {
    "max_workers": 5,
    "max_queue_depth": 10000,
    "max_requests_per_second": 10.0,
    "available_tokens": 8.3
  },
  "recent_jobs": [
    {
      "id": 1,
      "origin_url": "https://books.toscrape.com/",
      "max_depth": 2,
      "status": "running",
      "pages_crawled": 245,
      "queue_size": 832,
      "pages_per_second": 4.2,
      "links_dropped": 0
    }
  ]
}
```

---

## Project Structure

```
web-crawler/
├── app.py                      # Flask API server & static file serving
├── database.py                 # SQLite WAL mode, schema, thread-safe connections
├── requirements.txt            # Python dependencies (flask, requests, beautifulsoup4)
├── services/
│   ├── __init__.py
│   ├── crawler_service.py      # BFS engine, ThreadPool, TokenBucket, checkpoint/resume
│   └── search_service.py       # Keyword + relevance search, live-results indicator
├── utils/
│   ├── __init__.py
│   └── html_parser.py          # HTTP fetching, URL normalization, link extraction
├── data/storage/               # Inverted index files (auto-generated)
│   └── *.data                  # Word frequency data per letter
├── demo/                       # Web UI (SPA)
│   ├── index.html              # Single-page application
│   └── style.css               # Premium dark mode design system
├── agents/                     # Multi-agent workflow definitions
│   ├── architect.md
│   ├── backend_engineer.md
│   ├── frontend_engineer.md
│   └── qa_integration.md
├── product_prd.md              # Product requirements document
├── recommendation.md           # Production deployment recommendations
├── multi_agent_workflow.md     # Multi-agent development process
├── readme.md                   # This file
└── crawler.db                  # SQLite database (auto-generated)
```

---

## Configuration

Edit the constants at the top of `services/crawler_service.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `MAX_WORKERS` | 5 | Concurrent download threads |
| `MAX_REQUESTS_PER_SECOND` | 10.0 | Token bucket refill rate |
| `MAX_QUEUE_DEPTH` | 10,000 | Max BFS frontier size before dropping links |
| `CHECKPOINT_INTERVAL` | 50 | Pages between frontier checkpoints (for resume) |

---

## Architecture

### How Concurrent Search Works

The key design decision enabling "search while indexing" is **SQLite WAL (Write-Ahead Logging) mode**:

- In WAL mode, writers append to a separate log file instead of modifying the main database
- Readers see a consistent snapshot and are **never blocked** by writers
- This means search queries execute instantly even during heavy crawl writes
- No external database server needed — it's a single file on disk

### Backpressure Design

Three complementary mechanisms prevent the system from overwhelming itself or target servers:

```
                     ┌─────────────────────┐
  Discovered URLs ──►│  Bounded Queue       │
                     │  (max 10,000 URLs)   │
                     └─────────┬───────────┘
                               │
                     ┌─────────▼───────────┐
                     │  Token Bucket        │
                     │  (10 tokens/sec)     │
                     └─────────┬───────────┘
                               │
                     ┌─────────▼───────────┐
                     │  Thread Pool         │
                     │  (5 workers)         │
                     └─────────┬───────────┘
                               │
                          HTTP Fetch
```

### Designing for Search During Active Indexing

The requirement states: "Search should be able to run while indexing is still active, reflecting new results as they are discovered."

Our approach:
1. **WAL mode** ensures reads never block on writes (and vice versa)
2. Search responses include an `indexing_active` flag
3. The UI shows a pulsing "Live" indicator when indexing is in progress
4. Users can re-search to see newly indexed pages

An alternative approach would be to use **Server-Sent Events (SSE)** or **WebSockets** to push new results to the client in real-time as they're indexed. This would eliminate the need for manual re-searching but adds complexity. For a production system, this would be the preferred approach.

---

## Troubleshooting

**Port already in use:** Change the port in `app.py`:
```python
app.run(debug=True, threaded=True, port=3601)
```

**sqlite3.OperationalError: database is locked:** Increase `REQUEST_DELAY` or reduce `MAX_WORKERS`. WAL mode significantly reduces this, but extremely fast writes on slow disks can still cause contention.

**Pages Crawled stays at 0:** Ensure you have internet access. Some sites block automated requests. Test with `https://books.toscrape.com/` which is designed for scraping practice.

---

## License

MIT License. Built for technical assessment purposes.