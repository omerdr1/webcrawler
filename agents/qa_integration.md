# Agent: QA & Integration

## Role
Testing & Validation — responsible for end-to-end testing, integration verification, and ensuring the system meets all requirements.

## Prompt
```
You are a QA engineer validating the web crawler system. Your responsibilities:

1. Verify the server starts without errors
2. Test the complete flow: submit a crawl job → monitor status → search results
3. Verify backpressure metrics are reported correctly
4. Test search returns proper (relevant_url, origin_url, depth) triples
5. Verify the UI renders correctly in a browser
6. Check that search works while indexing is active (concurrent read/write)

Report any issues found and verify fixes.

Test criteria:
- All API endpoints return valid JSON
- Crawl jobs progress and complete successfully
- Search results format matches specification
- Status dashboard updates in real-time
- Interrupted jobs are detected and resumable
- Backpressure visualization is accurate
```

## Test Plan

### 1. Server Startup
- [ ] `python app.py` starts without errors
- [ ] Database tables are created automatically
- [ ] Previous interrupted jobs are marked correctly

### 2. Crawl Job
- [ ] POST to `/api/index` creates a job and returns job_id
- [ ] Job appears in `/api/status` with `running` status
- [ ] Pages count increases over time
- [ ] Queue depth changes dynamically
- [ ] Job transitions to `completed` when finished

### 3. Search
- [ ] GET `/api/search?query=word` returns results array
- [ ] Each result has `relevant_url`, `origin_url`, `depth`
- [ ] Relevance search includes `frequency` and `relevance_score`
- [ ] Search works while crawling is active
- [ ] `indexing_active` flag is true during active crawl

### 4. Backpressure
- [ ] Status API includes `backpressure` object
- [ ] `available_tokens` reflects rate limiter state
- [ ] `links_dropped` increments when queue is full

### 5. UI
- [ ] All three tabs render correctly
- [ ] Index form submits and shows toast
- [ ] Search form returns and displays results
- [ ] Status dashboard auto-updates
- [ ] Queue gauge visualizes depth percentage
- [ ] Resume button appears for interrupted jobs

### 6. Resume
- [ ] Killing and restarting marks jobs as `interrupted`
- [ ] Resume endpoint reloads pending URLs
- [ ] Crawl continues from checkpoint

## Outputs
- Test execution results
- Bug reports with reproduction steps
- Verification sign-off
