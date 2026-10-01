"""Run the first script in an HTML snippet and return document.cookie."""

import execjs
from bs4 import BeautifulSoup

_PRELUDE = """
var window = {};
var document = { cookie: "" };
function setTimeout() {}
function clearTimeout() {}
"""


def run_sandboxed_script(html_content):
    """Execute the first <script> in html_content and return document.cookie.

    The script runs in a local JavaScript runtime with a minimal mock of
    window, document.cookie, setTimeout, and clearTimeout. This is a logic
    harness only: the runtime is the host JS engine (for example Node), not
    an isolated security boundary.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    script = soup.find("script")
    if script is None or script.string is None:
        return ""

    source = script.string.strip()
    if not source:
        return ""

    context = execjs.compile(_PRELUDE + "\n" + source)
    cookie = context.eval("document.cookie")
    if cookie is None:
        return ""
    return str(cookie)
