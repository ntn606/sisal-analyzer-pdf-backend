"""Deterministic metadata extraction; no JavaScript, LLM or article-body cache."""

import re
from datetime import date
from html.parser import HTMLParser

from .security import SafeError, instant, load_json, unsafe_content


class MetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = []
        self.in_title = False
        self.metadata = {}
        self.jsonld = []
        self.in_ld = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            key = a.get("property", a.get("name", "")).lower()
            if key in ("og:title", "article:published_time"):
                self.metadata[key] = a.get("content", "")
        if tag == "script" and a.get("type") == "application/ld+json":
            self.in_ld = True
            self.jsonld.append("")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "script":
            self.in_ld = False

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if self.in_ld and self.jsonld:
            self.jsonld[-1] += data


def metadata(raw, media_type):
    if media_type != "text/html":
        raise SafeError("unexpected_content_type")
    try:
        text = raw.decode("utf-8")
        parser = MetadataParser()
        parser.feed(text)
        parser.close()
    except (UnicodeError, ValueError):
        raise SafeError("html_parsing_failed") from None
    title = parser.metadata.get("og:title") or "".join(parser.title)
    published = parser.metadata.get("article:published_time")
    publication_basis = "html_meta" if published else None
    for item in parser.jsonld[:8]:
        if len(item) > 16_000:
            continue
        try:
            node = load_json(item)
        except SafeError:
            continue
        nodes = (
            node
            if isinstance(node, list)
            else node.get("@graph", [node])
            if isinstance(node, dict)
            else []
        )
        if not isinstance(nodes, list):
            continue
        for obj in nodes[:20]:
            if isinstance(obj, dict) and obj.get("@type") in ("NewsArticle", "Article"):
                published = published or obj.get("datePublished")
                title = title or obj.get("headline", "")
                publication_basis = (
                    "jsonld_datePublished" if published else publication_basis
                )
    if (
        not isinstance(title, str)
        or published is not None
        and not isinstance(published, str)
    ):
        raise SafeError("metadata_contract_invalid")
    title = re.sub(r"\s+", " ", title or "").strip()[:160]
    rejected = unsafe_content(title) or unsafe_content(published or "")
    if rejected:
        return {
            "title": None,
            "published_at": None,
            "publication_date": None,
            "publication_basis": None,
            "content_quarantined": True,
            "reason": rejected,
        }
    date_value = None
    stamp = None
    if isinstance(published, str):
        try:
            stamp = instant(published).isoformat()
        except SafeError:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
                try:
                    date.fromisoformat(published)
                    date_value = published
                except ValueError:
                    pass
    return {
        "title": title or None,
        "published_at": stamp,
        "publication_date": date_value,
        "publication_basis": publication_basis if stamp or date_value else None,
        "content_quarantined": False,
        "reason": None,
    }
