"""KB ingest — load data/tenants/<slug>/kb/*.txt → kb_chunks FTS5 (D-07).

Reads per-tenant knowledge-base text files, splits them into chunks, and bulk-inserts
into the kb_chunks FTS5 virtual table.  Idempotent: existing chunks for the tenant are
deleted before re-inserting so re-running after content updates does not duplicate rows.

Run standalone to (re-)ingest a tenant's KB:
    python -m src.kb.ingest --tenant=demo

Security (T-01-SQLI): all SQL uses parameterized queries — tenant_id is bound via ?
and never f-string/formatted into SQL.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import aiosqlite

# Maximum characters per chunk when splitting on size.  Paragraphs shorter than
# this are kept intact; larger paragraphs are split at chunk_size boundaries.
_DEFAULT_CHUNK_SIZE = 300


def _split_into_chunks(text: str, chunk_size: int = _DEFAULT_CHUNK_SIZE) -> list[str]:
    """Split text into chunks for FTS5 indexing.

    Strategy (two-pass):
    1. Split on blank lines to preserve natural paragraph boundaries.
    2. For any paragraph longer than chunk_size, further split into consecutive
       character windows of chunk_size (no word-boundary required — good enough for
       FTS5 retrieval which matches at the token level).

    Empty paragraphs (whitespace only) are discarded.
    """
    paragraphs = [p.strip() for p in text.split("\n\n")]
    chunks: list[str] = []
    for para in paragraphs:
        if not para:
            continue
        if len(para) <= chunk_size:
            chunks.append(para)
        else:
            # Split long paragraph into consecutive windows
            for i in range(0, len(para), chunk_size):
                piece = para[i : i + chunk_size].strip()
                if piece:
                    chunks.append(piece)
    return chunks


async def ingest_kb_files(
    db_path: str,
    tenant_id: str,
    kb_dir: str,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
) -> int:
    """Read *.txt files from kb_dir, split into chunks, insert into kb_chunks.

    Idempotent: deletes ALL existing chunks for tenant_id before inserting the
    current files.  Also updates kb_documents with an ingested_at timestamp.

    Returns the total number of chunks inserted.

    Security (T-01-SQLI): tenant_id and all values are bound via ? — never
    interpolated into SQL strings.
    """
    kb_path = Path(kb_dir)
    if not kb_path.is_dir():
        raise FileNotFoundError(f"KB directory not found: {kb_dir}")

    # Collect all chunks from *.txt files
    file_chunks: list[tuple[str, str, str, str]] = []  # (tenant_id, doc_id, chunk_id, content)
    for fname in sorted(os.listdir(kb_dir)):
        if not fname.endswith(".txt"):
            continue
        fpath = kb_path / fname
        text = fpath.read_text(encoding="utf-8")
        for i, chunk in enumerate(_split_into_chunks(text, chunk_size)):
            file_chunks.append((tenant_id, fname, str(i), chunk))

    async with aiosqlite.connect(db_path) as db:
        # Idempotency: delete existing chunks for this tenant (FTS5 has no UNIQUE)
        await db.execute(
            "DELETE FROM kb_chunks WHERE tenant_id = ?",
            (tenant_id,),
        )
        # Delete existing kb_documents records for this tenant
        await db.execute(
            "DELETE FROM kb_documents WHERE tenant_id = ?",
            (tenant_id,),
        )

        # Insert all chunks in one executemany (bulk — matches seed_demo.py pattern)
        await db.executemany(
            "INSERT INTO kb_chunks(tenant_id, doc_id, chunk_id, content) VALUES (?,?,?,?)",
            file_chunks,
        )

        # Record each ingested file in kb_documents
        # Use a set to avoid duplicate filenames in the metadata table
        ingested_files: set[str] = {row[1] for row in file_chunks}
        await db.executemany(
            "INSERT INTO kb_documents(tenant_id, filename) VALUES (?,?)",
            [(tenant_id, fname) for fname in sorted(ingested_files)],
        )

        await db.commit()

    return len(file_chunks)


async def _main() -> None:
    """CLI entry point: python -m src.kb.ingest --tenant=<slug>"""
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Ingest per-tenant KB text files into kb_chunks FTS5 table."
    )
    parser.add_argument(
        "--tenant",
        required=True,
        help="Tenant slug (e.g. demo).  Resolves kb_ref from the tenants table.",
    )
    parser.add_argument(
        "--db",
        default="centralino.db",
        help="Path to the SQLite database (default: centralino.db).",
    )
    args = parser.parse_args()

    # Resolve kb_ref from TenantRepository
    from src.config.repository import TenantRepository

    repo = TenantRepository(db_path=args.db)
    await repo.init_db()

    tenant = await repo.get_tenant(args.tenant)
    if not tenant.kb_ref:
        print(f"Tenant '{args.tenant}' has no kb_ref configured — nothing to ingest.")
        return

    count = await ingest_kb_files(
        db_path=args.db,
        tenant_id=tenant.id,
        kb_dir=tenant.kb_ref,
    )
    print(f"Ingested {count} chunk(s) for tenant '{tenant.id}' from '{tenant.kb_ref}'.")


if __name__ == "__main__":
    asyncio.run(_main())
