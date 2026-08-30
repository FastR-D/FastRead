from __future__ import annotations

import argparse
import json

from app.db.init_db import init_db
from app.services.metadata_migration_service import MetadataMigrationService


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay versioned paper metadata normalization")
    parser.add_argument("--apply", action="store_true", help="write per-task atomic changes; default is dry-run")
    parser.add_argument("--task-id", action="append", default=[])
    args = parser.parse_args()
    init_db()
    report = MetadataMigrationService().run(
        dry_run=not args.apply,
        task_ids=set(args.task_id) if args.task_id else None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
