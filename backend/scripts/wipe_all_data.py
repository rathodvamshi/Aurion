"""
Wipe all stored data from MongoDB, Redis, Neo4j, and Pinecone
without removing indexes, schemas, or credentials.

Safety features:
- Default is dry-run unless --yes is provided.
- Provides per-system summaries and graceful skips when not configured.

Usage:
  python backend/scripts/wipe_all_data.py --dry-run
  python backend/scripts/wipe_all_data.py --yes

Notes:
- MongoDB: deletes all documents in each collection (preserves indexes)
- Redis: FLUSHDB on the configured DB only (preserves users/config)
- Neo4j: DETACH DELETE nodes in batches (preserves schema indexes/constraints)
- Pinecone: index.delete(delete_all=True) (preserves the index itself)
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional, Dict, Any

import logging

# Lightweight imports; we import cloud SDKs lazily
import certifi

import os as _os
import sys as _sys
from pathlib import Path as _Path

# Ensure backend package is importable when running as a script
_BACKEND_DIR = _Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in _sys.path:
    _sys.path.insert(0, str(_BACKEND_DIR))

from app.config import settings

logger = logging.getLogger("wipe_all_data")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def wipe_mongodb(dry_run: bool) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"enabled": False, "collections": [], "error": None}
    try:
        from pymongo import MongoClient
    except Exception as e:
        summary["error"] = f"pymongo not available: {e}"
        return summary

    mongo_uri = getattr(settings, "MONGO_URI", None) or getattr(settings, "DATABASE_URL", None)
    db_name = getattr(settings, "MONGO_DB", None) or getattr(settings, "MONGO_DB_NAME", None) or "assistant_db"
    if not mongo_uri:
        summary["error"] = "MongoDB not configured (MONGO_URI/DATABASE_URL missing)"
        return summary

    try:
        client = MongoClient(
            mongo_uri,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=4000,
        )
        # Force connection
        client.admin.command("ping")
        db = client[db_name]
        summary["enabled"] = True

        coll_names = [c for c in db.list_collection_names() if not c.startswith("system.")]
        logger.info(f"MongoDB db='{db_name}' collections found: {len(coll_names)}")
        for name in coll_names:
            coll = db[name]
            try:
                approx_count = coll.estimated_document_count()
            except Exception:
                approx_count = None

            if dry_run:
                logger.info(f"[MongoDB] Would delete all documents from '{name}' (approx {approx_count})")
                summary["collections"].append({"name": name, "approx_before": approx_count, "deleted": 0})
            else:
                res = coll.delete_many({})
                deleted = getattr(res, "deleted_count", None)
                logger.info(f"[MongoDB] Cleared collection '{name}' (deleted={deleted})")
                summary["collections"].append({"name": name, "approx_before": approx_count, "deleted": deleted})

        return summary
    except Exception as e:
        summary["error"] = f"Mongo wipe failed: {e}"
        return summary


def wipe_redis(dry_run: bool) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"enabled": False, "dbsize_before": None, "flushed": False, "error": None}
    try:
        import redis as redis_sync
    except Exception as e:
        summary["error"] = f"redis-py not available: {e}"
        return summary

    try:
        client: Optional[Any] = None
        if getattr(settings, "REDIS_URL", None):
            client = redis_sync.from_url(settings.REDIS_URL, decode_responses=True)
        else:
            client = redis_sync.Redis(
                host=getattr(settings, "REDIS_HOST", "localhost"),
                port=int(getattr(settings, "REDIS_PORT", 6379)),
                db=int(getattr(settings, "REDIS_DB", 0)),
                password=getattr(settings, "REDIS_PASSWORD", None) or None,
                ssl=True if getattr(settings, "REDIS_TLS", False) else False,
                decode_responses=True,
            )

        # Test connection
        client.ping()
        summary["enabled"] = True
        size = client.dbsize()
        summary["dbsize_before"] = size
        if dry_run:
            logger.info(f"[Redis] Would FLUSHDB on DB={getattr(settings, 'REDIS_DB', 0)} (keys={size})")
        else:
            client.flushdb()
            summary["flushed"] = True
            logger.info("[Redis] FLUSHDB completed")
        return summary
    except Exception as e:
        summary["error"] = f"Redis wipe failed: {e}"
        return summary


def wipe_neo4j(dry_run: bool, batch: int = 10000, timeout: int = 30) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"enabled": False, "nodes_before": None, "nodes_deleted": 0, "error": None}
    try:
        from neo4j import GraphDatabase
    except Exception as e:
        summary["error"] = f"neo4j driver not available: {e}"
        return summary

    uri = getattr(settings, "NEO4J_URI", None)
    user = getattr(settings, "NEO4J_USER", None)
    pwd = getattr(settings, "NEO4J_PASSWORD", None)
    database = getattr(settings, "NEO4J_DATABASE", None) or None
    if not (uri and user and pwd):
        summary["error"] = "Neo4j not fully configured (NEO4J_URI/USER/PASSWORD)"
        return summary

    try:
        driver = GraphDatabase.driver(uri, auth=(user, pwd))
        with driver.session(database=database) as session:
            # Count nodes
            try:
                c = session.run("MATCH (n) RETURN count(n) as c").single()["c"]
            except Exception:
                c = None
            summary["nodes_before"] = c
            summary["enabled"] = True

            if dry_run:
                logger.info(f"[Neo4j] Would detach-delete all nodes (current count={c})")
                return summary

            total_deleted = 0
            start = time.time()
            while True:
                # Delete in batches; use result summary counters
                result = session.run(
                    "MATCH (n) WITH n LIMIT $batch DETACH DELETE n RETURN 0 as noop",
                    {"batch": batch},
                )
                summary_result = result.consume()
                deleted = 0
                try:
                    deleted = summary_result.counters.nodes_deleted
                except Exception:
                    deleted = 0
                total_deleted += int(deleted or 0)
                if deleted == 0:
                    break
                if time.time() - start > timeout * 10:  # generous upper bound
                    logger.warning("[Neo4j] Deletion taking long; continuing best-effort")
                    break
            summary["nodes_deleted"] = total_deleted
            logger.info(f"[Neo4j] Deleted nodes total={total_deleted}")
        driver.close()
        return summary
    except Exception as e:
        summary["error"] = f"Neo4j wipe failed: {e}"
        return summary


def wipe_pinecone(dry_run: bool) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"enabled": False, "index": None, "vectors_before": None, "namespaces": [], "deleted_all": False, "error": None, "note": None}
    api_key = getattr(settings, "PINECONE_API_KEY", None)
    index_name = getattr(settings, "PINECONE_INDEX", None) or "aurion"
    if not api_key:
        summary["error"] = "Pinecone API key not configured"
        return summary

    try:
        from pinecone import Pinecone
    except Exception as e:
        summary["error"] = f"pinecone client not available: {e}"
        return summary

    try:
        pc = Pinecone(api_key=api_key)
        idx = pc.Index(index_name)
        summary["enabled"] = True
        summary["index"] = index_name
        namespaces = []
        try:
            stats = idx.describe_index_stats()
            total = None
            if isinstance(stats, dict):
                total = stats.get("total_vector_count") or stats.get("vectors_count")
                ns_map = stats.get("namespaces") or {}
                if isinstance(ns_map, dict):
                    namespaces = list(ns_map.keys())
            summary["vectors_before"] = total
            summary["namespaces"] = namespaces
        except Exception:
            pass

        if dry_run:
            if namespaces:
                for ns in namespaces:
                    logger.info(f"[Pinecone] Would delete all vectors in namespace='{ns}' of index='{index_name}'")
            else:
                logger.info(f"[Pinecone] Would delete all vectors from index='{index_name}' (count≈{summary['vectors_before']})")
            return summary

        # Perform deletion
        try:
            if namespaces:
                for ns in namespaces:
                    idx.delete(delete_all=True, namespace=ns)
                summary["deleted_all"] = True
                logger.info(f"[Pinecone] delete_all completed for {len(namespaces)} namespaces in index='{index_name}'")
            else:
                # No namespaces reported; attempt whole-index delete_all
                idx.delete(delete_all=True)
                summary["deleted_all"] = True
                logger.info(f"[Pinecone] delete_all completed for index='{index_name}' (no namespaces listed)")
            return summary
        except Exception as e:
            msg = str(e)
            # Treat namespace-not-found as no-op
            if "Namespace not found" in msg:
                summary["note"] = "Namespace not found; nothing to delete"
                summary["deleted_all"] = True
                logger.info(f"[Pinecone] No namespaces found to delete for index='{index_name}'")
                return summary
            raise
    except Exception as e:
        summary["error"] = f"Pinecone wipe failed: {e}"
        return summary


def main():
    parser = argparse.ArgumentParser(description="Wipe data from MongoDB, Redis, Neo4j, and Pinecone (preserve indexes & credentials)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without making changes")
    parser.add_argument("--yes", action="store_true", help="Proceed with deletion without prompting")
    parser.add_argument("--only", choices=["mongo", "redis", "neo4j", "pinecone"], help="Limit wipe to a single system", default=None)
    args = parser.parse_args()

    dry_run = args.dry_run or (not args.yes)
    if dry_run and args.yes:
        logger.warning("Both --dry-run and --yes provided; proceeding in dry-run mode.")

    if not dry_run and not args.yes:
        logger.error("Destructive operation requires --yes. Use --dry-run to preview.")
        sys.exit(2)

    logger.info("Starting data wipe" + (" (dry-run)" if dry_run else ""))

    overall: Dict[str, Any] = {}

    def maybe(name: str) -> bool:
        return (args.only is None) or (args.only == name)

    # MongoDB
    if maybe("mongo"):
        overall["mongodb"] = wipe_mongodb(dry_run)
    # Redis
    if maybe("redis"):
        overall["redis"] = wipe_redis(dry_run)
    # Neo4j
    if maybe("neo4j"):
        overall["neo4j"] = wipe_neo4j(dry_run)
    # Pinecone
    if maybe("pinecone"):
        overall["pinecone"] = wipe_pinecone(dry_run)

    # Summarize
    logger.info("\n===== Wipe Summary " + ("(dry-run)" if dry_run else "") + " =====")
    for k, v in overall.items():
        status = "OK" if v.get("enabled") and not v.get("error") else ("SKIPPED" if not v.get("enabled") else "ERROR")
        logger.info(f"{k.upper():8s}: {status} - {v}")

    if any(v.get("error") for v in overall.values()):
        sys.exit(1 if not dry_run else 0)

    logger.info("All done.")


if __name__ == "__main__":
    main()
