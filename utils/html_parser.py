import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, urlunparse


def normalize_url(url):
    """
    Normalizes a URL to reduce duplicate crawls:
    - Strips fragment identifiers (#section)
    - Removes trailing slashes from paths
    - Lowercases the scheme and netloc
    """
    parsed = urlparse(url)
    # Remove fragment, lowercase scheme + netloc
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        fragment='',
        path=parsed.path.rstrip('/') if parsed.path != '/' else '/'
    )
    return urlunparse(normalized)


def fetch_html(url):
    """Downloads HTML content from the given URL."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        response = requests.get(url, timeout=10, headers=headers, allow_redirects=True)
        response.raise_for_status()

        # Only process HTML content, skip binary files
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' not in content_type and 'application/xhtml' not in content_type:
            return None

        return response.text
    except requests.RequestException:
        return None


def extract_title_and_text(html_content):
    """Extracts the page title and readable text from HTML, stripping scripts/styles."""
    soup = BeautifulSoup(html_content, 'html.parser')

    for tag in soup(['script', 'style', 'noscript', 'iframe']):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else ''
    text = soup.get_text(separator=' ', strip=True)
    return title, text


def extract_links(html_content, current_url, origin_url):
    """
    Extracts all valid links from HTML, resolves them to absolute URLs,
    normalizes them, and filters to same-domain only.

    Note: In a production system, this should also parse and respect robots.txt
    directives for each domain (see recommendation.md).
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    links = set()
    base_netloc = urlparse(origin_url).netloc.lower()

    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href'].strip()

        # Skip non-navigational links
        if href.startswith('#') or href.startswith('mailto:') or href.startswith('javascript:'):
            continue
        if href.startswith('tel:') or href.startswith('data:'):
            continue

        absolute_url = urljoin(current_url, href)
        normalized = normalize_url(absolute_url)

        # Only follow same-domain links
        if urlparse(normalized).netloc == base_netloc:
            links.add(normalized)

    return list(links)