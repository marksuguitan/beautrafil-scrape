# Hyperscrape

## Data Structures

The data output from the `combined_scraper.py` is seen in the `/data_structures` directory. These `V1__scrape_output_schema.json` files are versioned incrementally.

The schema being used to validate the output of the scraper function is referenced in the `validate_output_schema` function in the `combined_scraper.py` file:

```python
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
```
