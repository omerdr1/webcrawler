import os
from database import get_db_connection
from services.crawler_service import active_jobs


def search(query, sort_by=None):
    """
    Searches indexed pages for the given query.

    Returns a list of triples: (relevant_url, origin_url, depth)
    With optional enrichment fields (title, frequency, relevance_score).

    Two modes:
    - Default: SQL LIKE search across page titles and content
    - sortBy=relevance: Uses the inverted index .data files for exact word
      frequency matching with a scoring formula

    This function is safe to call while the indexer is active because SQLite
    is running in WAL mode, which allows concurrent readers and writers.
    """

    if sort_by == 'relevance':
        return _search_by_relevance(query)

    return _search_by_keyword(query)


def _search_by_keyword(query):
    """SQL-based keyword search using LIKE matching."""
    conn = get_db_connection()
    cursor = conn.cursor()

    search_term = f"%{query}%"
    cursor.execute(
        "SELECT url, origin_url, depth, title FROM pages "
        "WHERE title LIKE ? OR content_text LIKE ?",
        (search_term, search_term)
    )

    results = cursor.fetchall()

    # Format as (relevant_url, origin_url, depth) triples with enrichment
    formatted = [
        {
            "relevant_url": row["url"],
            "origin_url": row["origin_url"],
            "depth": row["depth"],
            "title": row["title"] or ""
        }
        for row in results
    ]
    return formatted


def _search_by_relevance(query):
    """
    File-based inverted index search with relevance scoring.

    Reads from data/storage/{first_letter}.data files which contain
    space-delimited records: word url origin_url depth frequency

    Scoring formula: score = (frequency * 10) + 1000 - (depth * 5)
    Results are sorted by descending relevance score.
    """
    word = query.lower().strip()
    if not word or not word[0].isalpha():
        return []

    first_letter = word[0]
    filepath = os.path.join("data", "storage", f"{first_letter}.data")

    results = []
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(' ')
                if len(parts) >= 5 and parts[0] == word:
                    try:
                        url = parts[1]
                        origin = parts[2]
                        depth = int(parts[3])
                        frequency = int(parts[4])

                        score = (frequency * 10) + 1000 - (depth * 5)
                        results.append({
                            "relevant_url": url,
                            "origin_url": origin,
                            "depth": depth,
                            "frequency": frequency,
                            "relevance_score": score
                        })
                    except ValueError:
                        pass

    results.sort(key=lambda x: x['relevance_score'], reverse=True)
    return results


def is_indexing_active():
    """Returns True if any crawl job is currently running."""
    return any(j['status'] == 'running' for j in active_jobs.values())