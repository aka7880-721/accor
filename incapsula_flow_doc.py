"""
Document the Imperva Incapsula network handshake observed on all.accor.com.

This script captures the HTTP sequence a browser performs during the initial page
load. It does not attempt to solve the client-side JavaScript challenge or forge
a reese84 cookie; that token is only issued after the obfuscated sensor script
executes in a real browser environment.

Use the output in security analysis reports to describe request order, headers,
cookies, and challenge resource URLs.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_ENTRY_URL = "https://www.all.accor.com/"
TIMEOUT = 30.0


@dataclass
class HttpStep:
    step: str
    method: str
    url: str
    status_code: int
    request_headers: dict[str, str]
    response_headers: dict[str, str]
    set_cookies: list[str]
    cookies_after: dict[str, str]
    notes: list[str] = field(default_factory=list)
    body_preview: str | None = None


@dataclass
class ChallengeArtifacts:
    incapsula_script_urls: list[str] = field(default_factory=list)
    inline_script_count: int = 0
    challenge_page_detected: bool = False
    reese84_present: bool = False


def _cookie_jar_snapshot(client: httpx.Client) -> dict[str, str]:
    return {cookie.name: cookie.value for cookie in client.cookies.jar}


def _header_map(response: httpx.Response) -> dict[str, str]:
    return {key: value for key, value in response.headers.items()}


def _set_cookie_headers(response: httpx.Response) -> list[str]:
    if hasattr(response.headers, "get_list"):
        return response.headers.get_list("set-cookie")
    raw = response.headers.get("set-cookie")
    return [raw] if raw else []


def _looks_like_block_page(html: str) -> bool:
    markers = (
        "Pardon Our Interruption",
        "Incapsula incident",
        "Request unsuccessful",
        "_Incapsula_Resource",
    )
    return any(marker in html for marker in markers)


def extract_incapsula_resources(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    urls: list[str] = []
    for tag in soup.find_all("script", src=True):
        src = tag.get("src", "")
        if "_Incapsula_Resource" in src or "SWJIYLWA" in src:
            urls.append(urljoin(base_url, src))
    if urls:
        return urls

    for match in re.finditer(r'/_Incapsula_Resource[^"\']+', html):
        urls.append(urljoin(base_url, match.group(0)))
    return list(dict.fromkeys(urls))


def document_incapsula_flow(
    entry_url: str = DEFAULT_ENTRY_URL,
    *,
    follow_redirects: bool = True,
) -> dict[str, Any]:
    """
    Record the legitimate HTTP steps observed during an all.accor.com page load.

    Returns a structured report suitable for security documentation. The report
    includes cookies such as visid_incap_* and incap_ses_* when the edge assigns
    them, but reese84 is typically absent until browser JavaScript completes.
    """
    steps: list[HttpStep] = []
    artifacts = ChallengeArtifacts()
    parsed_entry = urlparse(entry_url)
    origin = f"{parsed_entry.scheme}://{parsed_entry.netloc}"

    with httpx.Client(
        follow_redirects=follow_redirects,
        timeout=TIMEOUT,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    ) as client:
        final_cookies: dict[str, str] = {}
        initial = client.get(entry_url)
        initial_html = initial.text
        artifacts.incapsula_script_urls = extract_incapsula_resources(
            initial_html, str(initial.url)
        )
        artifacts.inline_script_count = len(
            BeautifulSoup(initial_html, "lxml").find_all("script")
        )
        artifacts.challenge_page_detected = _looks_like_block_page(initial_html)
        cookies_after_initial = _cookie_jar_snapshot(client)
        final_cookies = cookies_after_initial
        artifacts.reese84_present = "reese84" in cookies_after_initial

        initial_notes = []
        if initial.status_code in (403, 503):
            initial_notes.append("Edge returned an interstitial or block status.")
        if artifacts.incapsula_script_urls:
            initial_notes.append(
                "Page references Imperva sensor script via _Incapsula_Resource."
            )
        if not artifacts.reese84_present:
            initial_notes.append(
                "reese84 not issued yet; browser must execute the sensor script."
            )

        steps.append(
            HttpStep(
                step="1_initial_page_load",
                method="GET",
                url=str(initial.url),
                status_code=initial.status_code,
                request_headers={"User-Agent": USER_AGENT},
                response_headers=_header_map(initial),
                set_cookies=_set_cookie_headers(initial),
                cookies_after=cookies_after_initial,
                notes=initial_notes,
                body_preview=initial_html[:500],
            )
        )

        for index, script_url in enumerate(artifacts.incapsula_script_urls, start=1):
            script_response = client.get(
                script_url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": origin + "/",
                    "Accept": "*/*",
                },
            )
            cookies_after_script = _cookie_jar_snapshot(client)
            final_cookies = cookies_after_script
            artifacts.reese84_present = "reese84" in cookies_after_script

            script_notes = [
                "Browser would evaluate this JavaScript and then POST a sensor payload.",
                "Pure HTTP clients cannot derive the signed payload from static fingerprints.",
            ]
            if script_response.headers.get("content-type", "").startswith(
                "application/javascript"
            ):
                script_notes.append("Resource is obfuscated JavaScript (~80 KB).")

            steps.append(
                HttpStep(
                    step=f"2_fetch_sensor_script_{index}",
                    method="GET",
                    url=script_url,
                    status_code=script_response.status_code,
                    request_headers={
                        "User-Agent": USER_AGENT,
                        "Referer": origin + "/",
                    },
                    response_headers=_header_map(script_response),
                    set_cookies=_set_cookie_headers(script_response),
                    cookies_after=cookies_after_script,
                    notes=script_notes,
                    body_preview=script_response.text[:300],
                )
            )

        final_cookies = _cookie_jar_snapshot(client)
        artifacts.reese84_present = "reese84" in final_cookies
        steps.append(
            HttpStep(
                step="3_verification_post_not_reproduced",
                method="POST",
                url=f"{origin}/ (sensor endpoint; path varies by deployment)",
                status_code=0,
                request_headers={
                    "User-Agent": USER_AGENT,
                    "Referer": origin + "/",
                    "Content-Type": "application/json",
                },
                response_headers={},
                set_cookies=[],
                cookies_after=final_cookies,
                notes=[
                    "A real browser POSTs a dynamically computed JSON sensor blob.",
                    "The server responds with 302 and Set-Cookie: reese84=... on success.",
                    "This script intentionally does not forge that payload.",
                ],
            )
        )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "entryUrl": entry_url,
        "followRedirects": follow_redirects,
        "artifacts": asdict(artifacts),
        "steps": [asdict(step) for step in steps],
        "summary": {
            "reese84Obtained": artifacts.reese84_present,
            "incapsulaCookiesSeen": [
                name
                for name in final_cookies
                if name.startswith(("visid_incap_", "incap_ses_", "nlbi_", "reese84"))
            ],
            "requiresBrowserExecution": not artifacts.reese84_present,
        },
    }


def main() -> None:
    report = document_incapsula_flow()
    output_path = "incapsula_flow_report.json"
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report["summary"], indent=2))
    print(f"Wrote full report to {output_path}")


if __name__ == "__main__":
    main()
