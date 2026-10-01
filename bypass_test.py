"""Test js_runner.py against the Accor WAF challenge on the catalog API."""

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

from js_runner import run_sandboxed_script

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


def parse_cookie_string(raw):
    cookies = {}
    if not raw:
        return cookies
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        if name:
            cookies[name] = value.strip()
    return cookies


def copy_session_cookies(source_session, target_session, url):
    hostname = urlparse(url).hostname or ""
    for cookie in source_session.cookies:
        domain = (cookie.domain or hostname).lstrip(".")
        if domain and hostname and not hostname.endswith(domain):
            continue
        target_session.cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)


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


def main():
    session = requests.Session()
    print("=== initial request ===")
    print("GET", API_URL)
    response = request_catalog(session)
    print("status:", response.status_code)

    solved_cookies = {}
    if response.status_code == 403:
        CHALLENGE_FILE.write_text(response.text, encoding="utf-8")
        print("saved challenge HTML to", CHALLENGE_FILE)

        print("\n=== solving challenge ===")
        cookie_string = run_sandboxed_script(CHALLENGE_FILE.read_text(encoding="utf-8"))
        print("document.cookie:", cookie_string or "(empty)")
        solved_cookies = parse_cookie_string(cookie_string)
        reese84 = solved_cookies.get("reese84")
        if reese84:
            print("reese84 extracted:", reese84[:80] + ("..." if len(reese84) > 80 else ""))
        else:
            print("reese84 not found in solved cookie string")

        print("\n=== retry with cookies ===")
        retry_session = requests.Session()
        copy_session_cookies(session, retry_session, API_URL)
        for name, value in solved_cookies.items():
            retry_session.cookies.set(name, value, domain=".accor.com", path="/")
        response = request_catalog(retry_session)
        print("status:", response.status_code)
    else:
        print("no WAF challenge detected (expected 403 to test bypass)")

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


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error
