import re
import subprocess
import tempfile
import nh3
from datetime import date
from html import unescape
import email
from email.message import EmailMessage
from email.utils import formataddr, getaddresses, parseaddr, parsedate_to_datetime
from os import getenv
from pathlib import Path

from inbox_manager.markdown_render import md_to_html, md_to_text

# Where the forward/receipt boilerplate lives.
TEMPLATE_DIR = Path(
    getenv("INBOX_TEMPLATE_DIR") or Path(__file__).resolve().parents[4] / "templates"
)

# ---- sanitisation policy for untrusted forwarded HTML ----
ALLOWED_TAGS = {
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}
ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}
ALLOWED_SCHEMES = {"https", "mailto", "cid"}  # no http / javascript: / data:
ALLOWED_IMG_SUBTYPES = {"png", "jpeg", "jpg", "gif", "webp"}
SAFE_CID = re.compile(r"^[A-Za-z0-9._%+@-]+$")
MAX_IMAGES = 20
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_BODY_CHARS = 500_000
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _strip_controls(s):
    return _CONTROL.sub("", (s or "").replace("\r\n", "\n").replace("\r", "\n"))


def _header_value(s):
    """One-line, control-free version of an untrusted header for display/use."""
    return _strip_controls(s or "").replace("\n", " ").strip()


def _block_remote_images(tag, attr, value):
    # drop any image source that isn't an inline cid: reference (kills tracking pixels)
    if tag == "img" and attr == "src" and not value.lower().startswith("cid:"):
        return None
    return value


def _sanitize_html(raw_html):
    return nh3.clean(
        raw_html[:MAX_BODY_CHARS],
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        clean_content_tags={"script", "style"},  # remove tags AND their text content
        url_schemes=ALLOWED_SCHEMES,
        link_rel="noopener noreferrer",
        attribute_filter=_block_remote_images,
    )


def _html_to_text(html):
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p\s*>", "\n\n", html)
    html = re.sub(r"(?i)</div\s*>", "\n", html)
    return unescape(re.sub(r"(?s)<[^>]+>", "", html)).strip()


def _safe_inline_images(msg, clean_html):
    """(cid, data, subtype) for images that are safe AND actually referenced."""
    count = 0
    for part in msg.walk():
        if count >= MAX_IMAGES:
            break
        cid = part["Content-ID"]
        if not cid or part.get_content_maintype() != "image":
            continue
        cid = cid.strip("<>")
        subtype = part.get_content_subtype()
        if not SAFE_CID.match(cid) or subtype not in ALLOWED_IMG_SUBTYPES:
            continue
        if f"cid:{cid}" not in clean_html:  # skip unreferenced parts
            continue
        data = part.get_content()
        if not isinstance(data, (bytes, bytearray)) or len(data) > MAX_IMAGE_BYTES:
            continue
        count += 1
        yield cid, data, ("jpeg" if subtype == "jpg" else subtype)


def _copy_attachments(dest, source):
    """Re-attach every real attachment of `source` onto `dest`, verbatim."""
    for part in source.iter_attachments():
        data = part.get_payload(decode=True)
        if data is None:
            continue
        dest.add_attachment(
            data,
            maintype=part.get_content_maintype(),
            subtype=part.get_content_subtype(),
            filename=part.get_filename(),
        )


def _escape(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _text_to_html(text):
    """Escape plain text and keep its line breaks when rendered as HTML."""
    return "<br>".join(_escape(ln) for ln in (text or "").split("\n"))


def body_to_text(original):
    """Plain-text representation of a parsed message's body, preferring a
    real text/plain part and falling back to converting the HTML part."""
    plain_part = original.get_body(preferencelist=("plain",))
    html_part = original.get_body(preferencelist=("html",))
    if plain_part is not None:
        text = plain_part.get_content()
    elif html_part is not None:
        text = _html_to_text(html_part.get_content())
    else:
        text = ""
    return _strip_controls(text)[:MAX_BODY_CHARS]


def reporter_from(original):
    """The reporter's address, resolving the security@ list's 'via' munging.

    A report arriving through security@apache.org has its From rewritten to
    'Name via security <security@apache.org>' with the real sender in Reply-To;
    in that case the Reply-To is returned, otherwise the original From.
    """
    _, addr = parseaddr(original["From"] or "")
    if addr.lower() == "security@apache.org" and original["Reply-To"]:
        return original["Reply-To"]
    return original["From"]


def make_forward(original, intro_md, from_addr, to_addr):
    """Forward `original` (parsed with policy=default), quoting it inline,
    hardened against hostile content in the forwarded message.

    ``intro_md`` is the team's covering note as Markdown (the rendered
    ``forward.md`` / ``forward-duplicate.md`` template); it is rendered
    to both a wrapped plain-text part and a sanitised HTML part. The forward is
    always multipart/alternative so the covering note keeps its formatting even
    when the original report was plain text.
    """
    fwd = EmailMessage()
    fwd["Message-ID"] = email.utils.make_msgid(domain="security.apache.org")
    fwd["From"] = from_addr
    fwd["To"] = to_addr
    _, to_email = parseaddr(to_addr)
    if not re.fullmatch(r"security@.+\.apache\.org", to_email, re.IGNORECASE):
        fwd["Cc"] = "ASF Security <security@apache.org>"
    subject = _header_value(original["Subject"])
    fwd["Subject"] = (
        subject if subject.lower().startswith("fwd:") else f"Fwd: {subject}"
    )
    mid = original["Message-ID"]
    if mid:
        fwd["References"] = mid

    html_part = original.get_body(preferencelist=("html",))

    header_lines = [
        "---------- Forwarded message ----------",
        f"From: {_header_value(reporter_from(original))}",
        f"Date: {_header_value(original['Date'])}",
        f"Subject: {_header_value(original['Subject'])}",
        f"To: {_header_value(original['To'])}",
    ]

    # --- plain-text body ---
    original_text = body_to_text(original)
    plain_body = (
        f"{md_to_text(intro_md)}\n\n" + "\n".join(header_lines) + f"\n{original_text}"
    )

    # --- html body: rendered note + (sanitised original html | escaped text) ---
    header_html = _text_to_html("\n".join(header_lines))
    intro_html = _sanitize_html(md_to_html(intro_md))
    if html_part is not None:
        original_html = _sanitize_html(html_part.get_content())
    else:
        original_html = _text_to_html(original_text)
    html_body = (
        f"<div>{intro_html}</div><br>"
        f"<div>{header_html}</div>"
        f'<blockquote style="margin:0 0 0 .8ex;border-left:2px solid #ccc;padding-left:1ex">'
        f"{original_html}"
        f"</blockquote>"
    )

    fwd.set_content(plain_body)
    fwd.add_alternative(html_body, subtype="html")

    if html_part is not None:
        html_alt = fwd.get_payload()[1]
        for cid, data, subtype in _safe_inline_images(original, original_html):
            html_alt.add_related(
                data, maintype="image", subtype=subtype, cid=f"<{cid}>"
            )

    _copy_attachments(fwd, original)
    return fwd


def message_date(original):
    """The message's Date as yyyy-mm-dd, falling back to today if unparsable."""
    raw = original["Date"]
    if raw:
        try:
            return parsedate_to_datetime(raw).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            pass
    return date.today().strftime("%Y-%m-%d")


# Every marker any template can carry. The fill_*_template helpers fill the
# content ones (summary/reason/note/model/duplicate) from the bundle fragments,
# and fill_markers() fills the rest from the PMC / live message / operator. After
# filling, a line still holding any of these is dropped so no raw <placeholder>
# leaks into the sent mail.
_ALL_MARKERS = (
    "PMC name",
    "PMC security address",
    "Reporter name",
    "Triager full name",
    "link",
    "model link",
    "contributing link",
    "dashboard link",
    "summary",
    "reason",
    "note",
    "model",
    "duplicate",
)


def _apply(text, mapping):
    """Replace each marker (escaped ``\\<key>`` or bare ``<key>``) with its value."""
    for key, val in mapping.items():
        text = text.replace(f"\\<{key}>", val).replace(f"<{key}>", val)
    return text


def fill_markers(text, pmc, original, triager_name):
    """Fill the identity / PMC / infra markers in a template, then drop any line
    whose marker stayed empty.

    The fill_*_template helpers fill the content markers (summary / reason /
    note / model / duplicate) from the bundle fragments first; this fills the
    rest from the PMC coordinates, the live message, and the operator identity,
    then removes any line still carrying an unfilled marker (a PMC with no
    threat-model link, an empty receipt note, ...).
    """
    name, addr = parseaddr(reporter_from(original) or "")
    values = {
        "Reporter name": name or addr or "there",
        "Triager full name": triager_name or "the Apache Security Team",
    }
    if pmc:
        values["PMC name"] = pmc.name or pmc.id
        values["dashboard link"] = f"https://dash.security.apache.org/project/{pmc.id}"
        if pmc.specialized:
            values["PMC security address"] = pmc.security_contact
        # Human-facing templates cite the readable security page, not the raw
        # SECURITY.md source (which feeds the assessors instead).
        if pmc.security_model_link:
            values["link"] = pmc.security_model_link
            values["model link"] = pmc.security_model_link
        if pmc.contributing:
            values["contributing link"] = pmc.contributing
    text = _apply(text, values)
    text = "".join(
        ln
        for ln in text.splitlines(keepends=True)
        if not any(f"<{m}>" in ln for m in _ALL_MARKERS)
    )
    return re.sub(r"\n{3,}", "\n\n", text)


def fill_llm_suggestions_template(summary, model):
    """Render the "summary" section of a forward"""
    content = {}
    content["summary"] = summary
    content["model"] = model
    return _apply(
        (TEMPLATE_DIR / "forward-llm-summary.md").read_text(encoding="utf-8"), content
    )


def fill_forward_template(pmc, original, summary, model, triager_name, duplicate_of=""):
    """Render the PMC forward: forward-duplicate.md when ``duplicate_of`` is set,
    else forward.md. The content markers (summary / model / duplicate) are filled
    here from the bundle, the rest via fill_markers; an empty summary / model
    just drops its line.

    Serves both the cache-driven path (summary from the bundle's summary.md) and
    the interactive fallback (empty summary when there is no assessed bundle).
    """
    name = "forward-duplicate.md" if duplicate_of else "forward.md"
    content = {}
    if summary:
        content["summary"] = fill_llm_suggestions_template(summary, model)
    if duplicate_of:
        content["duplicate"] = duplicate_of
    text = _apply((TEMPLATE_DIR / name).read_text(encoding="utf-8"), content)
    return fill_markers(text, pmc, original, triager_name)


def fill_receipt_template(pmc, original, note, triager_name):
    """Render the reporter receipt: receipt-specialized.md for a specialized PMC,
    else receipt.md. The content (note) is filled here, the rest via
    fill_markers; an empty note drops its line."""
    name = "receipt-specialized.md" if (pmc and pmc.specialized) else "receipt.md"
    content = {"note": note} if note else {}
    text = _apply((TEMPLATE_DIR / name).read_text(encoding="utf-8"), content)
    return fill_markers(text, pmc, original, triager_name)


def fill_reject_template(pmc, original, reason, triager_name):
    """Render the reporter push-back from reject.md: the reason is filled here,
    the rest via fill_markers; an empty reason drops its line."""
    content = {"reason": reason} if reason else {}
    text = _apply((TEMPLATE_DIR / "reject.md").read_text(encoding="utf-8"), content)
    return fill_markers(text, pmc, original, triager_name)


def quote_original(original):
    """The original message quoted inline, with a forwarded-style header block.

    Shared by the reply builders that want the report visible for reference.
    """
    header_lines = [
        f"On {_header_value(original['Date'])}, {_header_value(reporter_from(original))} wrote:",
    ]
    quoted = "\n".join("> " + ln for ln in body_to_text(original).splitlines())
    return "\n".join(header_lines) + f"\n{quoted}"


# Reporters routinely Cc a project's public dev@/user@ list on their report.
# Those copies usually sit in the list's moderation queue, but mail this tool
# sends leaves through the ASF relay as security@apache.org and is NOT
# moderated - so a reply that kept the list in Cc would publish the report, and
# the team's assessment of it, straight into the public archives. Every
# recipient recognised as a public ASF list is therefore dropped from replies.
#
# Only apache.org addresses are classified: a list elsewhere cannot be
# recognised from its address alone, and our mail to it is moderated like
# anyone else's.

# The non-public lists on a project subdomain: the PMC's private list and its
# security alias.
_PRIVATE_LIST_NAMES = {"private", "security"}

# The public lists at the bare apache.org domain. Nearly everything there is
# either a committer's personal address or a private/moderated foundation list,
# so this stays an explicit allowlist - the project lists (dev@, user@,
# commits@, ...) all live on a subdomain and are caught by the rule below.
_PUBLIC_LIST_NAMES = {
    "announce",
    "builds",
    "community",
    "diversity",
    "feathercast",
    "geospacial",
    "history",
    "infrastructure-dev",
    "iot",
    "jcp-open",
    "legal-discuss",
    "license",
    "marketing",
    "mirrors",
    "privacy-commits",
    "privacy-discuss",
    "release-discuss",
    "repository",
    "retreats",
    "site-dev",
    "women",
}


def is_public_list(addr):
    """True if ``addr`` is a public ASF mailing list rather than a person.

    Addresses at any other domain are left alone: a list elsewhere is not
    recognisable from its address.
    """
    _, address = parseaddr(addr or "")
    local, _, domain = address.lower().partition("@")
    local = local.split("+", 1)[0]  # ignore any plus-addressing suffix
    if domain.endswith(".apache.org"):
        # A project subdomain carries lists only - committers' personal
        # addresses are never on one - so everything but private@/security@
        # is a public list.
        return local not in _PRIVATE_LIST_NAMES
    if domain == "apache.org":
        return local in _PUBLIC_LIST_NAMES
    return False


def without_public_lists(header_values):
    """The recipients of a header that are not public lists, as address strings
    with their display names preserved."""
    return [
        formataddr((_header_value(name), address))
        for name, address in getaddresses([v for v in header_values if v])
        if address and not is_public_list(address)
    ]


def _reply_envelope(original):
    """A reply to the reporter(s): From security@, threaded, Bcc the team.

    Any public ASF mailing list the reporter Cc'ed is dropped (see
    ``is_public_list``); the remaining Cc recipients are carried over.
    """
    msg = EmailMessage()
    msg["Message-ID"] = email.utils.make_msgid(domain="security.apache.org")
    msg["From"] = "ASF Security <security@apache.org>"
    msg["To"] = reporter_from(original)
    cc = without_public_lists(original.get_all("Cc") or [])
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Bcc"] = "ASF Security <security@apache.org>"
    subject = _header_value(original["Subject"])
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    mid = original["Message-ID"]
    if mid:
        msg["In-Reply-To"] = mid
        msg["References"] = mid
    return msg


def _set_md_body(msg, body_md):
    """Set a multipart/alternative body from a Markdown source."""
    msg.set_content(md_to_text(body_md))
    msg.add_alternative(_sanitize_html(md_to_html(body_md)), subtype="html")


def make_reject(original, body_md):
    """Build a push-back reply to the reporter(s) from a Markdown body.

    ``body_md`` is the team's note (the rendered ``reject.md`` template).
    The original report
    is appended verbatim for reference (not Markdown-rendered, since it is the
    reporter's own untrusted text).
    """
    reject = _reply_envelope(original)

    quoted = quote_original(original)
    reject.set_content(f"{md_to_text(body_md)}\n\n{quoted}")
    reject.add_alternative(
        f"{_sanitize_html(md_to_html(body_md))}<br><div>{_text_to_html(quoted)}</div>",
        subtype="html",
    )
    return reject


def make_receipt(original, body_md):
    """Build the acknowledgement to the reporter(s) from a Markdown body."""
    receipt = _reply_envelope(original)
    _set_md_body(receipt, body_md)
    return receipt


# MIME/content headers that describe the body we are about to replace, so they
# must not be carried over to the rebuilt plaintext message.
_CONTENT_HEADERS = {
    "content-type",
    "content-transfer-encoding",
    "content-disposition",
    "mime-version",
}


def edit_markdown_in_editor(md_text):
    """Open a Markdown draft body in $EDITOR and return the edited text.

    Used by the cache-driven flow: the operator edits the Markdown source and
    the message is re-rendered, so the HTML + plain-text parts stay in sync
    (unlike edit_body_in_editor, which edits the rendered plain text and drops
    the HTML alternative).
    """
    editor = getenv("EDITOR", "vi")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(md_text)
        path = f.name
    try:
        subprocess.run([editor, path])
        return Path(path).read_text(encoding="utf-8")
    finally:
        Path(path).unlink()


def edit_body_in_editor(message):
    """Edit the plaintext body (incl. the quoted forward) in $EDITOR.

    All non-content headers and any attachments are preserved; the result is a
    plaintext-only body, so editing drops any HTML alternative and inline
    images and sends plain text only.
    """
    editor = getenv("EDITOR", "vi")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(body_to_text(message))
        path = f.name
    try:
        subprocess.run([editor, path])
        edited = Path(path).read_text(encoding="utf-8")
    finally:
        Path(path).unlink()
    new = EmailMessage()
    for key, value in message.items():
        if key.lower() not in _CONTENT_HEADERS:
            new[key] = value
    new.set_content(edited)
    _copy_attachments(new, message)
    return new
