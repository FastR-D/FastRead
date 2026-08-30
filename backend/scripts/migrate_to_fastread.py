"""Compatibility entry point for the generic, versioned metadata migrator.

No paper IDs, titles, venues, authors, filenames, cities or registry URLs belong
here. Historical artifacts and future imports share metadata_normalization.py.
"""

from scripts.migrate_paper_metadata import main


if __name__ == "__main__":
    raise SystemExit(main())
