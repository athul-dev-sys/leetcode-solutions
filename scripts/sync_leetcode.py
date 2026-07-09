#!/usr/bin/env python3
"""Sync LeetCode submissions into a Git repository.

This script uses the same authenticated endpoint that the LeetCode submissions
page uses. LeetCode does not publish this as a stable public API, so failures
usually mean the session cookie expired or LeetCode changed the endpoint.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / ".leetcode_sync_state.json"
SUBMISSIONS_DIR = ROOT / "submissions"
SOLUTIONS_DIR = ROOT / "solutions"

LANG_EXTENSIONS = {
    "bash": "sh",
    "c": "c",
    "c#": "cs",
    "c++": "cpp",
    "cpp": "cpp",
    "dart": "dart",
    "elixir": "ex",
    "erlang": "erl",
    "go": "go",
    "golang": "go",
    "java": "java",
    "javascript": "js",
    "kotlin": "kt",
    "mysql": "sql",
    "mssql": "sql",
    "oraclesql": "sql",
    "pandas": "py",
    "php": "php",
    "postgresql": "sql",
    "python": "py",
    "python3": "py",
    "racket": "rkt",
    "ruby": "rb",
    "rust": "rs",
    "scala": "scala",
    "swift": "swift",
    "typescript": "ts",
}


def getenv_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"seen_submission_ids": [], "last_sync_at": None}
    with STATE_FILE.open("r", encoding="utf-8") as handle:
        state = json.load(handle)
    state.setdefault("seen_submission_ids", [])
    state.setdefault("last_sync_at", None)
    return state


def save_state(state: dict[str, Any]) -> None:
    state["seen_submission_ids"] = sorted(set(map(str, state["seen_submission_ids"])))
    state["last_sync_at"] = datetime.now(timezone.utc).isoformat()
    with STATE_FILE.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    return value.strip("-") or "unknown"


def extension_for(language: str) -> str:
    key = language.strip().lower()
    return LANG_EXTENSIONS.get(key, slugify(key) or "txt")


def allowed_statuses() -> set[str] | None:
    raw = os.getenv("LEETCODE_SYNC_STATUSES", "all").strip()
    if not raw or raw.lower() == "all":
        return None
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def request_json(url: str, session: str, csrf_token: str) -> dict[str, Any]:
    cookie = f"LEETCODE_SESSION={session}; csrftoken={csrf_token}"
    request = Request(
        url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Cookie": cookie,
            "Referer": os.getenv("LEETCODE_BASE_URL", "https://leetcode.com"),
            "User-Agent": "leetcode-github-sync/1.0",
            "X-CSRFToken": csrf_token,
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"LeetCode request failed with HTTP {exc.code}: {body[:500]}") from exc
    except URLError as exc:
        raise SystemExit(f"LeetCode request failed: {exc}") from exc


def fetch_submissions(session: str, csrf_token: str, seen_ids: set[str]) -> list[dict[str, Any]]:
    base_url = os.getenv("LEETCODE_BASE_URL", "https://leetcode.com").rstrip("/")
    limit = int(os.getenv("LEETCODE_PAGE_LIMIT", "20"))
    max_pages_raw = os.getenv("LEETCODE_MAX_PAGES", "").strip()
    max_pages = int(max_pages_raw) if max_pages_raw else None

    submissions: list[dict[str, Any]] = []
    offset = 0
    last_key = ""
    page = 0

    while True:
        query = urlencode({"offset": offset, "limit": limit, "lastkey": last_key})
        data = request_json(f"{base_url}/api/submissions/?{query}", session, csrf_token)
        page_submissions = data.get("submissions_dump", [])
        submissions.extend(page_submissions)

        page += 1
        if page_submissions and all(submission_id(item) in seen_ids for item in page_submissions):
            break
        if max_pages is not None and page >= max_pages:
            break
        if not data.get("has_next") or not page_submissions:
            break

        last_key = data.get("last_key") or ""
        offset += limit
        time.sleep(0.4)

    return submissions


def submission_id(submission: dict[str, Any]) -> str:
    return str(
        submission.get("id")
        or submission.get("submission_id")
        or submission.get("timestamp")
        or hash(json.dumps(submission, sort_keys=True))
    )


def submitted_at(submission: dict[str, Any]) -> str:
    timestamp = submission.get("timestamp") or submission.get("time")
    if timestamp:
        try:
            return datetime.fromtimestamp(int(timestamp), timezone.utc).strftime("%Y%m%d_%H%M%S")
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def status_for(submission: dict[str, Any]) -> str:
    return str(submission.get("status_display") or submission.get("statusDisplay") or "Unknown")


def language_for(submission: dict[str, Any]) -> str:
    return str(submission.get("lang") or submission.get("lang_name") or submission.get("langName") or "txt")


def problem_slug_for(submission: dict[str, Any]) -> str:
    return slugify(str(submission.get("title_slug") or submission.get("titleSlug") or submission.get("title") or "unknown-problem"))


def code_for(submission: dict[str, Any]) -> str:
    code = submission.get("code")
    if code is None:
        return ""
    return str(code).replace("\r\n", "\n").rstrip() + "\n"


def write_submission(submission: dict[str, Any]) -> None:
    sid = submission_id(submission)
    problem_slug = problem_slug_for(submission)
    language = language_for(submission)
    ext = extension_for(language)
    status_slug = slugify(status_for(submission))
    stamp = submitted_at(submission)
    code = code_for(submission)

    problem_dir = SUBMISSIONS_DIR / problem_slug
    problem_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"{stamp}_{sid}_{status_slug}"
    source_path = problem_dir / f"{base_name}.{ext}"
    metadata_path = problem_dir / f"{base_name}.json"

    source_path.write_text(code, encoding="utf-8")
    metadata = {
        "id": sid,
        "problem": submission.get("title"),
        "problem_slug": problem_slug,
        "status": status_for(submission),
        "language": language,
        "runtime": submission.get("runtime"),
        "memory": submission.get("memory"),
        "timestamp": submission.get("timestamp") or submission.get("time"),
        "url": submission.get("url"),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if status_for(submission).lower() == "accepted" and code:
        solution_dir = SOLUTIONS_DIR / problem_slug
        solution_dir.mkdir(parents=True, exist_ok=True)
        (solution_dir / f"{problem_slug}.{ext}").write_text(code, encoding="utf-8")
        (solution_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    session = getenv_required("LEETCODE_SESSION")
    csrf_token = getenv_required("LEETCODE_CSRF_TOKEN")
    statuses = allowed_statuses()
    state = load_state()
    seen_ids = set(map(str, state["seen_submission_ids"]))

    submissions = fetch_submissions(session, csrf_token, seen_ids)
    new_count = 0
    skipped_count = 0

    for submission in submissions:
        sid = submission_id(submission)
        if sid in seen_ids:
            skipped_count += 1
            continue

        status = status_for(submission).lower()
        if statuses is not None and status not in statuses:
            seen_ids.add(sid)
            skipped_count += 1
            continue

        write_submission(submission)
        seen_ids.add(sid)
        new_count += 1

    state["seen_submission_ids"] = sorted(seen_ids)
    save_state(state)

    print(f"Fetched {len(submissions)} submissions.")
    print(f"Archived {new_count} new submissions.")
    print(f"Skipped {skipped_count} submissions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
