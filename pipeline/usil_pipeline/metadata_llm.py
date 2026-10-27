"""Last-resort metadata: Claude reads the authors and venue from the paper's first page.

Used only when the bibliographic APIs find nothing. Claude must copy each answer's source text verbatim from the
page; an answer whose source cannot be found on the page is discarded. Nothing comes from the model's memory.
"""
from pydantic import BaseModel, Field

from .quotes import norm

SYSTEM = """You read the first page of a research paper and copy out its authors and where it was published.
Use ONLY the page text. Never use outside knowledge. If something is not on the page, return an empty string.
For each answer, also return the exact text from the page you took it from (copied verbatim)."""

USER = """Paper title (from our records): {title}

<first_page>
{page}
</first_page>"""


class FirstPage(BaseModel):
    authors: str = Field(description="Author names, comma-separated, in page order; '' if not on the page.")
    authors_source: str = Field(description="The verbatim line(s) of the page listing the authors.")
    venue: str = Field(description="Journal, conference, or workshop name (with volume/year if shown); '' if not on the page.")
    venue_source: str = Field(description="The verbatim text naming the venue (header, footer, or copyright line).")


def _on_page(source, page):
    s = norm(source)
    return len(s) >= 6 and s in norm(page)


def read_first_page(llm, model, key, title, pages):
    """{'authors': ..., 'venue': ...} with only the fields whose source text was found on page 1."""
    page = (pages[0] if pages else "")[:6000]
    if len(page) < 200:
        return {}
    out, _ = llm.structured(stage="firstpage", paper_key=key, model=model, system=SYSTEM,
                            user=USER.format(title=title, page=page), schema=FirstPage, max_tokens=1000)
    found = {}
    if out["authors"] and _on_page(out["authors_source"], page):
        found["authors"] = out["authors"]
    if out["venue"] and _on_page(out["venue_source"], page):
        found["venue"] = out["venue"]
    return found
