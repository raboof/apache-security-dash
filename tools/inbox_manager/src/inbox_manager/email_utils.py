import re
import subprocess
import tempfile
import nh3
from datetime import date
from html import unescape
import email
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
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

    ``intro_md`` is the team's covering note as Markdown (the triage-assess
    ``draft-forward.md`` body, or the filled forward template); it is rendered
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
    quoted = "\n".join("> " + ln for ln in original_text.splitlines())
    plain_body = f"{md_to_text(intro_md)}\n\n" + "\n".join(header_lines) + f"\n{quoted}"

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


def fill_forward_template(pmc, summary, model, triager_name):
    """The templates/forward.md boilerplate with its placeholders filled in.

    With an empty ``summary`` the summary line is dropped along with the AI
    disclaimer that refers to it, so an unfilled report reads cleanly.
    """
    template = (TEMPLATE_DIR / "forward.md").read_text(encoding="utf-8")
    template = template.replace("\\<", "<")  # drop the markdown escapes on placeholders
    pmc_name = (pmc.name or pmc.id) if pmc else ""
    template = template.replace("<PMC name>", pmc_name).replace(
        "<Triager full name>", triager_name
    )
    if pmc:
        template = template.replace(
            "<dashboard link>", f"https://dash.security.apache.org/project/{pmc.id}"
        )
    else:
        template = _drop_lines(template, "<dashboard link>")
    if summary:
        return template.replace("<summary>", summary).replace("<model>", model)
    # No summary yet: drop its line and the disclaimer, then collapse the gap.
    kept = [
        ln
        for ln in template.splitlines(keepends=True)
        if "<summary>" not in ln and not ln.startswith("Disclaimer:")
    ]
    return re.sub(r"\n{3,}", "\n\n", "".join(kept))


def _drop_lines(template, placeholder):
    """Remove every line of ``template`` that still contains ``placeholder``."""
    return "".join(
        ln for ln in template.splitlines(keepends=True) if placeholder not in ln
    )


def fill_receipt_template(pmc, reporter_name, note, triager_name):
    """The templates/receipt(-specialized).md boilerplate with placeholders filled.

    A *specialized* PMC (one that runs its own security team) gets ``receipt-specialized.md``,
    which informs the reporter about the project's own ``<PMC security address>``;
    every other PMC gets ``receipt.md``.
    A security-model line is filled when the PMC has a documented security page and dropped otherwise.
    An empty ``note`` likewise drops its line. Remaining gaps are collapsed.
    """
    specialized = bool(pmc and pmc.specialized)
    name = "receipt-specialized.md" if specialized else "receipt.md"
    template = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
    template = template.replace("\\<", "<")  # drop the markdown escapes on placeholders
    template = template.replace("<Reporter name>", reporter_name).replace(
        "<Triager full name>", triager_name
    )
    if specialized:
        # specialized == pmc.security_contact is the project's own address.
        template = template.replace("<PMC name>", pmc.name or pmc.id).replace(
            "<PMC security address>", pmc.security_contact
        )
    if pmc and pmc.security_link:
        template = template.replace("<PMC name>", pmc.name or pmc.id).replace(
            "<link>", pmc.security_link
        )
    else:
        template = _drop_lines(template, "<link>")
    if note:
        template = template.replace("<note>", note)
    else:
        template = _drop_lines(template, "<note>")
    return re.sub(r"\n{3,}", "\n\n", template)


def fill_reject_template(pmc, reporter_name, triager_name):
    """The templates/reject.md boilerplate with its placeholders filled in.

    ``<model link>`` is the PMC's documented security page (the coordinates
    'link') and ``<contributing link>`` its 'contributing' field. Either is
    substituted only when the PMC has it on record; otherwise the placeholder
    is left in place so the operator fills it in when editing the reply (the
    surrounding sentence carries the reasoning, so the line is never dropped).
    """
    template = (TEMPLATE_DIR / "reject.md").read_text(encoding="utf-8")
    template = template.replace("\\<", "<")  # drop the markdown escapes on placeholders
    template = template.replace("<Reporter name>", reporter_name).replace(
        "<Triager full name>", triager_name
    )
    if pmc and pmc.security_link:
        template = template.replace("<model link>", pmc.security_link)
    if pmc and pmc.contributing:
        template = template.replace("<contributing link>", pmc.contributing)
    return template


def quote_original(original):
    """The original message quoted inline, with a forwarded-style header block.

    Shared by the reply builders that want the report visible for reference.
    """
    header_lines = [
        f"On {_header_value(original['Date'])}, {_header_value(reporter_from(original))} wrote:",
    ]
    quoted = "\n".join("> " + ln for ln in body_to_text(original).splitlines())
    return "\n".join(header_lines) + f"\n{quoted}"


def _reply_envelope(original):
    """A reply to the reporter(s): From security@, threaded, Bcc the team."""
    msg = EmailMessage()
    msg["Message-ID"] = email.utils.make_msgid(domain="security.apache.org")
    msg["From"] = "ASF Security <security@apache.org>"
    msg["To"] = reporter_from(original)
    msg["Cc"] = original["Cc"]
    msg["Bcc"] = "ASF Security <security@apache.org>"
    subject = str(original["Subject"] or "")
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


def make_reject(original, body_md, quote=True):
    """Build a push-back reply to the reporter(s) from a Markdown body.

    ``body_md`` is the team's note (the triage-assess ``draft-reply.md`` body,
    or the filled reject template). When ``quote`` is set the original report
    is appended verbatim for reference (not Markdown-rendered, since it is the
    reporter's own untrusted text).
    """
    reject = _reply_envelope(original)
    if quote:
        quoted = quote_original(original)
        reject.set_content(f"{md_to_text(body_md)}\n\n{quoted}")
        reject.add_alternative(
            f"{_sanitize_html(md_to_html(body_md))}"
            f"<br><div>{_text_to_html(quoted)}</div>",
            subtype="html",
        )
    else:
        _set_md_body(reject, body_md)
    return reject


def make_receipt(original, body_md):
    """Build the acknowledgement to the reporter(s) from a Markdown body."""
    receipt = _reply_envelope(original)
    _set_md_body(receipt, body_md)
    return receipt


def fill_draft_placeholders(body, pmc):
    """Fill the placeholders triage-assess leaves for the sender to resolve.

    ``draft.py`` renders the team templates but cannot fill ``<dashboard link>``
    (the per-PMC dashboard URL) or the receipt's ``<link>`` (the PMC security
    page); inbox_manager has the PMC from Whimsy, so it fills them here. The
    placeholders survive in the draft markdown-escaped as ``\\<...>``. Any
    placeholder still unfilled (no PMC, or no security page) has its whole line
    dropped so no raw ``<...>`` leaks into the sent mail.
    """
    if pmc:
        dash = f"https://dash.security.apache.org/project/{pmc.id}"
        body = body.replace("\\<dashboard link>", dash).replace(
            "<dashboard link>", dash
        )
        if pmc.security_link:
            body = body.replace("\\<link>", pmc.security_link).replace(
                "<link>", pmc.security_link
            )
    if "<dashboard link>" in body or "<link>" in body:
        body = "".join(
            ln
            for ln in body.splitlines(keepends=True)
            if "<dashboard link>" not in ln and "<link>" not in ln
        )
    return re.sub(r"\n{3,}", "\n\n", body)


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
