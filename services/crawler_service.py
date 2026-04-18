import threading
import time
import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from collections import deque, Counter

from database import get_db_connection, close_thread_connection
from utils.html_parser import fetch_html, extract_links, extract_title_and_text, normalize_url

# ---------------------------------------------------------------------------
# Backpressure Configuration
# ---------------------------------------------------------------------------
# These three mechanisms work together to keep the system under control:
#
# 1. MAX_WORKERS: Caps the number of concurrent HTTP fetches (thread pool size)
# 2. MAX_REQUESTS_PER_SECOND: Token bucket refill rate — smooths out bursts
# 3. MAX_QUEUE_DEPTH: Hard ceiling on the BFS frontier — prevents unbounded
#    memory growth when crawling sites with millions of links
# ---------------------------------------------------------------------------
MAX_WORKERS = 5
MAX_REQUESTS_PER_SECOND = 10.0
MAX_QUEUE_DEPTH = 10000

# How often to checkpoint the pending queue to disk (for resume support)
CHECKPOINT_INTERVAL = 50  # every N pages crawled


class TokenBucketRateLimiter:
    """
    A token bucket rate limiter — language-native implementation.

    Tokens are added at a fixed rate (MAX_REQUESTS_PER_SECOND). Each request
    consumes one token. If no tokens are available, the caller blocks until
    one is replenished. This smooths out bursty traffic instead of using a
    naive per-request sleep.
    """

    def __init__(self, rate, burst=None):
        self.rate = rate  # tokens per second
        self.burst = burst or int(rate)  # max tokens that can accumulate
        self.tokens = float(self.burst)
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self):
        """Block until a token is available, then consume it."""
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self.last_refill
                self.last_refill = now
                self.tokens = min(self.burst, self.tokens + elapsed * self.rate)

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
            # No token available — wait a fraction of the refill interval
            time.sleep(1.0 / self.rate)

    @property
    def available_tokens(self):
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            return min(self.burst, self.tokens + elapsed * self.rate)


# Global rate limiter shared across all crawl jobs
_rate_limiter = TokenBucketRateLimiter(rate=MAX_REQUESTS_PER_SECOND)

# In-memory tracking of active jobs (survives across requests within a process)
active_jobs = {}
# Lock for modifying active_jobs dict itself
_jobs_lock = threading.Lock()


def start_crawling(origin_url, max_depth):
    """Starts a new crawl job in a background thread."""
    origin_url = normalize_url(origin_url)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO crawl_jobs (origin_url, max_depth, status) VALUES (?, ?, ?)",
        (origin_url, max_depth, 'running')
    )
    job_id = cursor.lastrowid
    conn.commit()

    with _jobs_lock:
        active_jobs[job_id] = {
            'status': 'running',
            'pages_crawled': 0,
            'queue_size': 1,
            'links_dropped': 0,
            'pages_per_second': 0.0,
        }

    thread = threading.Thread(target=_run_crawl_job, args=(job_id, origin_url, max_depth), daemon=True)
    thread.start()

    return job_id


def resume_crawling(job_id):
    """
    Resumes an interrupted crawl job by loading its pending URLs from the database.
    Returns the job_id if successful, None if the job cannot be resumed.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Verify the job exists and is in a resumable state
    cursor.execute("SELECT origin_url, max_depth, status FROM crawl_jobs WHERE id = ?", (job_id,))
    job = cursor.fetchone()

    if not job or job['status'] == 'completed':
        return None

    origin_url = job['origin_url']
    max_depth = job['max_depth']

    # Load pending URLs
    cursor.execute("SELECT url, depth FROM pending_urls WHERE job_id = ?", (job_id,))
    pending = cursor.fetchall()

    if not pending:
        # No pending URLs saved — nothing to resume from
        # But we can re-set the job to completed since there's nothing left
        cursor.execute("UPDATE crawl_jobs SET status = 'completed' WHERE id = ?", (job_id,))
        conn.commit()
        return None

    # Mark as running again
    cursor.execute("UPDATE crawl_jobs SET status = 'running' WHERE id = ?", (job_id,))
    conn.commit()

    # Count already-crawled pages for this job
    cursor.execute("SELECT COUNT(*) FROM pages WHERE job_id = ?", (job_id,))
    already_crawled = cursor.fetchone()[0]

    with _jobs_lock:
        active_jobs[job_id] = {
            'status': 'running',
            'pages_crawled': already_crawled,
            'queue_size': len(pending),
            'links_dropped': 0,
            'pages_per_second': 0.0,
        }

    # Build the initial queue from saved pending URLs
    initial_queue = [(row['url'], row['depth']) for row in pending]

    thread = threading.Thread(
        target=_run_crawl_job,
        args=(job_id, origin_url, max_depth, initial_queue),
        daemon=True
    )
    thread.start()

    return job_id


def _run_crawl_job(job_id, origin_url, max_depth, initial_queue=None):
    """
    Main crawl loop using BFS with backpressure control.

    The loop coordinates multiple workers via a ThreadPoolExecutor.
    A shared lock protects the visited set, queue, and job metrics.
    """
    if initial_queue:
        queue = deque(initial_queue)
    else:
        queue = deque([(origin_url, 0)])

    # Build visited set from already-crawled pages (for resume correctness)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT url FROM pages WHERE job_id = ?", (job_id,))
    visited = set(row['url'] for row in cursor.fetchall())

    lock = threading.Lock()
    in_flight = 0
    pages_since_checkpoint = 0
    start_time = time.monotonic()
    total_processed = len(visited)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        while queue or in_flight > 0:
            if queue:
                url, depth = queue.popleft()

                with lock:
                    if url in visited or depth > max_depth:
                        _update_queue_size(job_id, len(queue), lock=None)
                        continue
                    visited.add(url)
                    in_flight += 1

                # Rate limiter: block until a token is available
                _rate_limiter.acquire()

                future = executor.submit(
                    _process_url, url, depth, job_id, origin_url,
                    max_depth, queue, visited, lock
                )

                def make_callback(u):
                    def task_done(f):
                        nonlocal in_flight, pages_since_checkpoint, total_processed
                        with lock:
                            in_flight -= 1
                        try:
                            result = f.result()
                            if result:
                                total_processed += 1
                                pages_since_checkpoint += 1
                                # Update pages/sec metric
                                elapsed = time.monotonic() - start_time
                                if elapsed > 0:
                                    with _jobs_lock:
                                        if job_id in active_jobs:
                                            active_jobs[job_id]['pages_per_second'] = round(
                                                total_processed / elapsed, 2
                                            )
                                # Periodic checkpoint for resume support
                                if pages_since_checkpoint >= CHECKPOINT_INTERVAL:
                                    pages_since_checkpoint = 0
                                    _checkpoint_queue(job_id, queue, lock)
                        except Exception as e:
                            logging.error(f"Worker error ({u}): {e}")
                    return task_done

                future.add_done_callback(make_callback(url))

                with lock:
                    _update_queue_size(job_id, len(queue), lock=None)
            else:
                # Queue empty but workers still in flight — wait for them to
                # potentially add new URLs to the queue
                time.sleep(0.05)

    # ---- Crawl complete ----
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE crawl_jobs SET status = 'completed' WHERE id = ?", (job_id,))
    # Update final page count
    cursor.execute("SELECT COUNT(*) FROM pages WHERE job_id = ?", (job_id,))
    final_count = cursor.fetchone()[0]
    cursor.execute("UPDATE crawl_jobs SET pages_crawled = ? WHERE id = ?", (final_count, job_id))
    # Clean up pending URLs (job is done, nothing to resume)
    cursor.execute("DELETE FROM pending_urls WHERE job_id = ?", (job_id,))
    conn.commit()

    with _jobs_lock:
        if job_id in active_jobs:
            active_jobs[job_id]['status'] = 'completed'
            active_jobs[job_id]['queue_size'] = 0
            active_jobs[job_id]['pages_crawled'] = final_count

    logging.info(f"Crawl job {job_id} completed. Total pages: {final_count}")
    close_thread_connection()


def _process_url(url, depth, job_id, origin_url, max_depth, queue, visited, lock):
    """Downloads, parses, indexes a single URL and discovers new links."""
    logging.info(f"Crawling [depth={depth}]: {url}")
    html = fetch_html(url)

    if not html:
        logging.warning(f"Failed to fetch: {url}")
        return False

    title, text = extract_title_and_text(html)

    # Build word frequency index for the inverted index files
    all_text = (title + " " + text).lower()
    words = re.findall(r'\b[a-z]{2,}\b', all_text)
    word_counts = Counter(words)

    os.makedirs(os.path.join("data", "storage"), exist_ok=True)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO pages (url, job_id, origin_url, depth, title, content_text) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (url, job_id, origin_url, depth, title, text)
        )

        if cursor.rowcount > 0:
            # Update in-memory counters
            with _jobs_lock:
                if job_id in active_jobs:
                    active_jobs[job_id]['pages_crawled'] += 1

            # Update DB page count
            cursor.execute(
                "UPDATE crawl_jobs SET pages_crawled = pages_crawled + 1 WHERE id = ?",
                (job_id,)
            )

            # Write to inverted index files (grouped by first letter)
            for word, count in word_counts.items():
                first_letter = word[0]
                filepath = os.path.join("data", "storage", f"{first_letter}.data")
                with open(filepath, "a", encoding="utf-8") as f:
                    f.write(f"{word} {url} {origin_url} {depth} {count}\n")

        conn.commit()
    except Exception as e:
        logging.error(f"Database write error: {e}")
    finally:
        close_thread_connection()

    # Discover new links if we haven't reached max depth
    if depth < max_depth:
        new_links = extract_links(html, url, origin_url)

        with lock:
            for link in new_links:
                if link not in visited:
                    # BACKPRESSURE: Enforce queue depth limit
                    if len(queue) >= MAX_QUEUE_DEPTH:
                        with _jobs_lock:
                            if job_id in active_jobs:
                                active_jobs[job_id]['links_dropped'] += 1
                        break
                    queue.append((link, depth + 1))

            _update_queue_size(job_id, len(queue), lock=None)

    return True


def _update_queue_size(job_id, size, lock=None):
    """Updates the queue size metric for a job."""
    with _jobs_lock:
        if job_id in active_jobs:
            active_jobs[job_id]['queue_size'] = size


def _checkpoint_queue(job_id, queue, lock):
    """
    Saves the current queue state to disk for resume support.
    Called periodically during crawling so that if the process is killed,
    the frontier can be restored.
    """
    with lock:
        pending = list(queue)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pending_urls WHERE job_id = ?", (job_id,))
        for url, depth in pending:
            cursor.execute(
                "INSERT INTO pending_urls (job_id, url, depth) VALUES (?, ?, ?)",
                (job_id, url, depth)
            )
        conn.commit()
        logging.info(f"Checkpoint saved for job {job_id}: {len(pending)} pending URLs")
    except Exception as e:
        logging.error(f"Checkpoint error: {e}")


def mark_interrupted_jobs():
    """
    Called on startup: any jobs still marked 'running' in the DB were
    interrupted by a previous crash/shutdown. Mark them so the UI can
    offer a Resume button.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE crawl_jobs SET status = 'interrupted' WHERE status = 'running'"
        )
        count = cursor.rowcount
        conn.commit()
        if count > 0:
            logging.info(f"Marked {count} interrupted job(s) from previous session.")
    except Exception as e:
        logging.error(f"Error marking interrupted jobs: {e}")


def get_status():
    """Returns full system status including backpressure metrics."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM pages")
    total_pages = cursor.fetchone()[0]

    cursor.execute("""
        SELECT cj.*, 
               (SELECT COUNT(*) FROM pages p WHERE p.job_id = cj.id) as pages_crawled_db
        FROM crawl_jobs cj ORDER BY cj.created_at DESC LIMIT 10
    """)
    recent_jobs = []
    for row in cursor.fetchall():
        job = dict(row)
        jid = job['id']

        # Merge live in-memory metrics with DB data for running jobs
        with _jobs_lock:
            if jid in active_jobs and active_jobs[jid]['status'] == 'running':
                job['pages_crawled'] = active_jobs[jid].get('pages_crawled', job.get('pages_crawled_db', 0))
                job['queue_size'] = active_jobs[jid].get('queue_size', 0)
                job['links_dropped'] = active_jobs[jid].get('links_dropped', 0)
                job['pages_per_second'] = active_jobs[jid].get('pages_per_second', 0.0)
                job['status'] = 'running'
            else:
                job['pages_crawled'] = job.get('pages_crawled_db', job.get('pages_crawled', 0))
                job['queue_size'] = 0
                job['links_dropped'] = 0
                job['pages_per_second'] = 0.0

        # Clean up internal-only fields
        job.pop('pages_crawled_db', None)
        recent_jobs.append(job)

    active_count = sum(1 for j in active_jobs.values() if j['status'] == 'running')

    return {
        "total_pages_indexed": total_pages,
        "active_jobs_count": active_count,
        "recent_jobs": recent_jobs,
        "backpressure": {
            "max_workers": MAX_WORKERS,
            "max_queue_depth": MAX_QUEUE_DEPTH,
            "max_requests_per_second": MAX_REQUESTS_PER_SECOND,
            "available_tokens": round(_rate_limiter.available_tokens, 1),
        }
    }