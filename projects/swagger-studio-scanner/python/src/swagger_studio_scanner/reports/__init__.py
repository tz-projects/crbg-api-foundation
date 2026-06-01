"""Report writers — JSON (machine), CSV (finding-level), HTML (leadership).

Each writer is a single pure function: takes the scan results + a target
directory, writes its file, returns the path. The CLI fans these out in
parallel-ish order; nothing here depends on async or the network.
"""

from swagger_studio_scanner.reports.csv_writer import write_csv
from swagger_studio_scanner.reports.html_writer import write_html
from swagger_studio_scanner.reports.json_writer import write_json

__all__ = ["write_csv", "write_html", "write_json"]
