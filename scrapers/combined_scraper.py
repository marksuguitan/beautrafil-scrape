import requests
import json
import trafilatura
from typing import Tuple, Dict, Any, List, Optional
from bs4 import BeautifulSoup


# TODO: Handle 403s
# see: https://github.com/marksuguitan/beautrafil-scrape/issues/1
def extract_bs_metadata(html: str) -> Dict[str, Any]:
    """
    Parses HTML with BeautifulSoup and returns a dict of all meta tags.
    Keys are meta[@name] or meta[@property], values are their content.
    Also captures <title> if present.
    """
    soup = BeautifulSoup(html, "lxml")
    bs_meta: Dict[str, Any] = {}

    for tag in soup.find_all("meta"):
        if tag.get("name"):
            bs_meta[tag["name"]] = tag.get("content", "").strip()
        elif tag.get("property"):
            bs_meta[tag["property"]] = tag.get("content", "").strip()

    if soup.title and soup.title.string:
        bs_meta.setdefault("title", soup.title.string.strip())

    return bs_meta


def extract_body_and_meta_from_html(html: str) -> Tuple[str, Dict[str, Any]]:
    """
    1) Runs Trafilatura on the raw HTML to get body text + its metadata.
    2) Runs BeautifulSoup on the raw HTML to get all <meta> tags.
    3) Combines both into a single metadata dict:
       {
         title: ...,
         beautifulsoup_metadata: {...},
         trafilatura_metadata: {...}
       }
    Returns: (body_text, combined_metadata)
    """
    bs_meta = extract_bs_metadata(html)

    result_json = trafilatura.extract(
        html,
        output_format="json",
        with_metadata=True,
        include_comments=False,
        favor_precision=False,
    )
    if not result_json:
        return "", {
            "title": bs_meta.get("title", ""),
            "beautifulsoup_metadata": bs_meta,
            "trafilatura_metadata": {},
        }

    data = json.loads(result_json)
    body_text = data.get("text", "")

    trafil_meta = {
        k: data.get(k)
        for k in ("title", "author", "date", "keywords", "description", "source")
    }

    title = bs_meta.get("title", "")
    combined_meta = {
        "title": title,
        "beautifulsoup_metadata": bs_meta,
        "trafilatura_metadata": trafil_meta,
    }

    return body_text, combined_meta


def safe_extract(fn, *args, error_key=None):
    """
    Helper to run an extraction function and catch exceptions.
    Returns (success, result_dict)
    """
    try:
        body, meta = fn(*args)
        return True, {
            "title": meta.get("title"),
            "content": body,
            "beautifulsoup_metadata": meta.get("beautifulsoup_metadata"),
            "trafilatura_metadata": meta.get("trafilatura_metadata"),
        }
    except requests.exceptions.HTTPError as e:
        # TODO: Handle HTTP errors: https://github.com/marksuguitan/beautrafil-scrape/issues/2

        err = {error_key or "error": f"HTTP error: {e.response.status_code}"}

        print(
            {
                "status_code": e.response.status_code,
                "url": args[0],
                "error": str(e),
                error_key or "error": f"HTTP error: {e.response.status_code}",
            }
        )

        if error_key == "url":
            err["url"] = args[0]
        elif error_key == "file":
            err["file"] = args[0]
        return False, err
    except Exception as e:
        print(f"Error: {e}")
        err = {error_key or "error": str(e)}
        if error_key == "url":
            err["url"] = args[0]
        elif error_key == "file":
            err["file"] = args[0]
        return False, err


def extract_from_url(url: str) -> Tuple[str, Dict[str, Any]]:
    """
    Fetches HTML via requests, then runs combined extraction.
    """
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return extract_body_and_meta_from_html(resp.text)


def extract_from_file(path: str) -> Tuple[str, Dict[str, Any]]:
    """
    Reads an .html file from disk and runs combined extraction.
    """
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    return extract_body_and_meta_from_html(html)


def scrape_content(
    urls: Optional[List[str]] = None,
    html_file: Optional[str] = None,
    html_str: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Scrapes multiple sources using Trafilatura + BeautifulSoup metadata.

    Returns a dict with:
      - title: top-level title (prefers html_str > html_file > first URL)
      - content: top-level body text
      - urls: list of metadata dicts for each URL
      - html_file: metadata dict for local HTML file
      - html_str: metadata dict for raw HTML string
    """
    output: Dict[str, Any] = {}

    url_results: List[Dict[str, Any]] = []
    if urls is not None:
        for url in urls:
            _, result = safe_extract(extract_from_url, url, error_key="url")
            url_results.append(result)
    if url_results:
        output["urls"] = url_results

    if html_file is not None:
        success, result = safe_extract(extract_from_file, html_file, error_key="file")
        output["html_file"] = result

    if html_str is not None:
        success, result = safe_extract(extract_body_and_meta_from_html, html_str)
        output["html_str"] = result

    return output


if __name__ == "__main__":
    # Example usage
    urls_list = ["https://example.com/some-article"]
    raw_html = "<html><head><title>Test</title></head><body>Hello World</body></html>"

    result = scrape_content(
        urls=urls_list, html_file="build/index.html", html_str=raw_html
    )
    print(json.dumps(result, indent=2))
