"""Copy-only migration from an explicitly named legacy snapshot into a new Web DB.

Final cutover requires a quiescent backup. Source is never opened writable.
Unconverted domains remain archived and are enumerated, never silently dropped.
"""
from __future__ import annotations
import argparse
import json
import shutil
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse
from .store import Store, encode, uid


def inventory(source):
    source = Path(source).resolve()
    db_path = source / "fastread.db"
    tables = {}
    if db_path.is_file():
        with sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True) as db:
            names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for name in names:
                tables[name] = db.execute('SELECT count(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
    results = [p for p in (source / "paper_results").glob("*.json") if not p.name.endswith(".status.json")]
    return {"source": str(source), "tables": tables, "paper_results": len(results),
            "status_files": len(list((source / "paper_results").glob("*.status.json"))),
            "pdf_files": len(list((source / "uploads").glob("*.pdf"))),
            "browser_chat": "browser export required; not assumed present on server"}


def migrate(source, store, workspace):
    source = Path(source).resolve()
    if source == store.root or source in store.root.parents or store.root in source.parents:
        raise ValueError("Source and destination must be separate trees")
    if not store.one("SELECT id FROM workspaces WHERE id=?", (workspace,)):
        raise ValueError("workspace_not_found")
    report = inventory(source) | {"migrated": [], "already_migrated": [], "failed": []}
    rows = {}
    if (source / "fastread.db").is_file():
        with sqlite3.connect((source / "fastread.db").as_uri() + "?mode=ro", uri=True) as legacy:
            legacy.row_factory = sqlite3.Row
            if "paper_tasks" in report["tables"]:
                rows = {row["task_id"]: dict(row) for row in legacy.execute("SELECT * FROM paper_tasks")}
    for path in sorted((source / "paper_results").glob("*.json")):
        if path.name.endswith(".status.json"):
            continue
        source_key = str(source) + ":" + workspace + ":" + path.stem
        if store.one("SELECT source FROM migration_records WHERE source=?", (source_key,)):
            if "paper_tasks" in report["tables"] and path.stem not in rows:
                with store.connect(write=True) as db:
                    db.execute("UPDATE papers SET archived=1 WHERE id=(SELECT paper_id FROM migration_records WHERE source=?)", (source_key,))
            report["already_migrated"].append(path.stem)
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            document = dict(payload.get("paper_document") or {})
            legacy_row = rows.get(path.stem, {})
            document["legacy_collection"] = {key: legacy_row.get(key) for key in ("collection_folder", "collection_tags_json", "collection_note")}
            original_file = None
            for value in (document.get("filename"), document.get("pdf_url"), legacy_row.get("upload_filename")):
                if not value:
                    continue
                name = Path(urlparse(str(value)).path).name
                candidate = (source / "uploads" / name).resolve()
                if candidate.parent == (source / "uploads").resolve() and candidate.is_file():
                    original_file = candidate
                    break
            relative = None
            if original_file:
                relative = "files/" + uid() + ".pdf"
                shutil.copy2(original_file, store.root / relative)
            with store.connect(write=True) as db:
                imported = store.ingest(workspace, document, file_path=relative, source_key=source_key, db=db)
                if "paper_tasks" in report["tables"] and path.stem not in rows:
                    db.execute("UPDATE papers SET archived=1 WHERE id=?", (imported["paper_id"],))
                insights = payload.get("insights") or {}
                reading_report = insights.get("reading_report")
                if reading_report:
                    reading_report["document_version_id"] = imported["version_id"]
                    reading_report["claim_support_validation"] = "not_independently_verified"
                    db.execute("INSERT INTO report_versions VALUES(?,?,?,?,?,?)", (uid(), imported["paper_id"], imported["version_id"], None, encode(reading_report), time.time()))
                summary = insights.get("personal_summary") or {}
                text = summary.get("content", "") if isinstance(summary, dict) else str(summary)
                if text:
                    db.execute("UPDATE papers SET summary=? WHERE id=?", (text, imported["paper_id"]))
            report["migrated"].append({"legacy_id": path.stem, **imported, "original_pdf": bool(relative)})
        except Exception as exc:
            report["failed"].append({"legacy_id": path.stem, "error_type": type(exc).__name__})
    report["archived_domains"] = {name: count for name, count in report["tables"].items() if name not in {"paper_tasks", "providers", "models"} and count}
    if (source / "fastread.db").is_file():
        with sqlite3.connect((source / "fastread.db").as_uri() + "?mode=ro", uri=True) as legacy, store.connect(write=True) as db:
            legacy.row_factory = sqlite3.Row
            for table in report["archived_domains"]:
                for index, row in enumerate(legacy.execute('SELECT * FROM "' + table.replace('"','""') + '"')):
                    record = dict(row)
                    db.execute("INSERT OR IGNORE INTO legacy_archive VALUES(?,?,?,?,?)", (workspace,str(source),table,str(record.get("id", index)),encode(record)))
            topic_ids = {}
            import uuid
            for row in legacy.execute("SELECT * FROM research_topics") if "research_topics" in report["tables"] else []:
                topic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(source) + workspace + row["id"]))
                topic_ids[row["id"]] = topic_id
                db.execute("INSERT OR IGNORE INTO topics VALUES(?,?,?,?,?,?)", (topic_id,workspace,row["question"],row["scope_statement"],row["user_hypotheses_json"],time.time()))
            import re
            for row in legacy.execute("SELECT * FROM topic_evidence_items") if "topic_evidence_items" in report["tables"] else []:
                topic_id = topic_ids.get(row["topic_id"])
                if not topic_id:
                    continue
                mapping = db.execute("SELECT * FROM migration_records WHERE source=?", (str(source)+":"+workspace+":"+row["task_id"],)).fetchone()
                page = db.execute("SELECT text FROM pages WHERE version_id=? AND number=?", (mapping["version_id"],row["page"])).fetchone() if mapping else None
                quote = re.sub(r"\s+", " ", row["exact_quote"]).casefold()
                located = bool(page and quote and quote in re.sub(r"\s+", " ",page["text"]).casefold())
                evidence_id = str(uuid.uuid5(uuid.NAMESPACE_URL,str(source)+workspace+row["id"]))
                db.execute("INSERT OR IGNORE INTO topic_evidence VALUES(?,?,?,?,?,?,?,?,?)", (evidence_id,topic_id,mapping["paper_id"] if mapping else None,mapping["version_id"] if mapping else None,row["page"],row["exact_quote"],row["user_note"],row["role"],"located" if located else "unresolved"))
    report["topics_migrated"] = store.one("SELECT count(*) n FROM topics WHERE workspace_id=?", (workspace,))["n"]
    report["topic_evidence_migrated"] = store.one("SELECT count(*) n FROM topic_evidence e JOIN topics t ON t.id=e.topic_id WHERE t.workspace_id=?", (workspace,))["n"]
    report["orphan_result_ids"] = [p.stem for p in (source/"paper_results").glob("*.json") if not p.name.endswith(".status.json") and "paper_tasks" in report["tables"] and p.stem not in rows]
    report["orphan_policy"] = "archived for review; never silently resurrected in the active library"
    report["cutover_ready"] = not report["failed"]
    report["provider_keys"] = "not automatically assigned; administrator must assign providers to a workspace"
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--root")
    parser.add_argument("--workspace")
    parser.add_argument("--inventory", action="store_true")
    args = parser.parse_args()
    if args.inventory:
        output = inventory(args.source)
    else:
        if not args.workspace:
            parser.error("--workspace is required for migration")
        destination = Store(args.root)
        destination.initialize()
        output = migrate(args.source, destination, args.workspace)
    print(json.dumps(output, ensure_ascii=False, indent=2))
