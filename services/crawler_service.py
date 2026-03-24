import threading
import time
import os
import re
from concurrent.futures import ThreadPoolExecutor
from collections import deque, Counter
import logging

from database import get_db_connection
from utils.html_parser import fetch_html, extract_links, extract_title_and_text

MAX_WORKERS = 5
REQUEST_DELAY = 0.1

active_jobs = {}

def start_crawling(origin_url, max_depth):
    """Yeni bir tarama işini arka plan thread'inde başlatır."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO crawl_jobs (origin_url, max_depth, status) VALUES (?, ?, ?)",
        (origin_url, max_depth, 'running')
    )
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    active_jobs[job_id] = {'status': 'running', 'pages_crawled': 0, 'queue_size': 1}

    thread = threading.Thread(target=_run_crawl_job, args=(job_id, origin_url, max_depth))
    thread.daemon = True
    thread.start()
    
    return job_id

def _run_crawl_job(job_id, origin_url, max_depth):
    """Tarama işini yürüten ana mantık."""
    queue = deque([(origin_url, 0)])
    visited = set()
    
    # Eşzamanlılık için güvenlik kilidi (Lock) ve aktif görev sayacı
    lock = threading.Lock()
    in_flight = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Kuyrukta eleman varken VEYA hala indirilen sayfalar varken döngüye devam et
        while queue or in_flight > 0:
            if queue:
                url, depth = queue.popleft()
                
                with lock:
                    if url in visited or depth > max_depth:
                        continue
                    visited.add(url)
                    in_flight += 1 # Yeni bir işçi göreve başladı
                
                # Görevi başlat ve bitince çalışacak bir "callback" (geri çağırma) fonksiyonu ekle
                future = executor.submit(_process_url, url, depth, job_id, origin_url, max_depth, queue, visited, lock)
                
                def task_done(f):
                    nonlocal in_flight
                    with lock:
                        in_flight -= 1 # İşçi görevi bitirdi
                    try:
                        f.result() # Eğer thread içinde bir hata olduysa bunu fırlatır
                    except Exception as e:
                        logging.error(f"İş parçacığı hatası ({url}): {e}")

                future.add_done_callback(task_done)
                
                time.sleep(REQUEST_DELAY)
            else:
                # Kuyruk boş ama hala çalışan (in_flight) işçiler var. Onların bitmesini bekle.
                time.sleep(0.1)

    # Döngü bittiğinde iş tamamlanmıştır
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE crawl_jobs SET status = 'completed' WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    
    if job_id in active_jobs:
        active_jobs[job_id]['status'] = 'completed'
        active_jobs[job_id]['queue_size'] = 0
    logging.info(f"Tarama işi {job_id} tamamlandı.")


def _process_url(url, depth, job_id, origin_url, max_depth, queue, visited, lock):
    """Tek bir URL'yi indirir, ayrıştırır ve veritabanına kaydeder."""
    logging.info(f"Geziliyor [Derinlik: {depth}]: {url}")
    html = fetch_html(url)
    
    if not html:
        logging.warning(f"Sayfa indirilemedi veya boş: {url}")
        return

    title, text = extract_title_and_text(html)
    
    all_text = (title + " " + text).lower()
    words = re.findall(r'\b[a-z]{2,}\b', all_text)
    word_counts = Counter(words)
    
    os.makedirs(os.path.join("data", "storage"), exist_ok=True)
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO pages (url, job_id, origin_url, depth, title, content_text) VALUES (?, ?, ?, ?, ?, ?)",
            (url, job_id, origin_url, depth, title, text)
        )
        # Eğer etkilenen satır 1 ise (yani gerçekten yeni bir kayıt eklendiyse) sayacı artır
        if cursor.rowcount > 0:
            with lock:
                if job_id in active_jobs:
                    active_jobs[job_id]['pages_crawled'] += 1
                
                # Write to inverted index files
                for word, count in word_counts.items():
                    first_letter = word[0]
                    filepath = os.path.join("data", "storage", f"{first_letter}.data")
                    with open(filepath, "a", encoding="utf-8") as f:
                        f.write(f"{word} {url} {origin_url} {depth} {count}\n")
        conn.commit()
    except Exception as e:
        logging.error(f"Veritabanına yazarken hata: {e}")
    finally:
        conn.close()

    if depth < max_depth:
        new_links = extract_links(html, url, origin_url) # current url'ye göre linkleri tamamla, origin'e göre netloc sınırla
        
        with lock:
            for link in new_links:
                if link not in visited:
                    queue.append((link, depth + 1))
            
            if job_id in active_jobs:
                active_jobs[job_id]['queue_size'] = len(queue)

def get_status():
    """Sistemin genel durumunu döndürür."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pages")
    total_pages = cursor.fetchone()[0]
    cursor.execute("""
        SELECT cj.*, (SELECT COUNT(*) FROM pages p WHERE p.job_id = cj.id) as pages_crawled
        FROM crawl_jobs cj ORDER BY cj.created_at DESC LIMIT 5
    """)
    recent_jobs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    for job in recent_jobs:
        if job['id'] in active_jobs and job['status'] != 'completed':
            job['queue_size'] = active_jobs[job['id']].get('queue_size', 0)

    return {
        "total_pages_indexed": total_pages,
        "active_jobs_count": sum(1 for j in active_jobs.values() if j['status'] == 'running'),
        "recent_jobs": recent_jobs
    }