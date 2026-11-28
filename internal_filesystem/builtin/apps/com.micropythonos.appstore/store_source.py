import gc
import json
import logging

from mpos import BuildInfo, DownloadManager, SharedPreferences, TaskManager

logger = logging.getLogger(__name__)
BASE_URL = "https://upystore.io"
DEFAULT_SOURCE = "badgehub"
_REQUESTS = []

BADGEHUB_INDEX = "https://badgehub.eu/api/v3/project-summaries?badge=mpos_api_%s" % BuildInfo.version.api_level


def current_source():
    value = SharedPreferences("com.micropythonos.appstore").get_string("store_source", DEFAULT_SOURCE)
    return value if value in ("upystore", "badgehub") else DEFAULT_SOURCE


def index_url(source=None):
    return BASE_URL + "/app_index.json" if (source or current_source()) == "upystore" else BADGEHUB_INDEX


def absolute_url(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Missing store URL")
    if value.startswith("/") and not value.startswith("//"):
        return BASE_URL + value
    if value.startswith(BASE_URL + "/"):
        return value
    raise ValueError("Only HTTPS upystore.io URLs are accepted")


def identity(value):
    if not isinstance(value, str) or not value or len(value) > 120:
        raise ValueError("Invalid application identity")
    if any(not part for part in value.split(".")) or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in value
    ):
        raise ValueError("Invalid application identity")
    return value


def quote(value):
    return "".join(
        chr(c) if chr(c) in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.~" else "%%%02X" % c
        for c in value.encode("utf-8")
    )


def normalize(value, source):
    if source == "badgehub":
        result = dict(value)
        result["_store_source"] = source
        result["_store_slug"] = value.get("slug")
        return result
    fullname = identity(value.get("fullname"))
    download = value.get("download_url")
    slug = value.get("slug")
    if not slug and download and "/api/v1/apps/" in download:
        slug = download.split("/api/v1/apps/", 1)[1].split("/", 1)[0]
    if not slug:
        raise ValueError("Missing application URL slug")
    identity(slug)
    icon = value.get("icon_url")
    return {
        "name": value.get("name", fullname),
        "slug": fullname,
        "fullname": fullname,
        "_store_slug": slug,
        "_store_source": source,
        "description": value.get("short_description") or value.get("description") or "",
        "long_description": value.get("long_description") or "",
        "publisher": value.get("publisher"),
        "version": value.get("version"),
        "revision": value.get("revision"),
        "categories": value.get("category") or value.get("categories") or [],
        "icon_map": {"64x64": {"url": absolute_url(icon)}} if icon else {},
        "download_url": absolute_url(download) if download else None,
        "min_os_version": value.get("min_os_version"),
        "min_api_level": value.get("min_api_level"),
        "activities": value.get("activities", []),
        "ratings": {},
    }


def error_text(error):
    if type(error).__name__ == "IndexError":
        return "Invalid response from store"
    return str(error).strip() or type(error).__name__


async def request(url, timeout=35, **kwargs):
    ticket = object()
    _REQUESTS.append(ticket)

    async def wait_turn():
        while _REQUESTS[0] is not ticket:
            await TaskManager.sleep_ms(10)

    try:
        await TaskManager.wait_for(wait_turn(), 120)
        return await TaskManager.wait_for(DownloadManager.download_url(url, **kwargs), timeout)
    except Exception as error:
        logger.warning("APPSTORE_HTTP_FAILED %s %s %s", url, type(error).__name__, str(error))
        raise
    finally:
        _REQUESTS.remove(ticket)


async def json_get(url, limit=2097152):
    if __debug__: logger.debug("APPSTORE_SOURCE_REQUEST %s", url)
    if url.startswith(BASE_URL + "/"):
        response = bytearray()

        async def collect(chunk):
            if len(response) + len(chunk) > limit:
                raise ValueError("Invalid or oversized store response")
            response.extend(chunk)
            await TaskManager.sleep_ms(0)

        ok = await request(url, timeout=120 if url.endswith("/app_index.json") else 35, chunk_callback=collect)
        if not ok:
            raise RuntimeError("Store request failed")
    else:
        response = await request(url)
    if not response or len(response) > limit:
        raise ValueError("Invalid or oversized store response")
    value = json.loads(response)
    response = None
    gc.collect()
    return value


async def fetch_index(url=None, query=None):
    source = ("upystore" if url.startswith(BASE_URL + "/") else "badgehub") if url else current_source()
    prefs = SharedPreferences("com.micropythonos.appstore")
    query = (prefs.get_string("store_query", "") or "") if query is None else query
    if source == "upystore" and query:
        return await list_apps(query=query)
    data = await json_get(url or index_url(source))
    if not isinstance(data, list):
        raise ValueError("Invalid store catalog")
    values = [normalize(row, source) for row in data]
    data = None
    gc.collect()
    if source == "badgehub" and query:
        values = [
            row for row in values if query.lower() in (row.get("name", "") + " " + row.get("description", "")).lower()
        ]
    return values


async def fetch_updates(url=None):
    source = ("upystore" if url.startswith(BASE_URL + "/") else "badgehub") if url else current_source()
    if source == "upystore":
        return await list_apps()
    return await fetch_index(url, query="")


async def list_apps(query="", category=None):
    results = []
    page = 1
    while page <= 100:
        url = BASE_URL + "/api/v1/apps?limit=100&page=%d&q=%s" % (page, quote(query))
        if category:
            url += "&category=" + quote(category)
        data = await json_get(url)
        if not isinstance(data, dict) or not isinstance(data.get("apps"), list):
            raise ValueError("Invalid application list")
        results.extend(normalize(row, "upystore") for row in data["apps"])
        pages = data.get("pagination", {}).get("total_pages", 1)
        data = None
        gc.collect()
        if page >= pages:
            return results
        page += 1
        await TaskManager.sleep_ms(0)
    raise ValueError("Store list exceeds pagination limit")


async def fetch_details(fullname, slug=None, source=None):
    source = source or current_source()
    identity(fullname)
    if source == "badgehub":
        from appstore_core import fetch_badgehub_project_details

        result = await fetch_badgehub_project_details("https://badgehub.eu/api/v3/projects/" + fullname)
        result["_store_source"] = source
        result["fullname"] = fullname
        return result
    if not slug:
        candidates = await list_apps(query=fullname)
        match = next((row for row in candidates if row["fullname"] == fullname), None)
        if match is None:
            raise ValueError("Application is not in this store")
        slug = match["_store_slug"]
    identity(slug)
    data = await json_get(BASE_URL + "/api/v1/apps/" + slug)
    app = data.get("app")
    versions = data.get("versions")
    if not isinstance(app, dict) or app.get("fullname") != fullname or not isinstance(versions, list):
        raise ValueError("Invalid app detail identity or versions")
    revision = app.get("revision")
    version = next((v for v in versions if v.get("revision") == revision), None)
    if not version:
        raise ValueError("Published revision unavailable")
    if version.get("version") and version["version"] != app.get("version"):
        raise ValueError("Published version mismatch")
    return {
        "fullname": fullname,
        "version": app.get("version"),
        "revision": revision,
        "publisher": app.get("publisher"),
        "long_description": app.get("long_description") or app.get("short_description") or "",
        "download_url": absolute_url(version.get("download_url") or app.get("download_url")),
        "download_url_size": version.get("file_size_bytes"),
        "file_sha256": version.get("file_sha256"),
        "min_os_version": app.get("min_os_version"),
        "min_api_level": app.get("min_api_level"),
        "_store_source": source,
        "_store_slug": slug,
        "versions": versions,
    }


def attach(app, row):
    app._store_source = row.get("_store_source", current_source())
    app._store_slug = row.get("_store_slug")
    app._remote_version = row.get("version")
    if row.get("revision") is not None:
        app.revision = row["revision"]
    if row.get("download_url"):
        app.download_url = row["download_url"]
    if row.get("publisher"):
        app.publisher = row["publisher"]
    return app
