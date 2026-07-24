"""HTML-to-text conversion for job descriptions.

All extraction (matching, sections, evidence offsets) operates on the plain
text produced here, and the same text is persisted as jobs.description_text
so offsets stored in the database remain valid for rendering.
"""

import re
from html.parser import HTMLParser

_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "tr", "table", "section", "article", "header", "footer", "blockquote",
}
_SKIP_TAGS = {"script", "style"}

_MULTI_NEWLINE = re.compile(r"\n{3,}")
_TRAILING_SPACE = re.compile(r"[ \t]+\n")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "li":
            self._chunks.append("\n• ")
        elif tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS and tag != "br":
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        raw = raw.replace("\xa0", " ").replace("​", "")
        raw = _TRAILING_SPACE.sub("\n", raw)
        raw = _MULTI_NEWLINE.sub("\n\n", raw)
        return raw.strip()


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()
