import json
import sys
from pathlib import Path

from debug_scraper import collect


def parse_args(argv):
    destinations = []
    out = Path("output") / "hotels.json"
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("--help", "-h"):
            print("Usage: python cli.py [--out file.json] <destination> [destination...]")
            print("Example: python cli.py --out output/hotels.json paris london tokyo")
            raise SystemExit(0)
        if arg == "--out":
            if index + 1 >= len(argv):
                raise SystemExit("--out needs a file path")
            out = Path(argv[index + 1])
            index += 2
            continue
        destinations.append(arg)
        index += 1
    return destinations, out


def main(argv=None):
    destinations, out = parse_args(sys.argv[1:] if argv is None else argv)
    report = collect(destinations)
    output = out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n=== production output ===")
    print("wrote", output)
    for row in report["destinations"]:
        fields = row.get("fields") or {}
        pagination = "complete" if row["paginationComplete"] else "incomplete"
        full_fields = "yes" if fields.get("fullFields") else "no"
        print(
            f"{row['query']}: {len(row['hotels'])} hotels, pages {row['pagesFetched']}, "
            f"pagination {pagination}, full fields {full_fields}"
        )
    return report


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(error)
        raise SystemExit(1) from error
