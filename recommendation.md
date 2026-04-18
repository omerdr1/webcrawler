# Recommendations for Production Deployment

## Infrastructure & Scaling

To transition this crawler from a single-machine exercise into a production-grade system, the architecture should evolve in two key areas: **data layer** and **compute layer**.

For the data layer, SQLite should be replaced with **PostgreSQL** for relational storage (job metadata, page records) and the custom `data/storage/*.data` inverted index files should be replaced with a purpose-built search engine like **Elasticsearch** or **Typesense**. These systems natively handle distributed full-text indexing, BM25/TF-IDF relevance scoring, faceted search, and horizontal scaling — capabilities that the current file-based approach cannot match at scale. PostgreSQL's `LISTEN/NOTIFY` mechanism could also replace the polling-based status updates with real-time push notifications.

For the compute layer, the native `ThreadPoolExecutor` model should be replaced with a **distributed task queue** such as Celery (backed by Redis or RabbitMQ) or a streaming platform like Apache Kafka. This enables horizontal scaling by adding worker nodes that consume URLs from the queue independently, inherently solving backpressure through queue-level flow control. The token bucket rate limiter should be moved to a shared Redis instance (using a Lua script for atomicity) so that rate limits are enforced globally across all workers rather than per-process. Python's GIL limitation becomes irrelevant when work is distributed across multiple processes and machines.

## Compliance & Resilience

Production crawlers require several additional capabilities beyond the core crawl loop:

1. **`robots.txt` compliance** — Automatically fetch, parse, and respect `robots.txt` directives for every domain before crawling. Implement `Crawl-delay` headers where specified. This is both an ethical requirement and a legal one in many jurisdictions.

2. **Domain-specific rate limiting** — Instead of a single global rate limiter, maintain per-domain rate limits to avoid overwhelming individual servers. A polite crawler should typically wait 1–2 seconds between requests to the same domain.

3. **Proxy rotation & IP management** — High-volume crawling from a single IP will trigger blocks and CAPTCHAs. Use a rotating proxy service and implement exponential backoff on HTTP 429/503 responses.

4. **JavaScript rendering** — The current `requests`-based approach cannot execute JavaScript, which means Single Page Applications (SPAs) and dynamically-loaded content will be invisible. Integrating a headless browser engine (Playwright or Puppeteer) for selective rendering would expand coverage significantly, though this comes with substantial resource costs and should be used selectively.

5. **Deduplication & content normalization** — At scale, near-duplicate pages (pagination, sort parameters, session tokens in URLs) can waste significant crawl budget. Implement content hashing (SimHash or MinHash) to detect and skip near-duplicate content.

6. **Monitoring & alerting** — Production systems should export metrics (Prometheus), structured logs (ELK stack), and alerts (PagerDuty/OpsGenie) for crawler health, error rates, queue depth trends, and storage growth.