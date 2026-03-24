# Product Requirements Document (PRD): Web Crawler & Search Engine

## 1. Product Overview
The objective is to build a single-machine, locally runnable Web Crawler and Search Engine. The system must expose two distinct capabilities: `index` (crawling) and `search` (querying). A critical requirement is that the system must support concurrency—specifically, `search` must be fully operational and reflect new data while `index` is actively running in the background.

## 2. Core Capabilities

### 2.1. Index (Crawler)
- **Input:** `origin` (URL string) and `k` (integer representing max depth/hops).
- **Behavior:**
  - Initiates a Breadth-First Search (BFS) web crawl starting from `origin`.
  - Extracts all valid `<a href>` links and follows them up to depth `k`.
  - Must *never* crawl the same URL twice (cycle detection).
  - Extracts and stores the page `title` and readable `text_content`.
- **Constraints & Architecture:**
  - Must use language-native concurrency (e.g., Python's `threading` and `concurrent.futures`) rather than heavy frameworks like Scrapy.
  - **Back Pressure:** Must implement load control (e.g., `MAX_WORKERS` limit and request rate-limiting/delays) to prevent overwhelming the host or target server.
  - State should be managed in a way that handles concurrent read/writes safely.

### 2.2. Search (Query Engine)
- **Input:** `query` (string keyword).
- **Behavior:**
  - Searches the indexed database for pages where the `query` exists in the title or content.
  - Must be able to run while the indexer is active (non-blocking).
- **Output:** Returns a list of triples in the format: `(relevant_url, origin_url, depth)`.

### 2.3. User Interface
- Provide a simple Web UI (or CLI) with three main views/commands:
  1. **Initiate:** Form to start the `index` capability.
  2. **Search:** Form to execute the `search` capability and display formatted results.
  3. **Status:** Dashboard showing indexing progress, total pages, active job count, and current queue depth.

## 3. Technical Requirements
- **Language:** Python
- **Database:** SQLite (must be local, file-based, requiring no external server installation). Using SQLite also fulfills the bonus requirement: the system can resume/preserve data after an interruption.
- **Libraries:** Limit external libraries to HTTP clients (`requests`), HTML parsers (`beautifulsoup4`), and lightweight Web Frameworks (`flask`). Do not use out-of-the-box crawling libraries.

## 4. Expected Data Model
- `crawl_jobs`: Tracks job ID, origin_url, max_depth, and status.
- `pages`: Tracks unique URLs, associated job_id, depth, title, and parsed content.