import json

from mpos import DownloadManager, TaskManager

BASE = "https://upystore.io"
ROOT = "/data/appstore-test"
revision = 1
requests = []
_original = None


def metadata(record):
    result = dict(record)
    result["download_url"] = "/api/v1/apps/%s/download?revision=%d" % (record["slug"], record["revision"])
    result["short_description"] = "Controlled on-device upgrade fixture; not a published store app"
    result["long_description"] = result["short_description"]
    result["publisher"] = "FreakStudio test fixtures"
    result["category"] = "development"
    result["activities"] = record["manifest"]["activities"]
    return result


async def download(url, *args, **kwargs):
    path, separator, query = url.partition("?")
    with open(ROOT + "/fixtures.json") as source:
        records = json.load(source)
    current = [metadata(records[key][revision - 1]) for key in ("upgrade", "peer")]
    params = dict(pair.split("=", 1) for pair in query.split("&") if "=" in pair)
    response = None
    if path == BASE + "/app_index.json":
        response = current
    elif path == BASE + "/api/v1/apps":
        search = params.get("q", "").lower()
        matching = [r for r in current if search in (r["fullname"] + " " + r["name"]).lower()]
        page = int(params.get("page", "1"))
        response = {
            "apps": matching[page - 1 : page],
            "pagination": {"total_pages": len(matching), "page": page, "total": len(matching)},
        }
    else:
        for key in ("upgrade", "peer"):
            item = records[key][revision - 1]
            route = BASE + "/api/v1/apps/" + item["slug"]
            if path == route:
                response = {"app": metadata(item), "versions": [metadata(v) for v in records[key][:revision]]}
                break
            if path == route + "/download":
                target = records[key][int(params.get("revision", str(revision))) - 1]
                print("CONTROLLED_FIXTURE_DOWNLOAD", url, target["filename"])
                requests.append(url)
                callback = kwargs.get("chunk_callback")
                with open(ROOT + "/" + target["filename"], "rb") as package:
                    if not callback:
                        return package.read()
                    while True:
                        chunk = package.read(512)
                        if not chunk:
                            break
                        await callback(chunk)
                        await TaskManager.sleep_ms(0)
                return True
    if response is not None:
        print("CONTROLLED_FIXTURE_METADATA", url)
        requests.append(url)
        await TaskManager.sleep_ms(0)
        data = json.dumps(response).encode()
        callback = kwargs.get("chunk_callback")
        if callback:
            await callback(data)
            return True
        return data
    return await _original(url, *args, **kwargs)


def install():
    global _original
    if _original is not None:
        raise RuntimeError("Fixture transport already installed")
    _original = DownloadManager.download_url
    DownloadManager.download_url = staticmethod(download)
    print("CONTROLLED_FIXTURE_TRANSPORT_INSTALLED")


def uninstall():
    global _original
    if _original is not None:
        DownloadManager.download_url = _original
        _original = None
    print("CONTROLLED_FIXTURE_TRANSPORT_REMOVED")
