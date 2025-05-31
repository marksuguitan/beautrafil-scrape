import requests
import json
import trafilatura
from typing import Tuple, Dict, Any, List, Optional
from bs4 import BeautifulSoup
from datetime import date
import psycopg
import os
import jsonschema


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


# ---------------- Structured-content presets (one place) ----------------
_MARKDOWN_OPTS = dict(
    output_format="markdown",
    include_links=True,
    include_formatting=True,
    include_comments=False,
    favor_precision=False,
)
_HTML_OPTS = dict(
    output_format="html",
    include_links=True,
    include_formatting=True,
    include_comments=False,
    favor_precision=False,
)


# ------------------------------------------------------------------------
def extract_body_and_meta_from_html(html: str) -> Tuple[str, Dict[str, Any]]:
    """
    Returns:
        plain_text,
        combined_metadata shaped exactly like

        {
          "title": "...",
          "content": {
              "plain_text": "...",
              "structured_markdown": "...",
              "structured_html": "..."
          },
          "beautifulsoup_metadata": { ... },
          "trafilatura_metadata":   { ... }
        }
    """
    # --- BeautifulSoup meta -------------------------------------------------
    bs_meta = extract_bs_metadata(html)

    # --- Plain text (+ Trafilatura meta) ------------------------------------
    json_str = (
        trafilatura.extract(
            html,
            output_format="json",
            with_metadata=True,
            include_comments=False,
            favor_precision=False,
        )
        or "{}"
    )
    data = json.loads(json_str)
    plain_text = data.get("text", "")

    trafil_meta = {
        k: data.get(k)
        for k in ("title", "author", "date", "keywords", "description", "source")
    }

    # --- Structured versions (MD + HTML) ------------------------------------
    structured_md = trafilatura.extract(html, **_MARKDOWN_OPTS) or ""
    structured_htm = trafilatura.extract(html, **_HTML_OPTS) or ""

    combined = {
        "title": bs_meta.get("title", ""),
        "content": {
            "plain_text": plain_text,
            "structured_markdown": structured_md,
            "structured_html": structured_htm,
        },
        "beautifulsoup_metadata": bs_meta,
        "trafilatura_metadata": trafil_meta,
    }
    return plain_text, combined


def safe_extract(fn, *args, error_key=None, **kwargs):
    try:
        _plain, meta = fn(*args, **kwargs)  # meta already has the desired shape
        return True, meta
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


def clean_article_title(url_result: Dict[str, Any]) -> None:
    """
    Cleans the title fields in url_result dict if the source is PubMed.
    Modifies url_result in place.
    """
    url = None
    trafil_source = url_result.get("trafilatura_metadata", {}).get("source")
    if trafil_source:
        url = trafil_source
    if not url:
        bs_og_url = url_result.get("beautifulsoup_metadata", {}).get("og:url")
        if bs_og_url:
            url = bs_og_url
    if not url:
        for k, v in url_result.get("beautifulsoup_metadata", {}).items():
            if k.endswith("url") and isinstance(v, str) and "pubmed" in v.lower():
                url = v
                break

    def _clean(title):
        if title is None:
            return title
        if url and "pubmed" in url.lower():
            return title.removesuffix(" - PubMed")
        return title

    if url_result.get("title"):
        url_result["title"] = _clean(url_result["title"])
    if "trafilatura_metadata" in url_result and url_result["trafilatura_metadata"].get(
        "title"
    ):
        url_result["trafilatura_metadata"]["title"] = _clean(
            url_result["trafilatura_metadata"]["title"]
        )
    if "beautifulsoup_metadata" in url_result and url_result[
        "beautifulsoup_metadata"
    ].get("title"):
        url_result["beautifulsoup_metadata"]["title"] = _clean(
            url_result["beautifulsoup_metadata"]["title"]
        )


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
            # Add schema_version to each url result
            if isinstance(result, dict):
                result["schema_version"] = "1"
                result["data_source"] = "url"

            url_results.append(result)
    if url_results:
        for url_result in url_results:
            clean_article_title(url_result)
        output["urls"] = url_results

    if html_file is not None:
        success, result = safe_extract(extract_from_file, html_file, error_key="file")
        if isinstance(result, dict):
            result["schema_version"] = "1"
            result["data_source"] = "html_file"
        output["html_file"] = result

    if html_str is not None:
        success, result = safe_extract(extract_body_and_meta_from_html, html_str)
        if isinstance(result, dict):
            result["schema_version"] = "1"
            result["data_source"] = "html_str"
        output["html_str"] = result

    return output


def validate_output_schema(data: dict, schema_path: str = None):
    if schema_path is None:
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "data_structures",
            "V1__scrape_output_schema.json",
        )
        schema_path = os.path.abspath(schema_path)
    with open(schema_path, "r") as f:
        schema = json.load(f)
    jsonschema.validate(instance=data, schema=schema)


def save_scraped_data(scraped: Dict[str, Any]) -> None:
    """
    Saves the scraped data into the database.
    Uses similar functionality to db.py.
    """
    # Build DSN from environment or default values
    DB_PARAMS = {
        "host": os.getenv("PGHOST", "localhost"),
        "port": os.getenv("PGPORT", "5432"),
        "dbname": os.getenv("POSTGRES_DB", "mydb"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
    }
    DSN = " ".join(f"{k}={v}" for k, v in DB_PARAMS.items())

    # TODO: #7 Determine the the overall scraped schema
    # --- Add validation here ---
    if "urls" in scraped:
        for url_result in scraped["urls"]:
            validate_output_schema(url_result)

    if "html_file" in scraped:
        validate_output_schema(scraped["html_file"])

    if "html_str" in scraped:
        validate_output_schema(scraped["html_str"])

    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            # Use scraped data with priority: html_str > html_file > first URL result
            if "html_str" in scraped:
                record = scraped["html_str"]
            elif "html_file" in scraped:
                record = scraped["html_file"]
            elif "urls" in scraped and scraped["urls"]:
                record = scraped["urls"][0]
            else:
                record = {"title": "No Title", "content": ""}

            title = ""
            content = ""
            cur.execute(
                """
                INSERT INTO documents
                  (title, content)
                VALUES
                  (%(title)s, %(content)s)
                RETURNING id;
                """,
                {
                    "title": title,
                    "content": content,
                },
            )
            document_id = cur.fetchone()[0]
            print("▶ Created document:", document_id)

            cur.execute(
                """
                INSERT INTO raw_documents
                  (document_id, version_number, raw_data)
                VALUES
                  (%(document_id)s, %(version_number)s, %(raw_data)s);
                """,
                {
                    "document_id": document_id,
                    "version_number": 1,
                    "raw_data": json.dumps(record),
                },
            )
            print("▶ Inserted raw_documents v1 for:", document_id)


if __name__ == "__main__":
    urls_list = ["https://pubmed.ncbi.nlm.nih.gov/26460662/"]
    result = scrape_content(urls=urls_list)

    # html_file = (
    #     "Drugs used for the treatment of hypertensive emergencies - UpToDate.html"
    # )
    # result = scrape_content(
    #     urls=None,
    #     html_file=html_file,
    #     # html_str=None,  # Uncomment if you want to test with a raw HTML string
    # )
    # html_str = "..."

    # Optionally, set html_file or html_str if needed
    print(json.dumps(result, indent=2))
    save_scraped_data(result)
