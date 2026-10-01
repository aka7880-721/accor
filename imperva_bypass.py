"""
Pure HTTP Imperva bypass for all.accor.com.

Accor currently ships the UTMVC sensor (`/_Incapsula_Resource?SWJIYLWA=...`).
Running that obfuscated script in Node (not Playwright/Selenium) produces the
`___utmvc` cookie. Some Imperva deployments also POST a reese84 sensor payload;
when that POST is emitted we replay it and store the returned `reese84` token.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_ENTRY_URL = "https://all.accor.com"
TIMEOUT = 30
ROOT = Path(__file__).resolve().parent
SENSOR_RUNTIME = ROOT / "sensor_runtime.js"

IMPERVA_COOKIE_NAMES = ("reese84", "___utmvc", "_integrity_")
UTMVC_SENSOR_MARKER = "SWJIYLWA"
REESE_SENSOR_MARKERS = ("reese84", "?d=", "vice-")


@dataclass
class CapturedRequest:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    via: str = ""


@dataclass
class BypassResult:
    entry_url: str
    sensor_url: str | None = None
    cookies: dict[str, str] = field(default_factory=dict)
    posts: list[CapturedRequest] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    reese84: bool = False
    utmvc: bool = False
    bypass_ok: bool = False

    def summary(self) -> dict[str, Any]:
        return {
            "entryUrl": self.entry_url,
            "sensorUrl": self.sensor_url,
            "reese84": self.reese84,
            "utmvc": self.utmvc,
            "bypassOk": self.bypass_ok,
            "cookies": sorted(self.cookies.keys()),
            "postsCaptured": len(self.posts),
            "errors": self.errors,
        }


def default_headers(*, referer: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def extract_incapsula_scripts(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for tag in soup.find_all("script", src=True):
        src = tag.get("src") or ""
        if "_Incapsula_Resource" in src or "SWJIYLWA" in src or "SWKMTFSR" in src:
            urls.append(urljoin(base_url, src))
    if urls:
        return list(dict.fromkeys(urls))

    for match in re.finditer(r'/_Incapsula_Resource[^"\']+', html):
        urls.append(urljoin(base_url, match.group(0)))
    return list(dict.fromkeys(urls))


def pick_sensor_url(script_urls: list[str]) -> str | None:
    if not script_urls:
        return None
    for url in script_urls:
        if UTMVC_SENSOR_MARKER in url:
            return url
    for url in script_urls:
        if any(marker in url for marker in REESE_SENSOR_MARKERS):
            return url
    return script_urls[0]


def run_sensor_in_node(sensor_source: str, *, max_ticks: int = 200) -> dict[str, Any]:
    if not SENSOR_RUNTIME.is_file():
        raise FileNotFoundError(f"Missing Node runtime: {SENSOR_RUNTIME}")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as handle:
        handle.write(sensor_source)
        sensor_path = handle.name

    try:
        completed = subprocess.run(
            ["node", str(SENSOR_RUNTIME), sensor_path, str(max_ticks)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    finally:
        Path(sensor_path).unlink(missing_ok=True)

    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "sensor runtime failed"
        raise RuntimeError(message)

    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError("sensor runtime returned no output")
    return json.loads(stdout)


def apply_cookies(session: requests.Session, cookies: dict[str, str], *, domain: str = ".accor.com") -> None:
    for name, value in cookies.items():
        if not name or value is None:
            continue
        session.cookies.set(name, value, domain=domain, path="/")


def replay_runtime_requests(
    session: requests.Session,
    posts: list[dict[str, Any]],
    *,
    referer: str,
    base_url: str,
) -> list[CapturedRequest]:
    replayed: list[CapturedRequest] = []
    for raw in posts:
        method = str(raw.get("method") or "GET").upper()
        url = str(raw.get("url") or "")
        if url.startswith("/"):
            url = urljoin(base_url, url)
        headers = dict(raw.get("headers") or {})
        headers.setdefault("User-Agent", USER_AGENT)
        headers.setdefault("Referer", referer)
        body = raw.get("body")
        request = CapturedRequest(
            method=method,
            url=url,
            headers=headers,
            body="" if body is None else str(body),
            via=str(raw.get("via") or ""),
        )
        replayed.append(request)
        session.request(method, url, headers=headers, data=request.body or None, timeout=TIMEOUT)
    return replayed


def submit_reese_payload(
    session: requests.Session,
    post: CapturedRequest,
    *,
    referer: str,
) -> str | None:
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": post.headers.get("Content-Type", "text/plain; charset=UTF-8"),
    }
    response = session.post(
        post.url,
        headers=headers,
        data=post.body.encode("utf-8"),
        timeout=TIMEOUT,
    )
    if response.status_code >= 400:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    token = payload.get("token")
    if isinstance(token, str) and token:
        return token
    return None


def cookie_snapshot(session: requests.Session) -> dict[str, str]:
    return {cookie.name: cookie.value for cookie in session.cookies}


def ensure_bypass(
    session: requests.Session | None = None,
    *,
    entry_url: str = DEFAULT_ENTRY_URL,
    refresh: bool = False,
) -> BypassResult:
    """
    Establish Imperva cookies on ``session`` using pure HTTP + Node sensor execution.

    Returns a :class:`BypassResult`. For Accor this typically yields ``___utmvc``.
    When a reese84 POST is captured, the token is stored as ``reese84``.
    """
    if session is None:
        session = requests.Session()

    result = BypassResult(entry_url=entry_url)
    parsed = urlparse(entry_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    if not refresh:
        existing = cookie_snapshot(session)
        if existing.get("reese84") or existing.get("___utmvc"):
            result.cookies = {
                name: existing[name]
                for name in IMPERVA_COOKIE_NAMES
                if name in existing
            }
            result.reese84 = "reese84" in existing
            result.utmvc = "___utmvc" in existing
            result.bypass_ok = result.reese84 or result.utmvc
            return result

    try:
        home = session.get(entry_url, headers=default_headers(), timeout=TIMEOUT)
        home.raise_for_status()
    except requests.RequestException as error:
        result.errors.append(f"homepage failed: {error}")
        return result

    script_urls = extract_incapsula_scripts(home.text, str(home.url))
    sensor_url = pick_sensor_url(script_urls)
    result.sensor_url = sensor_url
    if not sensor_url:
        result.errors.append("no Imperva sensor script found on entry page")
        return result

    try:
        sensor_response = session.get(
            sensor_url,
            headers=default_headers(referer=origin + "/"),
            timeout=TIMEOUT,
        )
        sensor_response.raise_for_status()
        runtime = run_sensor_in_node(sensor_response.text)
    except (requests.RequestException, RuntimeError, json.JSONDecodeError, OSError) as error:
        result.errors.append(f"sensor execution failed: {error}")
        return result

    apply_cookies(session, runtime.get("cookies") or {})
    result.errors.extend(str(item) for item in runtime.get("errors") or [] if item)

    posts = runtime.get("posts") or []
    result.posts = replay_runtime_requests(session, posts, referer=origin + "/", base_url=origin)

    for post in result.posts:
        if post.method != "POST" or not post.body:
            continue
        token = submit_reese_payload(session, post, referer=origin + "/")
        if token:
            session.cookies.set("reese84", token, domain=".accor.com", path="/")
            break

    # Refresh session cookies on the entry page after sensor completion.
    try:
        session.get(entry_url, headers=default_headers(referer=origin + "/"), timeout=TIMEOUT)
    except requests.RequestException as error:
        result.errors.append(f"post-bypass refresh failed: {error}")

    snapshot = cookie_snapshot(session)
    result.cookies = {
        name: snapshot[name]
        for name in IMPERVA_COOKIE_NAMES
        if name in snapshot
    }
    result.reese84 = "reese84" in snapshot
    result.utmvc = "___utmvc" in snapshot
    result.bypass_ok = result.reese84 or result.utmvc
    return result


def solve_inline_challenge(session: requests.Session, challenge_html: str, *, referer: str) -> dict[str, str]:
    """
    Attempt to solve an inline Imperva challenge page (for example API 403 HTML).
    Returns any cookies written by the challenge script.
    """
    runtime = run_sensor_in_node(challenge_html)
    cookies = dict(runtime.get("cookies") or {})
    apply_cookies(session, cookies)
    replay_runtime_requests(session, runtime.get("posts") or [], referer=referer, base_url=referer.rstrip("/"))
    return cookies


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pure HTTP Imperva bypass for all.accor.com")
    parser.add_argument("--test", action="store_true", help="Run bypass self-test and print summary JSON")
    parser.add_argument("--entry-url", default=DEFAULT_ENTRY_URL, help="Entry URL used to bootstrap the session")
    parser.add_argument("--refresh", action="store_true", help="Force a new sensor solve even if cookies exist")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    session = requests.Session()
    result = ensure_bypass(session, entry_url=args.entry_url, refresh=args.refresh)
    summary = result.summary()
    print(json.dumps(summary, indent=2))
    if args.test:
        print("reese84:", "OK" if result.reese84 else "MISSING")
        print("___utmvc:", "OK" if result.utmvc else "MISSING")
    return 0 if result.bypass_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
