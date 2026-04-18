# Product Requirements Document (PRD): Web Crawler & Search Engine

## 1. Product Overview

A single-machine, locally runnable Web Crawler and Search Engine that exposes two core capabilities: **index** (crawling) and **search** (querying). The system supports full concurrency — search returns live results while the indexer is actively running in the background. Built-in backpressure mechanisms ensure the system manages load in a controlled way, and crawl jobs can be resumed after interruption.

## 2. Core Capabilities

### 2.1. Index (Crawler)

- **Input:** `origin` (URL string) and `k` (integer representing max depth/hops).
- **Behavior:**
  - Initiates a Breadth-First Search (BFS) web crawl starting from `origin`.
  - Extracts all valid `<a href>` links and follows them up to depth `k`.
  - Never crawls the same URL twice (visited set + URL normalization).
  - Extracts and stores the page `title` and readable `text_content`.
- **Backpressure (3 mechanisms):**
  1. **Token Bucket Rate Limiter** — Smooths burst traffic at `MAX_REQUESTS_PER_SECOND = 10`. Workers acquire a token before each fetch; if none are available, they block until refill.
  2. **Bounded Queue** — `MAX_QUEUE_DEPTH = 10,000`. When the BFS frontier exceeds this limit, newly discovered links are dropped and counted. Prevents unbounded memory growth.
  3. **Worker Pool** — `MAX_WORKERS = 5` concurrent threads via `ThreadPoolExecutor`. Caps CPU and network usage.
- **Resumability:**
  - The BFS frontier is checkpointed to a `pending_urls` database table every 50 pages.
  - On startup, any previously-running jobs are marked as `interrupted`.
  - Interrupted jobs can be resumed via a dedicated API endpoint, restoring the frontier from the last checkpoint.
- **Concurrency:**
  - Uses Python `threading` and `concurrent.futures.ThreadPoolExecutor` (language-native, no heavy frameworks).
  - Shared state (visited set, queue, metrics) protected by `threading.Lock()`.

### 2.2. Search (Query Engine)

- **Input:** `query` (string keyword), optional `sortBy` parameter.
- **Output:** List of triples `(relevant_url, origin_url, depth)` with optional enrichment fields.
- **Two Search Modes:**
  1. **Keyword (default):** SQL `LIKE` search across page titles and content text. Returns all matching pages.
  2. **Relevance (`sortBy=relevance`):** Reads from inverted index files (`data/storage/{letter}.data`) for exact word frequency matching. Computes `score = (frequency × 10) + 1000 − (depth × 5)` and sorts descending.
- **Concurrent Search:** SQLite WAL mode allows read queries to execute without being blocked by write operations. Search responses include an `indexing_active` flag so the UI can display a "live results" indicator.

### 2.3. User Interface

A single-page web application with three tabs:

1. **Index Tab** — Form to submit crawl jobs (origin URL + depth). Includes explanation of backpressure mechanisms.
2. **Search Tab** — Search form with keyword/relevance mode toggle. Results displayed as cards with depth badges, origin URLs, and relevance score bars.
3. **Status Tab** — Real-time dashboard (2s polling) showing:
   - Total pages indexed
   - Active job count
   - Backpressure metrics (available tokens, max queue depth, max workers, max rate)
   - Queue utilization gauge (color-coded: green → amber → red)
   - Job table with live progress, pages/sec, queue depth, and resume buttons for interrupted jobs
   - Toast notifications for job events

## 3. Technical Requirements

- **Language:** Python 3.8+
- **Database:** SQLite with WAL mode (zero-configuration, file-based, supports concurrent read/write)
- **Libraries:** Only:
  - `flask` — HTTP server and API routing
  - `requests` — HTTP client for page fetching
  - `beautifulsoup4` — HTML parsing
- **No** crawling frameworks (Scrapy, etc.), rate-limiting libraries, or out-of-the-box search engines

## 4. Data Model

### SQLite Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `crawl_jobs` | Tracks crawl job metadata | `id`, `origin_url`, `max_depth`, `status`, `pages_crawled`, `created_at` |
| `pages` | Stores crawled page data | `url` (PK), `job_id`, `origin_url`, `depth`, `title`, `content_text`, `crawled_at` |
| `pending_urls` | Resume support: persists BFS frontier | `job_id`, `url`, `depth` |

### Inverted Index Files

- Located at `data/storage/{first_letter}.data`
- Space-delimited format: `word url origin_url depth frequency`
- Used exclusively for relevance-scored search queries

## 5. API Contract

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/index` | Start a crawl job. Body: `{"origin": "...", "k": 2}` |
| `POST` | `/api/resume/<job_id>` | Resume an interrupted job |
| `GET`  | `/api/search?query=...&sortBy=relevance` | Search indexed pages |
| `GET`  | `/api/status` | System status with backpressure metrics |
| `GET`  | `/` | Serves the SPA |