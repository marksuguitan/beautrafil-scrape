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
            try:
                body, meta = extract_from_url(url)
                url_results.append(
                    {
                        "title": meta.get("title"),
                        "content": body,
                        "beautifulsoup_metadata": meta.get("beautifulsoup_metadata"),
                        "trafilatura_metadata": meta.get("trafilatura_metadata"),
                    }
                )
            except Exception as e:
                url_results.append({"url": url, "error": str(e)})
    if url_results:
        output["urls"] = url_results

    html_file_body = ""
    html_file_meta: Dict[str, Any] = {}
    if html_file is not None:
        try:
            html_file_body, html_file_meta = extract_from_file(html_file)
            output["html_file"] = {
                "title": html_file_meta.get("title"),
                "content": html_file_body,
                "beautifulsoup_metadata": html_file_meta.get("beautifulsoup_metadata"),
                "trafilatura_metadata": html_file_meta.get("trafilatura_metadata"),
            }
        except Exception as e:
            output["html_file"] = {"file": html_file, "error": str(e)}

    html_str_body = ""
    html_str_meta: Dict[str, Any] = {}
    if html_str is not None:
        try:
            html_str_body, html_str_meta = extract_body_and_meta_from_html(html_str)
            output["html_str"] = {
                "title": html_str_meta.get("title"),
                "content": html_str_body,
                "beautifulsoup_metadata": html_str_meta.get("beautifulsoup_metadata"),
                "trafilatura_metadata": html_str_meta.get("trafilatura_metadata"),
            }
        except Exception as e:
            output["html_str"] = {"error": str(e)}

    return output


if __name__ == "__main__":
    # Example usage
    urls_list = ["https://example.com/some-article"]
    raw_html = "<html><head><title>Test</title></head><body>Hello World</body></html>"

    result = scrape_content(
        urls=urls_list, html_file="build/index.html", html_str=raw_html
    )
    print(json.dumps(result, indent=2))
