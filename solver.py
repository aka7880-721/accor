from pathlib import Path

from mock_browser import create_mock_browser

CHALLENGE_FILE = Path(__file__).resolve().parent / "challenge.js"


def solve_challenge():
    if not CHALLENGE_FILE.exists():
        raise FileNotFoundError("challenge.js was not found. Run extract.py first.")

    # The current page script calls this helper from its else branch.
    # That helper is not defined in challenge.js, and it does not write a cookie.
    sandbox = create_mock_browser()
    sandbox["makeTargetedComponentVisible"] = lambda *_args, **_kwargs: None
    CHALLENGE_FILE.read_text(encoding="utf-8")
    return sandbox["document"].cookie


if __name__ == "__main__":
    print(solve_challenge())
