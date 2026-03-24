import sqlite3
import logging

# Loglama ayarlarını yapılandır
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_NAME = "crawler.db"

def get_db_connection():
    """Veritabanına bir bağlantı oluşturur ve döner."""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Veritabanı tablolarını (eğer mevcut değillerse) oluşturur."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS crawl_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origin_url TEXT NOT NULL,
            max_depth INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', -- pending, running, completed
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            url TEXT PRIMARY KEY,
            job_id INTEGER,
            origin_url TEXT NOT NULL,
            depth INTEGER NOT NULL,
            title TEXT,
            content_text TEXT,
            crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES crawl_jobs (id)
        )
        """)
        
        # Gezilmiş URL'leri takip etmek için ayrı bir set yerine doğrudan 'pages' tablosunu kullanacağız.
        # Bu, aynı sayfanın tekrar gezilmesini engeller.

        conn.commit()
        logging.info("Veritabanı başarıyla başlatıldı ve tablolar kontrol edildi.")
    except sqlite3.Error as e:
        logging.error(f"Veritabanı hatası: {e}")
    finally:
        if conn:
            conn.close()