import os
import psycopg
from datetime import date
import json

# 1. Load from your environment (or hard‐code for local dev)
DB_PARAMS = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": os.getenv("PGPORT", "5432"),
    "dbname": os.getenv("POSTGRES_DB", "mydb"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
}

# 2. Build a DSN string
DSN = " ".join(f"{k}={v}" for k, v in DB_PARAMS.items())

with psycopg.connect(DSN) as conn:
    with conn.cursor() as cur:
        # Insert into documents
        cur.execute(
            """
            INSERT INTO documents
              (title, content, publication_date, extraction_source, status)
            VALUES
              (%(title)s, %(content)s, %(publication_date)s, %(extraction_source)s, %(status)s)
            RETURNING id;
            """,
            {
                "title": "My Docker-backed Doc",
                "content": "Content stored via psycopg3…",
                "publication_date": date.today(),
                "extraction_source": "docker_compose",
                "status": "new",
            },
        )
        document_id = cur.fetchone()[0]
        print("▶ Created document:", document_id)

        # Insert into raw_documents
        cur.execute(
            """
            INSERT INTO raw_documents
              (document_id, version_number, raw_data, ingested_by, format, source_reference)
            VALUES
              (%(document_id)s, %(version_number)s, %(raw_data)s, %(ingested_by)s, %(format)s, %(source_reference)s);
            """,
            {
                "document_id": document_id,
                "version_number": 1,
                "raw_data": json.dumps({"foo": "bar", "baz": 123}),
                "ingested_by": "etl_user",
                "format": "json",
                "source_reference": "docker_example_20250517",
            },
        )
        print("▶ Inserted raw_documents v1 for:", document_id)
