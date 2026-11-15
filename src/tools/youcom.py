"""Web search through You.com. Works without an API key.

With no key, requests go to the free keyless endpoint (about 100 searches a
day). Set YDC_API_KEY to use the keyed endpoint and its higher limits.
"""

import os

import requests

KEYLESS_URL = "https://api.you.com/v1/agents/search"
KEYED_URL = "https://ydc-index.io/v1/search"
USER_AGENT = "youdotcom-integration/zi-yue-1129-DATAGEN"
KEYLESS_MAX_COUNT = 50
KEYED_MAX_COUNT = 100


def _request(query: str, count: int) -> dict:
    api_key = os.environ.get("YDC_API_KEY", "").strip()
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if api_key:
        count = max(1, min(count, KEYED_MAX_COUNT))
        response = requests.post(
            KEYED_URL,
            headers={**headers, "X-API-Key": api_key},
            json={"query": query, "count": count},
            timeout=20,
        )
    else:
        count = max(1, min(count, KEYLESS_MAX_COUNT))
        response = requests.get(
            KEYLESS_URL,
            headers=headers,
            params={"query": query, "count": count},
            timeout=20,
        )
    if response.status_code in (401, 403):
        raise ValueError(f"You.com rejected YDC_API_KEY (HTTP {response.status_code})")
    if response.status_code in (402, 429) and not api_key:
        raise ValueError(
            f"You.com keyless limit reached (HTTP {response.status_code}). "
            "Set YDC_API_KEY for higher limits."
        )
    response.raise_for_status()
    return response.json()


def youcom_search(query: str, count: int = 5) -> str:
    """Search the web with You.com and return the top results as plain text.

    Each result is formatted as title, snippet and link, the same layout the
    google_search tool returns. Raises on network or API errors.
    """
    data = _request(query, count)
    results = data.get("results") or {}
    items = list(results.get("web") or []) + list(results.get("news") or [])
    lines = []
    for item in items[:count]:
        title = item.get("title") or "No Title"
        snippets = item.get("snippets") or []
        snippet = " ".join(snippets[:2]) or item.get("description") or "No Snippet"
        link = item.get("url") or "No Link"
        lines.append(f"{title}\n{snippet}\n{link}\n\n")
    return "".join(lines)
