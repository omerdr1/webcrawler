from database import get_db_connection

def search(query):
    """Veritabanında verilen sorguyla eşleşen sayfaları arar."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Arama terimini LIKE sorgusu için hazırla
    search_term = f"%{query}%"
    
    # content_text veya title içinde arama yap
    cursor.execute(
        "SELECT url, origin_url, depth, title FROM pages WHERE title LIKE ? OR content_text LIKE ?",
        (search_term, search_term)
    )
    
    results = cursor.fetchall()
    conn.close()
    
    # Sonuçları istenen (relevant_url, origin_url, depth) formatına çevir
    formatted_results = [
        {"url": row["url"], "origin": row["origin_url"], "depth": row["depth"], "title": row["title"]}
        for row in results
    ]
    return formatted_results