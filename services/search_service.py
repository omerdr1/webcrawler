import os
from database import get_db_connection

def search(query, sort_by=None):
    """Veritabanında veya dosya sisteminde verilen sorguyla eşleşen sayfaları arar."""
    
    if sort_by == 'relevance':
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
                                "url": url,
                                "origin_url": origin,
                                "depth": depth,
                                "frequency": frequency,
                                "relevance_score": score
                            })
                        except ValueError:
                            pass
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        return results
        
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