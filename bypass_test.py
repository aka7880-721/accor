"""Test the Imperva bypass against the Accor catalog API."""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

from imperva_bypass import ensure_bypass, solve_inline_challenge

API_URL = "https://api.accor.com/catalog/v1/hotels?q=paris"
CHALLENGE_FILE = Path("challenge.html")
TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def default_headers():
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/html, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://all.accor.com/",
    }


def extract_hotels(body):
    try:
        data = json.loads(body)
    except ValueError:
        return []

    if not isinstance(data, dict):
        return []

    rows = data.get("hotels")
    if not isinstance(rows, list):
        rows = data.get("results") or []

    hotels = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        hotel_id = str(row.get("id") or row.get("hotelId") or row.get("code") or "").strip()
        name = str(row.get("name") or row.get("hotelName") or "").strip()
        if hotel_id or name:
            hotels.append({"id": hotel_id, "name": name})
    return hotels


def request_catalog(session):
    return session.get(API_URL, headers=default_headers(), timeout=TIMEOUT)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Test Imperva bypass on the Accor catalog API.")
    parser.add_argument(
        "--challenge-file",
        type=Path,
        metavar="FILE",
        help="Use a saved challenge HTML file to run solve-and-retry without a live 403",
    )
    return parser.parse_args(argv)


def print_result(response):
    hotels = extract_hotels(response.text)
    print("\n=== result ===")
    print("final status:", response.status_code)
    if hotels:
        print("first 3 hotels:")
        for index, hotel in enumerate(hotels[:3], start=1):
            print(f"{index}. {hotel['id']} {hotel['name']}")
    else:
        print("hotels: (none in response)")
        preview = response.text[:300].replace("\n", " ")
        print("response preview:", preview)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)

    session = requests.Session()
    print("=== imperva bypass ===")
    bypass = ensure_bypass(session, refresh=True)
    print(json.dumps(bypass.summary(), indent=2))

    print("\n=== initial request ===")
    print("GET", API_URL)
    response = request_catalog(session)
    print("status:", response.status_code)

    if args.challenge_file:
        challenge_path = args.challenge_file.resolve()
        if not challenge_path.is_file():
            raise FileNotFoundError(f"Challenge file not found: {challenge_path}")
        print("using challenge file:", challenge_path)
        challenge_html = challenge_path.read_text(encoding="utf-8")
        solved = solve_inline_challenge(session, challenge_html, referer="https://all.accor.com/")
        print("inline challenge cookies:", sorted(solved.keys()))
        response = request_catalog(session)
    elif response.status_code == 403:
        CHALLENGE_FILE.write_text(response.text, encoding="utf-8")
        print("saved challenge HTML to", CHALLENGE_FILE)
        solved = solve_inline_challenge(session, response.text, referer="https://all.accor.com/")
        print("inline challenge cookies:", sorted(solved.keys()))
        response = request_catalog(session)
    else:
        print("no WAF challenge detected (expected 403, or pass --challenge-file)")

    hostname = urlparse(API_URL).hostname or ""
    cookie_names = sorted({cookie.name for cookie in session.cookies if hostname.endswith((cookie.domain or hostname).lstrip("."))})
    print("session cookies:", cookie_names)
    print("reese84:", "reese84" in cookie_names)
    print("___utmvc:", "___utmvc" in cookie_names)
    print_result(response)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
