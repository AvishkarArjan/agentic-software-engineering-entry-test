#!/usr/bin/env python3

import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

PYPI = "https://pypi.org/pypi"
LINE_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(.*)$")
PIN_RE = re.compile(r"(?:^|,)\s*===?\s*([^\s,;]+)")


def parse(path):
    """Return list of (name, pinned_version_or_None) for each requirement line."""
    reqs = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.split(" #")[0].strip()  # strip inline comments
            if not line or line.startswith(("#", "-")) or "://" in line:
                continue  # blank, comment, option (-r/-e/--hash...), or URL
            line = line.split(";")[0].strip()  # drop environment markers
            m = LINE_RE.match(line)
            if not m:
                continue
            name, rest = m.groups()
            pin = PIN_RE.search(rest)
            reqs.append((name, pin.group(1) if pin else None))
    return reqs


def get_json(url):
    """Return parsed JSON, or None on 404."""
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def check(req):
    """Return (name, version, status, upload_time) with status in ok/no_pkg/no_version."""
    name, version = req
    if version is None:
        return (name, None, "ok" if get_json(f"{PYPI}/{name}/json") else "no_pkg", None)

    data = get_json(f"{PYPI}/{name}/{version}/json")
    if data is not None:
        urls = data.get("urls") or []
        upload = urls[0].get("upload_time") if urls else None
        return (name, version, "ok", upload)

    # version endpoint 404'd: does the package exist at all?
    if get_json(f"{PYPI}/{name}/json") is None:
        return (name, version, "no_pkg", None)
    return (name, version, "no_version", None)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "requirements.txt"
    reqs = parse(path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(check, reqs))

    missing_pkgs = [n for n, _, s, _ in results if s == "no_pkg"]
    missing_vers = [f"{n}=={v}" for n, v, s, _ in results if s == "no_version"]
    dated = [(t, n, v) for n, v, s, t in results if s == "ok" and v and t]
    oldest = min(dated) if dated else None  # ISO timestamps sort chronologically
    
    print(f"Dependencies checked: {len(reqs)}")
    print(f"Packages not on PyPI: {len(missing_pkgs)}")
    print(f"Versions not on PyPI: {len(missing_vers)}")
    if oldest:
        t, n, v = oldest
        print(f"Oldest pinned release: {n}=={v} ({t[:4]})")
    else:
        print("Oldest pinned release: none")


if __name__ == "__main__":
    main()