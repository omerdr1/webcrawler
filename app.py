from flask import Flask, request, jsonify, send_from_directory
import os

from database import init_db
from services import crawler_service, search_service

# Initialize database and mark any interrupted jobs from a previous session
init_db()
crawler_service.mark_interrupted_jobs()

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Static file serving — the UI is a single-page application in /demo
# ---------------------------------------------------------------------------

@app.route('/')
def home():
    """Serves the main SPA entry point."""
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), 'demo'), 'index.html'
    )


@app.route('/demo/<path:filename>')
def demo_static(filename):
    """Serves static assets (CSS, JS, images) from the demo directory."""
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), 'demo'), filename
    )


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.route('/api/index', methods=['POST'])
def start_index():
    """
    Initiates a new background crawl job.
    Accepts JSON: { "origin": "https://...", "k": 2 }
    """
    data = request.get_json(force=True, silent=True) or {}
    url = data.get('origin', '').strip()
    try:
        depth = int(data.get('k', 2))
    except (ValueError, TypeError):
        depth = 2

    if not url:
        return jsonify({"error": "origin URL is required"}), 400

    if not url.startswith('http://') and not url.startswith('https://'):
        url = 'https://' + url

    job_id = crawler_service.start_crawling(url, depth)
    return jsonify({"job_id": job_id, "status": "started", "origin": url, "k": depth})


@app.route('/api/resume/<int:job_id>', methods=['POST'])
def resume_job(job_id):
    """Resumes an interrupted crawl job."""
    result = crawler_service.resume_crawling(job_id)
    if result:
        return jsonify({"job_id": result, "status": "resumed"})
    return jsonify({"error": "Job cannot be resumed (completed or no pending URLs)"}), 400


@app.route('/api/search')
def search():
    """
    Searches indexed pages.
    Query params: query (string), sortBy (optional, 'relevance')
    Returns list of (relevant_url, origin_url, depth) triples.
    """
    query = request.args.get('query', '').strip()
    sort_by = request.args.get('sortBy', '')

    if not query:
        return jsonify({"results": [], "indexing_active": search_service.is_indexing_active()})

    results = search_service.search(query, sort_by=sort_by if sort_by else None)

    return jsonify({
        "results": results,
        "query": query,
        "count": len(results),
        "indexing_active": search_service.is_indexing_active()
    })


@app.route('/api/status')
def api_status():
    """Returns system status with backpressure metrics."""
    status_data = crawler_service.get_status()
    return jsonify(status_data)


if __name__ == '__main__':
    # threaded=True allows Flask to handle multiple requests concurrently,
    # which is critical so the UI remains responsive during background crawling.
    app.run(debug=True, threaded=True, port=3600)