"""Optional webpage extraction through Monid's TinyFish endpoint."""

import json
import os
import time

import requests


def _extract_page(url: str, headers: dict) -> str:
    deadline = time.monotonic() + 300
    response = requests.post(
        "https://api.monid.ai/v1/run",
        headers={**headers, "Content-Type": "application/json; charset=utf-8"},
        data=json.dumps(
            {
                "provider": "tinyfish",
                "endpoint": "/automation/run",
                "input": {
                    "queryParams": {},
                    "pathParams": {},
                    "body": {
                        "url": url,
                        "goal": "Extract the main text content of this webpage as content.",
                        "output_schema": {
                            "type": "object",
                            "properties": {"content": {"type": "string"}},
                            "required": ["content"],
                        },
                    },
                },
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        timeout=60,
    )
    response.raise_for_status()
    run = response.json()
    if response.status_code == 202:
        run_id = run["runId"]
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Monid run timed out")
            time.sleep(min(2, remaining))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Monid run timed out")
            response = requests.get(
                f"https://api.monid.ai/v1/runs/{run_id}",
                headers=headers,
                timeout=min(30, remaining),
            )
            response.raise_for_status()
            run = response.json()
            if run.get("status") in (
                "COMPLETED", "FAILED", "TIMED_OUT", "STOPPED", "BLOCKED"
            ):
                break
    provider_response = run.get("providerResponse") or {}
    if provider_response.get("httpStatus", 200) >= 400:
        raise ValueError(
            f"TinyFish error {provider_response['httpStatus']}: "
            f"{provider_response.get('error')}"
        )
    if run.get("status") not in (None, "COMPLETED"):
        raise RuntimeError(f"Monid run {run.get('status')}")
    result = run["output"]["result"]
    if not isinstance(result, dict) or not isinstance(result.get("content"), str):
        raise ValueError("TinyFish did not return webpage content")
    return result["content"]


def monid(urls: list[str]) -> str:
    """Extract webpage text using Monid and TinyFish. Requires MONID_API_KEY.

    Pages come back in input order. A URL that fails becomes
    `Error: <url>: <reason>`, so only those URLs need a retry.
    """
    api_key = os.environ.get("MONID_API_KEY")
    if not api_key:
        return "Error: MONID_API_KEY is not set"
    headers = {"Authorization": f"Bearer {api_key}"}
    pages = []
    for url in urls:
        try:
            pages.append(_extract_page(url, headers))
        except Exception as e:
            pages.append(f"Error: {url}: {e}")
    return "\n\n".join(pages)
