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


def make_forward(original, intro_text, from_addr, to_addr):
    """Forward `original` (parsed with policy=default), quoting it inline,
    hardened against hostile content in the forwarded message.
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

    # --- plain-text body (always built) ---
    original_text = body_to_text(original)
    quoted = "\n".join("> " + ln for ln in original_text.splitlines())
    plain_body = f"{intro_text}\n\n" + "\n".join(header_lines) + f"\n{quoted}"

    # --- plain-text-only original ---
    if html_part is None:
        fwd.set_content(plain_body)
    else:
        # --- original had HTML: sanitise, then emit dual plain + html ---
        clean_html = _sanitize_html(html_part.get_content())
        header_html = _text_to_html("\n".join(header_lines))
        intro_block = _text_to_html(intro_text)
        html_body = (
            f"<div>{intro_block}</div><br>"
            f"<div>{header_html}</div>"
            f'<blockquote style="margin:0 0 0 .8ex;border-left:2px solid #ccc;padding-left:1ex">'
            f"{clean_html}"
            f"</blockquote>"
        )

        fwd.set_content(plain_body)
        fwd.add_alternative(html_body, subtype="html")

        html_alt = fwd.get_payload()[1]
        for cid, data, subtype in _safe_inline_images(original, clean_html):
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
    """The templates/receipt.md boilerplate with its placeholders filled in.

    The security-model line is filled when the PMC has a documented security
    page, otherwise that whole line is dropped. An empty ``note`` likewise
    drops its line. Remaining gaps are collapsed.
    """
    template = (TEMPLATE_DIR / "receipt.md").read_text(encoding="utf-8")
    template = template.replace("\\<", "<")  # drop the markdown escapes on placeholders
    template = template.replace("<Reporter name>", reporter_name).replace(
        "<Triager full name>", triager_name
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


def make_reject(original, pmc, triager_name):
    """Build a rejection reply to the reporter(s) of `original`.

    From security@apache.org, To the original reporter(s), threaded onto the
    report and Bcc'ing the Security team, with the report quoted inline for
    reference. The body is templates/reject.md - it carries placeholders and
    "...." gaps the operator is expected to fill in by editing the reply.
    """
    reporter = reporter_from(original)
    name, addr = parseaddr(reporter or "")
    body = fill_reject_template(pmc, name or addr, triager_name)
    body = f"{body}\n\n{quote_original(original)}"

    reject = EmailMessage()
    reject["Message-ID"] = email.utils.make_msgid(domain="security.apache.org")
    reject["From"] = "ASF Security <security@apache.org>"
    reject["To"] = reporter
    reject["Cc"] = original["Cc"]
    reject["Bcc"] = "ASF Security <security@apache.org>"
    subject = str(original["Subject"] or "")
    reject["Subject"] = (
        subject if subject.lower().startswith("re:") else f"Re: {subject}"
    )
    mid = original["Message-ID"]
    if mid:
        reject["In-Reply-To"] = mid
        reject["References"] = mid
    reject.set_content(body)
    return reject


def make_receipt(original, pmc, triager_name):
    """Build the acknowledgement sent back to the reporter(s) of `original`.

    From security@apache.org, To the original reporter(s), Bcc'ing the Security
    team, threaded onto the report.
    """
    reporter = reporter_from(original)
    name, addr = parseaddr(reporter or "")
    # TODO: pick up the note from the triage-assess skill's output when
    # available; for now it is left empty.
    body = fill_receipt_template(pmc, name or addr, "", triager_name)

    receipt = EmailMessage()
    receipt["Message-ID"] = email.utils.make_msgid(domain="security.apache.org")
    receipt["From"] = "ASF Security <security@apache.org>"
    receipt["To"] = reporter
    receipt["Cc"] = original["Cc"]
    receipt["Bcc"] = "ASF Security <security@apache.org>"
    subject = str(original["Subject"] or "")
    receipt["Subject"] = (
        subject if subject.lower().startswith("re:") else f"Re: {subject}"
    )
    mid = original["Message-ID"]
    if mid:
        receipt["In-Reply-To"] = mid
        receipt["References"] = mid
    receipt.set_content(body)
    return receipt


# MIME/content headers that describe the body we are about to replace, so they
# must not be carried over to the rebuilt plaintext message.
_CONTENT_HEADERS = {
    "content-type",
    "content-transfer-encoding",
    "content-disposition",
    "mime-version",
}


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
