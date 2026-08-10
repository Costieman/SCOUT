from __future__ import annotations

import json
from urllib.request import Request, urlopen

URL = "https://stooq.com/q/d/l/?s=spy.us&d1=20260401&d2=20260807&i=d"

headersets = {
    "trade_scout": {
        "Accept": "text/csv",
        "User-Agent": "Trade-Scout/0.1",
    },
    "browser_like": {
        "Accept": "text/csv,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0 Safari/537.36"
        ),
    },
}

for label, headers in headersets.items():
    request = Request(URL, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read()
            text = payload[:500].decode("utf-8", errors="replace")
            print(json.dumps({
                "label": label,
                "status": getattr(response, "status", None),
                "content_type": response.headers.get("Content-Type"),
                "length": len(payload),
                "prefix": text.replace("\n", "\\n")[:500],
            }, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"label": label, "error": repr(exc)}, sort_keys=True))
