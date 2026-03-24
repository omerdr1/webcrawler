# Web Crawler & Search Engine

A concurrent web crawling platform and search engine built with Python and Flask. It features real-time monitoring, intelligent search capabilities, and a lightweight file-based SQLite database, allowing you to search through indexed content while the crawler is actively running in the background.

## 🌟 Features

* **Multi-threaded Web Crawler:** Utilizes Python's `ThreadPoolExecutor` for concurrent page fetching without blocking the main server.
* **Real-time Search Engine:** Query indexed pages instantly, even while new pages are being crawled and added to the database.
* **Back-pressure Management:** Built-in rate limiting (`REQUEST_DELAY`) and concurrency limits (`MAX_WORKERS`) to prevent overloading host and target servers.
* **Persistent SQLite Storage:** Zero-configuration database automatically creates tables (`crawl_jobs`, `pages`). Supports resuming/maintaining data across server restarts.
* **Responsive Web Interface:** Clean HTML/CSS frontend to manage indexing, monitor system status, and explore search results.
* **Smart Cycle Detection:** Prevents infinite loops by tracking visited URLs and restricting crawls to the specified depth (`k`).

---

## 🚀 Quick Start

### Prerequisites
* Python 3.8 or higher
* Web browser (Chrome, Firefox, Safari, Edge)

### Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/web-crawler.git
   cd web-crawler
   ```

2. **Create and activate a virtual environment (Recommended):**

   *On macOS/Linux:*
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

   *On Windows:*
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Start the application:**
   ```bash
   python app.py
   ```
   The server will start on `http://127.0.0.1:5000` (or the configured port) and automatically initialize the `crawler.db` database.

5. **Open the web interface:**
   Navigate to `http://127.0.0.1:5000/` in your web browser.

---

## 📖 Usage Guide

### 1. Creating a Crawl Job
Navigate to the Index page (`http://127.0.0.1:5000/`).

Fill in the parameters:
- **Origin URL:** The starting point (e.g., `http://books.toscrape.com/`).
- **Max Depth (k):** How many links deep the crawler should go (0 = only the origin page, 2 = origin -> link -> link).

Click **"Start Indexing"**. The job will run in the background.

### 2. Monitoring Crawlers
Navigate to the Status page (`http://127.0.0.1:5000/status`).

The dashboard auto-refreshes every 3 seconds to show:
- **Total Pages Indexed**
- **Active Crawling Jobs**
- **Live details for recent jobs** (Status, Pages Crawled, Current Queue Size).

### 3. Searching Content
Navigate to the Search page (`http://127.0.0.1:5000/search`).

Enter a keyword (e.g., "poetry", "python").

The engine will query the SQLite database (`LIKE` search on titles and text content) and return a formatted table displaying the Relevant URL, Origin URL, and Depth.

---

## 🔧 Routes & Endpoints
The application uses standard HTTP methods for communication between the UI and the server.

### Web Views (UI)
- `GET /` : Renders the Crawler Initiation form.
- `GET /search` : Renders the Search interface and handles query parameters.
- `GET /status` : Renders the Status dashboard.

### API & Actions
- `POST /index` : Initiates a new background crawl job.
  - *Form Data:* `origin_url` (string), `depth` (integer)

- `GET /api/status` : Returns real-time system metrics in JSON format.
  ```json
  {
    "active_jobs_count": 1,
    "total_pages_indexed": 145,
    "recent_jobs": [
      {
        "id": 1,
        "origin_url": "http://books.toscrape.com/",
        "max_depth": 2,
        "status": "running",
        "pages_crawled": 145,
        "queue_size": 32
      }
    ]
  }
  ```

---

## 📁 Project Structure

```plaintext
web-crawler/
├── app.py                      # 🚀 Main Flask application and routing
├── database.py                 # 🗄️ SQLite initialization and connection pool
├── requirements.txt            # 📦 Project dependencies
├── services/                   # 🏗️ Business logic layer
│   ├── crawler_service.py      #    Crawler logic, ThreadPool, BFS Queue
│   └── search_service.py       #    Database querying and formatting
├── utils/                      # 🛠️ Core utilities
│   ├── html_parser.py          #    Request handling, BeautifulSoup parsing
│   └── test_html_parser.py     #    Unit tests for parser (Optional)
├── demo/                       # 🎨 Web interface templates
│   ├── crawler.html            #    Index initiation form
│   ├── search.html             #    Search interface
│   └── status.html             #    Real-time monitoring dashboard
├── crawler.db                  # 💾 SQLite Database (Auto-generated)
└── README.md                   # 📖 This documentation file
```

---

## ⚙️ Configuration
You can tweak the performance and behavior of the crawler by modifying the constants at the top of `services/crawler_service.py`:

- `MAX_WORKERS = 5`: Maximum number of concurrent threads downloading pages. Increase for faster crawling, decrease if you encounter memory/CPU issues.
- `REQUEST_DELAY = 0.1`: Time in seconds to wait between processing queue items. Acts as a rate limiter to prevent IP bans.

---

## 🔍 How It Works

### Crawler Architecture
- **Breadth-First Search (BFS):** Uses Python's `collections.deque` to process URLs level by level, ensuring depth constraints are strictly followed.
- **Concurrency & Thread Safety:** The main loop dispatches URLs to a `ThreadPoolExecutor`. A `threading.Lock()` is used to safely update shared resources (like the visited set and active job counters) preventing race conditions.
- **Resiliency:** Automatically removes `<script>` and `<style>` tags before indexing text to ensure clean search results. Handles 404s and connection timeouts gracefully without crashing the main thread.

### Search System
- **Data Model:** Extracted text and titles are stored alongside their `origin_url` and discovery depth in the `pages` table.
- **Non-blocking:** Because SQLite is configured with `check_same_thread=False` and Flask runs with `threaded=True`, `SELECT` queries from the search page run perfectly even while the background thread executes `INSERT` statements.

---

## 🚨 Troubleshooting

### Port already in use:
If `app.run()` fails because port 5000 is occupied, you can change it in `app.py`:
```python
app.run(debug=True, threaded=True, port=5001)
```

### sqlite3.OperationalError: database is locked:
This happens if the crawler is writing data too aggressively for your disk speed. Try increasing the `REQUEST_DELAY` in `crawler_service.py` to `0.5`.

### Pages Crawled stays at 0:
Ensure you have an active internet connection. Some websites actively block generic User-Agents. Our `html_parser.py` uses a standard Chrome User-Agent, but heavily protected sites (like those using Cloudflare) might still reject requests with a `403 Forbidden`. Test with `http://books.toscrape.com/`.

---

## 📜 License
This project is licensed under the MIT License. Built for technical assessment purposes.