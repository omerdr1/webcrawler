import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

def fetch_html(url):
    """Verilen URL'den HTML içeriğini indirir."""
    try:
        # Gerçek bir tarayıcı gibi görünmek engellenme riskini azaltır
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        response = requests.get(url, timeout=10, headers=headers)
        response.raise_for_status() 
        return response.text
    except requests.RequestException as e:
        # Hata durumunu loglamak faydalıdır, ama programı çökertmemelidir
        # print(f"Fetch Error: {url} -> {e}") 
        return None

def extract_title_and_text(html_content):
    """HTML'den başlığı ve okunabilir metni çıkarır."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    for script_or_style in soup(['script', 'style']):
        script_or_style.decompose()
        
    title = soup.title.string.strip() if soup.title else ''
    text = soup.get_text(separator=' ', strip=True)
    return title, text

def extract_links(html_content, current_url, origin_url):
    """HTML'den tüm geçerli linkleri çıkarır ve mutlak URL'lere dönüştürür."""
    soup = BeautifulSoup(html_content, 'html.parser')
    links = set()
    base_netloc = urlparse(origin_url).netloc

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href'].strip()
        if href.startswith('#') or href.startswith('mailto:') or href.startswith('javascript:'):
            continue
        
        absolute_url = urljoin(current_url, href)
        if urlparse(absolute_url).netloc == base_netloc:
            links.add(absolute_url)
            
    return list(links)