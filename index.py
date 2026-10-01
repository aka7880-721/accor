from pathlib import Path

import requests

URL = "https://all.accor.com"
OUTPUT_FILE = Path("challenge_response.html")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def main():
    response = requests.get(
        URL,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=30,
    )
    print("HTTP status:", response.status_code)

    set_cookie = []
    raw_headers = getattr(response.raw, "headers", None)
    if raw_headers is not None and hasattr(raw_headers, "getlist"):
        set_cookie = raw_headers.getlist("Set-Cookie")
    if not set_cookie:
        print("set-cookie: (none)")
    else:
        print("set-cookie headers:")
        for cookie in set_cookie:
            print(cookie)

    OUTPUT_FILE.write_text(response.text, encoding="utf-8")
    print("Saved response body to", OUTPUT_FILE)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(error)
        raise SystemExit(1) from error
