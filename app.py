from flask import Flask, render_template, request, jsonify, redirect, url_for

# Veritabanını ve servisleri import et
from database import init_db
from services import crawler_service, search_service

# Uygulama başlamadan önce veritabanını hazırla
init_db()

app = Flask(__name__, template_folder='demo', static_folder='demo')

@app.route('/')
def home():
    """Ana sayfa, indexleme formunu gösterir."""
    return render_template('crawler.html')

@app.route('/index', methods=['POST'])
def start_index():
    """Indexleme işini başlatan endpoint."""
    url = request.form.get('origin_url')
    try:
        depth = int(request.form.get('depth', 2))
    except (ValueError, TypeError):
        depth = 2

    if not url:
        return "URL girmek zorunludur!", 400
    
    crawler_service.start_crawling(url, depth)
    return redirect(url_for('status'))

@app.route('/search')
def search_page():
    """Arama sayfasını gösterir ve arama yapar."""
    query = request.args.get('query', '')
    sort_by = request.args.get('sortBy', '')
    results = []
    if query:
        results = search_service.search(query, sort_by=sort_by)
        
    if sort_by == 'relevance' or request.headers.get('Accept') == 'application/json':
        return jsonify(results)
        
    return render_template('search.html', query=query, results=results)

@app.route('/status')
def status():
    """Sistem durumunu gösteren sayfayı render eder."""
    return render_template('status.html')

@app.route('/api/status')
def api_status():
    """Sistem durumu verilerini JSON formatında döndüren API endpoint'i."""
    status_data = crawler_service.get_status()
    return jsonify(status_data)

if __name__ == '__main__':
    # threaded=True, Flask'in aynı anda birden fazla isteği işlemesini sağlar.
    # Bu, arka plan taraması çalışırken UI'ın donmamasını sağlar.
    app.run(debug=True, threaded=True, port=3600)