import requests
import json
from trafilatura import fetch_url, extract

#  Use beautifulsoup4 for more complete handling of metadata
## <meta name="…" content="…"> and <meta property="…" content="…">
## for tag in soup.find_all('meta'):
##     if tag.get('name'):
##         meta[tag['name']] = tag.get('content', '').strip()
##     elif tag.get('property'):
##         meta[tag['property']] = tag.get('content', '').strip()

urls = [
    "https://example.com/some-article",
    "https://www.nejm.org/doi/full/10.1056/NEJMoa2415820",
    "https://pubmed.ncbi.nlm.nih.gov/40337982/",
    # ... list of URLs to scrape
]

results = []
for url in urls:
    # Fetch the URL content (Trafilatura has fetch_url, or use requests)
    downloaded = fetch_url(url)  # this does an HTTP get with proper headers
    # Alternatively: downloaded = requests.get(url, timeout=10).text

    if not downloaded:
        continue  # skip if failed to fetch

    # Extract main content & metadata
    result = extract(downloaded, url=url, output_format="json", with_metadata=True)
    if result:
        data = json.loads(result)
    else:
        data = {}

    # Collect relevant fields
    results.append(
        {
            "url": url,
            "title": data.get("title"),
            "author": data.get("author"),
            "date": data.get("date"),
            "text": data.get("text"),
            # "images": data.get("images"),    # if include_images was True in extract()
            # "links": data.get("links"),      # if include_links was True
        }
    )

# Now 'results' is a list of dicts with the extracted info.
# You can print them or save to a file/DB as needed.
print(json.dumps(results, indent=2))
