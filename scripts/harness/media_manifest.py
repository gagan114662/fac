#!/usr/bin/env python3
"""Scan artifacts directory for media files and build a media manifest JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


MEDIA_EXTENSIONS = {
    ".png": "screenshot",
    ".jpg": "screenshot",
    ".jpeg": "screenshot",
    ".gif": "screenshot",
    ".mp4": "video",
    ".webm": "video",
    ".cast": "asciinema",
}


def scan_artifacts(artifacts_dir: str) -> List[Dict[str, Any]]:
    """Scan a directory for media files and return manifest items."""
    items: List[Dict[str, Any]] = []
    path = Path(artifacts_dir)
    if not path.is_dir():
        return items

    for file in sorted(path.iterdir()):
        if not file.is_file():
            continue
        suffix = file.suffix.lower()
        media_type = MEDIA_EXTENSIONS.get(suffix)
        if media_type is None:
            continue
        item: Dict[str, Any] = {
            "type": media_type,
            "path": str(file),
            "label": file.stem.replace("-", " ").replace("_", " "),
        }
        items.append(item)

    return items


def build_manifest(artifacts_dir: str = "artifacts",
                   loom_urls: List[str] | None = None,
                   asciinema_urls: List[str] | None = None) -> Dict[str, Any]:
    """Build a complete media manifest from scanned files and explicit URLs."""
    items = scan_artifacts(artifacts_dir)

    for url in (loom_urls or []):
        thumbnail = ""
        # Extract Loom ID for thumbnail if URL matches expected pattern
        parts = url.rstrip("/").split("/")
        if parts:
            loom_id = parts[-1]
            thumbnail = f"https://cdn.loom.com/sessions/thumbnails/{loom_id}.jpg"
        items.append({
            "type": "loom",
            "url": url,
            "thumbnail": thumbnail,
        })

    for url in (asciinema_urls or []):
        items.append({
            "type": "asciinema",
            "url": url,
        })

    return {"items": items}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build media manifest from artifacts")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Directory to scan for media files")
    parser.add_argument("--loom-url", action="append", default=[], help="Loom video URL (repeatable)")
    parser.add_argument("--asciinema-url", action="append", default=[], help="Asciinema recording URL (repeatable)")
    parser.add_argument("--out", default="artifacts/media-manifest.json", help="Output manifest path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_manifest(
        artifacts_dir=args.artifacts_dir,
        loom_urls=args.loom_url,
        asciinema_urls=args.asciinema_url,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
