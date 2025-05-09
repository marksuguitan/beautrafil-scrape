#!/usr/bin/env bash
set -euo pipefail

echo "==== Combined Scraper ===="
read -er -p "Enter comma-separated URLs (leave blank to skip): " urls_input
read -er -p "Enter HTML file path (leave blank to skip): " html_file
read -er -p "Enter raw HTML string (leave blank to skip): " html_str

# Require at least one
if [[ -z "$urls_input" && -z "$html_file" && -z "$html_str" ]]; then
  echo "Error: You must provide at least one of URLs, HTML file, or HTML string." >&2
  exit 1
fi

# Build Python literals for URLs
if [[ -n "$urls_input" ]]; then
  IFS=',' read -ra _urls <<< "$urls_input"
  PY_URLS="["
  for u in "${_urls[@]}"; do
    u_trim="$(echo "$u" | xargs)"
    PY_URLS+="\"${u_trim}\", "
  done
  PY_URLS="${PY_URLS%, }]"
else
  PY_URLS="None"
fi

# File or None
if [[ -n "$html_file" ]]; then
  PY_HTML_FILE="\"${html_file}\""
else
  PY_HTML_FILE="None"
fi

# HTML string or None (wrapped in triple-quotes)
if [[ -n "$html_str" ]]; then
  PY_HTML_STR="\"\"\"${html_str}\"\"\""
else
  PY_HTML_STR="None"
fi

# Ensure output dir
mkdir -p output

# Run scraper and let Python choose filename based on title
result_file=$(python3 - <<EOF
import os, sys, json, re
# make scrapers/ importable
sys.path.insert(0, "scrapers")
from combined_scraper import scrape_content

# scrape
result = scrape_content(
    urls=$PY_URLS,
    html_file=$PY_HTML_FILE,
    html_str=$PY_HTML_STR
)

# sanitize title for filename
title = result.get("title") or ""
name = re.sub(r'[^\w\s-]', '', title).strip().lower()
name = re.sub(r'[\s]+', '_', name)
if not name:
    name = "scrape_output"

out_dir = "output"
os.makedirs(out_dir, exist_ok=True)

# ensure uniqueness
fname = f"{name}.json"
i = 1
while os.path.exists(os.path.join(out_dir, fname)):
    fname = f"{name}_{i}.json"
    i += 1

# write file
with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

# echo the filename back to shell
print(fname)
EOF
)

echo "✔ Results written to output/$result_file"