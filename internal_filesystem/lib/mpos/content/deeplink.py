"""App-link (deep link) parsing and dispatch.

This module implements the QR-code app discovery link format:

    https://badgehub.eu/page/project/<app_id>[?v=<min_version>&s=<source>]
    https://badgehub.eu/<app_id>[?...]           (shorthand)
    micropythonos://app/<app_id>[?...]           (accepted alias, never emitted)
    mpos://app/<app_id>[?...]                    (short form of the alias)

All parts of a link are case-insensitive (QR alphanumeric mode uppercases
the whole payload), so MPOS://APP/COM.EXAMPLE.PAINT works too.

The link carries the app's *identity* only, never a download location: the
AppStore resolves the app_id against the catalog it already trusts, so a
hostile QR code can at worst point at an app that legitimately exists there.

Third-party apps can declare their own URL handlers in MANIFEST.JSON via a
"urlPattern" entry in an activity's intent_filters, e.g.:

    {"action": "view_url", "urlPattern": "https://store.acme.example/app/*"}

Patterns matching the official store host or the micropythonos:// / mpos:// schemes are
reserved for the system and rejected at registration time.

No LVGL or hardware dependencies at module level: everything heavy is
imported lazily inside open_url() so the parser stays desktop-testable.
"""

import logging

logger = logging.getLogger(__name__)

MAX_URL_LENGTH = 512
MAX_APP_ID_LENGTH = 64
MAX_PARAM_LENGTH = 64

STORE_HOSTS = ("badgehub.eu",)
STORE_SCHEMES = ("micropythonos", "mpos")
APPSTORE_FULLNAME = "com.micropythonos.appstore"

# Action carried by intents dispatched to third-party URL handlers.
ACTION_VIEW_URL = "view_url"

_APP_ID_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789._-"
_SCHEME_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789+.-"


def split_url(text):
    """Split a URL into (scheme, host, path, query) with strict validation.

    Returns None instead of raising on anything malformed. The scheme and
    host are folded to lowercase (QR codes encoded in alphanumeric mode are
    all-uppercase). The fragment, if any, is discarded. Hosts containing
    userinfo ("@") or a port (":") are rejected outright so look-alike
    tricks like "apps.micropythonos.com@evil.example" cannot parse.
    """
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text or len(text) > MAX_URL_LENGTH:
        return None
    sep = text.find("://")
    if sep <= 0:
        return None
    scheme = text[:sep].lower()
    for c in scheme:
        if c not in _SCHEME_CHARS:
            return None
    rest = text[sep + 3:]
    frag = rest.find("#")
    if frag != -1:
        rest = rest[:frag]
    query = ""
    qmark = rest.find("?")
    if qmark != -1:
        query = rest[qmark + 1:]
        rest = rest[:qmark]
    slash = rest.find("/")
    if slash == -1:
        host = rest
        path = ""
    else:
        host = rest[:slash]
        path = rest[slash:]
    host = host.lower()
    if not host or "@" in host or ":" in host or "*" in host:
        return None
    return (scheme, host, path, query)


def _parse_query(query):
    """Parse a query string into a dict; malformed pairs are skipped."""
    params = {}
    if not query:
        return params
    for pair in query.split("&"):
        eq = pair.find("=")
        if eq <= 0:
            continue
        key = pair[:eq]
        value = pair[eq + 1:]
        if len(value) > MAX_PARAM_LENGTH:
            continue
        params[key] = value
    return params


def _valid_app_id(app_id):
    if not app_id or len(app_id) > MAX_APP_ID_LENGTH:
        return False
    for c in app_id:
        if c not in _APP_ID_CHARS:
            return False
    return True


def _valid_version(version):
    if not version:
        return False
    for c in version:
        if c not in "0123456789.":
            return False
    return True


def parse_store_link(text):
    """Parse an official app-store link.

    Returns {"fullname": ..., "min_version": ... or None, "source": ... or None}
    for a valid link, None for everything else. Accepts the canonical BadgeHub
    https forms and the micropythonos:// or mpos:// alias. The app id is folded
    to lowercase (store app ids are lowercase by convention; QR alphanumeric
    mode uppercases everything).
    """
    parts = split_url(text)
    if not parts:
        return None
    scheme, host, path, query = parts
    if scheme == "https":
        if host not in STORE_HOSTS:
            return None
        # Case-insensitive prefix: QR alphanumeric mode uppercases the path too.
        path_prefix = path[:14].lower()
        if path_prefix == "/page/project/":
            app_id = path[14:]
        elif path.startswith("/") and path.count("/") == 1:
            app_id = path[1:]
        else:
            return None
    elif scheme in STORE_SCHEMES:
        # micropythonos://app/<id> parses as host="app", path="/<id>"
        if host != "app":
            return None
        app_id = path[1:] if path.startswith("/") else path
    else:
        return None
    app_id = app_id.lower()
    if "/" in app_id or not _valid_app_id(app_id):
        return None
    params = _parse_query(query)
    min_version = params.get("v")
    if min_version is not None and not _valid_version(min_version):
        min_version = None
    return {
        "fullname": app_id,
        "min_version": min_version,
        "source": params.get("s"),
    }


def validate_handler_pattern(pattern):
    """Validate a manifest urlPattern. Returns an error string, or None if OK.

    Rules: the pattern must parse as scheme://host/... with a literal host,
    a "*" wildcard is only allowed as the final character, and patterns
    that could match official store links (the store hosts or the
    micropythonos:// / mpos:// schemes) are reserved for the system.
    """
    if not isinstance(pattern, str) or not pattern or len(pattern) > MAX_URL_LENGTH:
        return "pattern missing or too long"
    star = pattern.find("*")
    if star != -1 and star != len(pattern) - 1:
        return "wildcard '*' is only allowed as the final character"
    literal = pattern[:-1] if pattern.endswith("*") else pattern
    parts = split_url(literal)
    if not parts:
        return "pattern must look like scheme://host/..."
    scheme, host, path, query = parts
    if query:
        return "pattern must not contain a query string"
    if scheme in STORE_SCHEMES:
        return "the %s:// scheme is reserved for the system" % scheme
    if host in STORE_HOSTS:
        return "host %s is reserved for the system" % host
    if pattern.endswith("*") and not path:
        return "wildcard requires at least scheme://host/"
    return None


def url_matches_pattern(pattern, url):
    """Check whether a URL matches a (validated) handler pattern.

    Matching is a case-insensitive-scheme-and-host prefix match; a trailing
    "*" in the pattern matches any suffix, otherwise the match is exact.
    """
    parts = split_url(url)
    if not parts:
        return False
    scheme, host, path, query = parts
    normalized = scheme + "://" + host + path
    if pattern.endswith("*"):
        prefix = pattern[:-1]
        # Fold the scheme://host portion of the pattern like split_url does.
        sep = prefix.find("://")
        if sep <= 0:
            return False
        slash = prefix.find("/", sep + 3)
        if slash == -1:
            prefix = prefix.lower()
        else:
            prefix = prefix[:slash].lower() + prefix[slash:]
        return normalized.startswith(prefix)
    pparts = split_url(pattern)
    if not pparts:
        return False
    pscheme, phost, ppath, pquery = pparts
    return scheme == pscheme and host == phost and path == ppath


def open_action_label(text):
    """Return a short action label if text is an app link the OS can open.

    Used by QR scanners (e.g. the Camera app) to decide whether to offer an
    "open" chip for a decoded code. Returns None for anything that no
    handler would accept, "Open in App Store" for official store links, and
    "Open link" when an installed app's urlPattern matches.
    """
    if parse_store_link(text):
        return "Open in App Store"
    if not isinstance(text, str):
        return None
    from .app_manager import AppManager
    if AppManager.resolve_url_handlers(text):
        return "Open link"
    return None


def open_url(text):
    """Dispatch a URL (e.g. decoded from a QR code) to its handler.

    Official store links open the AppStore on the linked app. Other URLs
    are offered to third-party handlers declared via manifest urlPattern
    entries: one match dispatches directly, several open the chooser.
    Returns True if something handled the URL, False otherwise. The text
    is treated strictly as data — it is never fetched or evaluated here.
    """
    from .app_manager import AppManager
    from .intent import Intent

    link = parse_store_link(text)
    if link:
        if __debug__: logger.debug("store link for app %s", link["fullname"])
        intent = Intent(extras={
            "deeplink_fullname": link["fullname"],
            "deeplink_min_version": link["min_version"],
        })
        return AppManager.start_app(APPSTORE_FULLNAME, intent=intent)

    handlers = AppManager.resolve_url_handlers(text)
    if not handlers:
        if __debug__: logger.debug("no handler for URL")
        return False
    from mpos.activity_navigator import ActivityNavigator
    intent = Intent(action=ACTION_VIEW_URL, data=text)
    if len(handlers) == 1:
        ActivityNavigator._dispatch(intent, handlers[0])
    else:
        # No sticky default on purpose: a later-installed app must not be
        # permanently shadowed by whichever registered first.
        ActivityNavigator._show_chooser(intent, handlers)
    return True
