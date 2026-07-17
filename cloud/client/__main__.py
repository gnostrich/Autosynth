"""`python -m cloud.client train <corpus>` — the ets-cloud CLI entry point."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
