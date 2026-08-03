from __future__ import annotations

import argparse
import base64
from html.parser import HTMLParser
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

from .bufr import is_bufr_payload
from .centers import issuing_agency


JTWC_PRODUCTS = (
    "https://www.metoc.navy.mil/jtwc/products/abpwweb.txt",
)

VHHH_TROPICAL_CYCLONE_WARNING_INDEX = "https://www.wis-jma.go.jp/d/o/VHHH/Alphanumeric/Warning/Tropical_cyclone/"
VHHH_HIMAWARI_SAREP_BUFR_INDEX = "https://www.wis-jma.go.jp/d/o/VHHH/BUFR/Satellite(Himawari)/SAREP/"
RJTD_HIMAWARI_SAREP_BUFR_INDEX = "https://www.wis-jma.go.jp/d/o/RJTD/BUFR/Satellite(Himawari)/SAREP/"

DEFAULT_SOURCES = (
    *JTWC_PRODUCTS,
    VHHH_TROPICAL_CYCLONE_WARNING_INDEX,
    VHHH_HIMAWARI_SAREP_BUFR_INDEX,
    RJTD_HIMAWARI_SAREP_BUFR_INDEX,
)


class DirectoryLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


def fetch_text(url: str, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "typhoon-tac-parser/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        body = response.read().decode("utf-8", errors="replace")
    if body.lstrip().startswith("<"):
        raise ValueError(f"{url} returned HTML instead of TAC text ({content_type})")
    return body


def fetch_binary(url: str, timeout: int = 20) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "typhoon-tac-parser/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        body = response.read()
    return body, content_type


def fetch_bytes(url: str, timeout: int = 20) -> tuple[str, str]:
    body, content_type = fetch_binary(url, timeout)
    return body.decode("utf-8", errors="replace"), content_type


def is_directory_url(url: str) -> bool:
    return urlparse(url).path.endswith("/")


def directory_product_links(index_url: str, max_depth: int = 3) -> list[str]:
    return _directory_product_links(index_url, max_depth=max_depth, depth=0, seen=set())


def _directory_product_links(index_url: str, max_depth: int, depth: int, seen: set[str]) -> list[str]:
    if index_url in seen:
        return []
    seen.add(index_url)
    html, _ = fetch_bytes(index_url)
    parser = DirectoryLinkParser()
    parser.feed(html)
    links = []
    for href in parser.links:
        if href.startswith("?") or href.startswith("/icons/") or "Parent Directory" in href:
            continue
        absolute = urljoin(index_url, href)
        if absolute.rstrip("/") == index_url.rstrip("/"):
            continue
        if absolute.endswith("/"):
            if depth < max_depth:
                links.extend(_directory_product_links(absolute, max_depth=max_depth, depth=depth + 1, seen=seen))
            continue
        links.append(absolute)
    return sorted(set(links))


def center_from_url(url: str) -> str | None:
    match = re.search(r"/d/o/([A-Z]{4})/", url)
    if match:
        return match.group(1)
    match = re.search(r"_C_([A-Z]{4})_", url)
    if match:
        return match.group(1)
    return None


def source_from_url(url: str) -> str:
    center = center_from_url(url)
    if center:
        return f"wis-{center.lower()}"
    return "url"


def split_bulletins(text: str) -> list[str]:
    chunks = re.split(r"\n(?=[A-Z]{4}\d{0,2}\s+[A-Z]{4}\s+\d{6})", text.strip())
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def crawl_urls(urls: Iterable[str]) -> list[dict[str, str]]:
    fetched_at = datetime.now(timezone.utc).isoformat()
    records = []
    for url in urls:
        if is_directory_url(url):
            try:
                product_urls = directory_product_links(url)
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                records.append({"source": "error", "url": url, "fetched_at": fetched_at, "error": str(exc), "raw": ""})
                continue
            if not product_urls:
                records.append({"source": "directory", "url": url, "fetched_at": fetched_at, "raw": "", "note": "No bulletin files found."})
                continue
            records.extend(crawl_urls(product_urls))
            continue
        try:
            binary, content_type = fetch_binary(url)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            records.append({"source": "error", "url": url, "fetched_at": fetched_at, "error": str(exc), "raw": ""})
            continue
        center = center_from_url(url)
        agency = (issuing_agency(center) or "Unknown") if center else None
        if url.lower().endswith(".bufr") or is_bufr_payload(binary):
            records.append({
                "source": source_from_url(url),
                "url": url,
                "fetched_at": fetched_at,
                "format": "BUFR",
                "content_type": content_type,
                "issuing_center": center,
                "issuing_agency": agency,
                "raw_base64": base64.b64encode(binary).decode("ascii"),
                "byte_length": len(binary),
            })
            continue
        text = binary.decode("utf-8", errors="replace")
        if text.lstrip().startswith("<"):
            records.append({"source": "error", "url": url, "fetched_at": fetched_at, "error": f"{url} returned HTML instead of TAC/BUFR data", "raw": ""})
            continue
        source = source_from_url(url)
        for bulletin in split_bulletins(text):
            records.append({"source": source, "url": url, "fetched_at": fetched_at, "issuing_center": center, "issuing_agency": agency, "raw": bulletin})
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch tropical cyclone TAC bulletins.")
    parser.add_argument("--url", action="append", help="Bulletin URL. Can be repeated.")
    parser.add_argument("--output", default="data/raw_bulletins.jsonl")
    args = parser.parse_args()

    urls = args.url or list(DEFAULT_SOURCES)
    records = crawl_urls(urls)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
