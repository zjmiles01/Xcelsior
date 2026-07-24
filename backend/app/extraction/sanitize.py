"""Sanitize untrusted job-description HTML into a safe subset for display.

Board postings arrive as HTML authored by employers on third-party ATSes;
that markup is stored (jobs.description) and, once sanitized here, served
to the browser as jobs.description_html. Untrusted HTML rendered in a page
is an XSS vector, so nothing reaches the DOM that hasn't passed through
this allowlist.

Sanitization is deliberately part of extraction (versioned by
EXTRACTOR_VERSION), not ingestion: a tightened allowlist is a version bump
and a re-extract of the immutable raw layer, exactly like any other
extractor change — never a re-fetch. The plain-text `description_text`
extraction (evidence offsets index into it) is unchanged and independent.

Allowlisting, not blocklisting: only the tags/attributes below survive;
everything else — scripts, styles, event handlers, iframes, form controls,
inline CSS, unknown schemes — is dropped. `nh3` (Rust ammonia bindings) is
the vetted sanitizer doing the work; this module only pins the policy.
"""

import nh3

# Formatting and structural tags a job description legitimately uses. No
# style/script/media/interactive tags — a description is prose, lists, and
# the occasional link, nothing that executes or loads cross-origin.
_ALLOWED_TAGS: set[str] = {
    "p", "br", "hr", "span", "div",
    "strong", "b", "em", "i", "u", "sub", "sup", "small",
    "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "code",
    "a",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
}

# The only attribute preserved anywhere is a link's href. No class/id/style
# (style carries CSS-based attacks), no width/colspan noise — the frontend
# owns presentation.
_ALLOWED_ATTRIBUTES: dict[str, set[str]] = {"a": {"href", "title"}}

# href schemes that can't script or exfiltrate. javascript:, data:, and
# vbscript: are absent by design; a stripped href leaves an inert <a>.
_URL_SCHEMES: set[str] = {"http", "https", "mailto"}

# script/style content is discarded wholesale (not just the tags) so no
# raw JS or CSS text leaks into the output as bare text nodes.
_CLEAN_CONTENT_TAGS: set[str] = {"script", "style"}


def sanitize_html(html: str | None) -> str | None:
    """Return a safe HTML subset of `html`, or None when there is nothing
    renderable. Idempotent: sanitizing already-clean output is a no-op."""
    if not html:
        return None
    cleaned = nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        clean_content_tags=_CLEAN_CONTENT_TAGS,
        url_schemes=_URL_SCHEMES,
        link_rel="noopener noreferrer nofollow",
        strip_comments=True,
    ).strip()
    return cleaned or None
