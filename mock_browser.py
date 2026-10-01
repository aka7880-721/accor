USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class Document:
    def __init__(self):
        self._cookies = {}

    @property
    def cookie(self):
        return "; ".join(f"{name}={value}" for name, value in self._cookies.items())

    @cookie.setter
    def cookie(self, raw):
        pair = str(raw).split(";", 1)[0]
        separator = pair.find("=")
        if separator == -1:
            return
        name = pair[:separator].strip()
        value = pair[separator + 1 :].strip()
        if not name:
            return
        self._cookies[name] = value


def create_mock_browser():
    document = Document()
    navigator = {
        "userAgent": USER_AGENT,
        "language": "en-US",
        "languages": ["en-US", "en"],
        "platform": "Win32",
    }
    screen = {
        "width": 1920,
        "height": 1080,
        "availWidth": 1920,
        "availHeight": 1040,
        "colorDepth": 24,
        "pixelDepth": 24,
    }
    window = {
        "document": document,
        "navigator": navigator,
        "screen": screen,
    }
    window["window"] = window
    window["self"] = window
    return {
        "window": window,
        "document": document,
        "navigator": navigator,
        "screen": screen,
    }
