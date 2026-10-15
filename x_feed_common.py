
import hashlib
import json
import os
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

API_BASE = "https://api.x.com/2"
TOKEN = os.getenv("X_BEARER_TOKEN", "").strip()
USER_CACHE_FILE = Path("x_user_ids.json")
DISCORD_QUEUE_FILE = Path("x_recent_posts.json")
POST_CACHE_FILE = Path("x_posts_cache.json")
LAST_POSTS_FILE = Path("last_posts.json")
START_IDS_FILE = Path("x_discord_start_ids.json")
QUEUE_BACKUP_FILE = Path("x_recent_posts_before_safe_restart.json")
TIMEOUT = 30
MAX_RSS_POSTS = 3

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "GitHubActions-X-RSS-Bot/1.0",
}


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path, data):
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def request_json(url, params=None):
    if not TOKEN:
        raise RuntimeError(
            "X_BEARER_TOKEN fehlt. GitHub-Secret überprüfen."
        )

    response = requests.get(
        url, headers=HEADERS, params=params, timeout=TIMEOUT
    )

    if response.status_code == 401:
        raise RuntimeError("X API 401: Bearer Token überprüfen.")
    if response.status_code == 403:
        raise RuntimeError(
            "X API 403: API-Zugriff und Berechtigungen überprüfen."
        )
    if response.status_code == 429:
        raise RuntimeError(
            "X API 429: Rate Limit erreicht. Später erneut versuchen."
        )

    response.raise_for_status()
    result = response.json()

    if result.get("errors") and not result.get("data"):
        raise RuntimeError(f"X API Fehler: {result['errors']}")

    return result


def get_user_id(username):
    cache = load_json(USER_CACHE_FILE, {})
    key = username.lower()

    if cache.get(key):
        return str(cache[key])

    result = request_json(
        f"{API_BASE}/users/by/username/{username}"
    )
    user = result.get("data") or {}

    if not user.get("id"):
        raise RuntimeError(f"X-Konto @{username} nicht gefunden.")

    cache[key] = str(user["id"])
    save_json(USER_CACHE_FILE, cache)

    print(f"User-ID für @{username} gespeichert.")
    return str(user["id"])

def get_last_sent_id(username):
    state = load_json(LAST_POSTS_FILE, {})
    ids = state.get(username.lower(), [])

    if not isinstance(ids, list):
        return None

    numeric_ids = [
        int(post_id)
        for post_id in ids
        if str(post_id).isdigit()
    ]

    return str(max(numeric_ids)) if numeric_ids else None

def parse_created_at(value):
    if not value:
        return datetime.now(timezone.utc)

    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    ).astimezone(timezone.utc)


def fetch_posts(username):
    user_id = get_user_id(username)

    post_cache = load_json(POST_CACHE_FILE, {})
    cached_posts = post_cache.get(username.lower(), [])
    
    cached_ids = [
        int(post["id"])
        for post in cached_posts
        if str(post.get("id", "")).isdigit()
    ]
    
    last_cached_id = str(max(cached_ids)) if cached_ids else None
    
    params = {
        "max_results": 100,
        "exclude": "replies",
        "tweet.fields": (
            "created_at,referenced_tweets,attachments,author_id"
        ),
        "expansions": (
            "attachments.media_keys,"
            "referenced_tweets.id,"
            "referenced_tweets.id.author_id"
        ),
        "media.fields": (
            "media_key,type,url,preview_image_url,alt_text"
        ),
        "user.fields": "username,name",
    }

    if last_cached_id:
        params["since_id"] = last_cached_id
        print(
            f"@{username}: Suche nach neuen Posts seit "
            f"{last_cached_id}."
        )
    else:
        print(
            f"@{username}: Noch kein Cache vorhanden. "
            "Initialer Abruf."
        )
    
    result = request_json(
        f"{API_BASE}/users/{user_id}/tweets", params
    )

    included = result.get("includes") or {}
    tweets_by_id = {
        str(t["id"]): t
        for t in included.get("tweets", [])
        if t.get("id")
    }
    media_by_key = {
        m["media_key"]: m
        for m in included.get("media", [])
        if m.get("media_key")
    }
    users_by_id = {
        str(u["id"]): u
        for u in included.get("users", [])
        if u.get("id")
    }

    normalized = []

    for post in result.get("data") or []:
        post_id = str(post.get("id", ""))
        if not post_id:
            continue

        refs = post.get("referenced_tweets") or []
        ref_types = {r.get("type") for r in refs}

        is_repost = "retweeted" in ref_types
        is_quote = "quoted" in ref_types

        referenced = {}
        for ref in refs:
            if ref.get("type") in ("retweeted", "quoted"):
                referenced = tweets_by_id.get(str(ref.get("id")), {})
                if referenced:
                    break

        author_id = str(referenced.get("author_id", ""))
        original_username = (
            users_by_id.get(author_id) or {}
        ).get("username", "")

        own_text = (post.get("text") or "").strip()
        original_text = (referenced.get("text") or "").strip()

        if is_repost:
            author = f"@{original_username}" if original_username else "Original-Post"
            text = (
                f"🔁 Repost von {author}\n\n"
                f"{original_text or own_text}"
            )
        elif is_quote:
            text = own_text
            if original_text:
                author = (
                    f"@{original_username}"
                    if original_username
                    else "Original-Post"
                )
                text += (
                    f"\n\n──────────────\n"
                    f"Zitat von {author}:\n{original_text}"
                )
            else:
                text = "🗨️ Zitierter Post\n\n" + text
        else:
            text = own_text


        media_urls = []
        candidates = [post]

        # Medien des eigenen Posts und des referenzierten Posts sammeln.
        if referenced:
            candidates.append(referenced)

        for candidate in candidates:
            attachments = candidate.get("attachments") or {}
            for media_key in attachments.get("media_keys", []):
                media = media_by_key.get(media_key) or {}
                url = media.get("url") or media.get("preview_image_url")
                if url and url not in media_urls:
                    media_urls.append(url)

        # Wenn beim Repost keine Bilder gefunden wurden,
        # die Daten des Originalposts direkt bei X abrufen.
        if referenced and not media_urls:
            referenced_id = str(referenced.get("id", ""))
            if referenced_id:
                try:
                    detail = request_json(
                        f"{API_BASE}/tweets/{referenced_id}",
                        {
                            "tweet.fields": "attachments",
                            "expansions": "attachments.media_keys",
                            "media.fields": (
                                "media_key,type,url,preview_image_url,alt_text"
                            ),
                        },
                    )

                    detail_post = detail.get("data") or {}
                    detail_includes = detail.get("includes") or {}
                    detail_media = {
                        m["media_key"]: m
                        for m in detail_includes.get("media", [])
                        if m.get("media_key")
                    }

                    for media_key in (
                        (detail_post.get("attachments") or {}).get(
                            "media_keys", []
                        )
                    ):
                        media = detail_media.get(media_key) or {}
                        url = (
                            media.get("url")
                            or media.get("preview_image_url")
                        )
                        if url and url not in media_urls:
                            media_urls.append(url)

                except requests.RequestException as exc:
                    print(
                        "Medien des Originalposts konnten nicht "
                        f"abgerufen werden: {exc}"
                    )


        normalized.append({
            "id": post_id,
            "text": text,
            "created_at": parse_created_at(
                post.get("created_at")
            ).isoformat(),
            "url": f"https://x.com/{username}/status/{post_id}",
            "media_urls": media_urls,
            "is_repost": is_repost,
            "is_quote": is_quote,
        })

    normalized.sort(
        key=lambda p: p["created_at"], reverse=True
    )
    
    # Neue und bereits gespeicherte Posts zusammenführen.
    merged = {
        str(post["id"]): post
        for post in cached_posts
        if post.get("id")
    }
    
    for post in normalized:
        merged[str(post["id"])] = post
    
    all_posts = sorted(
        merged.values(),
        key=lambda p: p["created_at"],
        reverse=True,
    )
    
    # Cache begrenzen, damit die Datei nicht unbegrenzt wächst.
    all_posts = all_posts[:500]
    
    post_cache[username.lower()] = all_posts
    save_json(POST_CACHE_FILE, post_cache)
    
    print(
        f"@{username}: {len(normalized)} neue API-Ergebnisse, "
        f"{len(all_posts)} Posts im Cache."
    )
    
    return all_posts



def download_image(url, post_id, index, image_dir):
    image_dir = Path(image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)

    suffix = "" if index == 0 else f"_{index + 1}"

    # Die üblichen Dateiendungen prüfen, ohne X erneut anzufragen.
    for ext in (".jpg", ".png", ".webp", ".gif"):
        target = image_dir / f"{post_id}{suffix}{ext}"
        if target.is_file() and target.stat().st_size > 0:
            return target

    try:
        response = requests.get(
            url,
            headers={"User-Agent": HEADERS["User-Agent"]},
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        content = response.content
        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if "png" in content_type:
            ext = ".png"
        elif "webp" in content_type:
            ext = ".webp"
        elif "gif" in content_type:
            ext = ".gif"
        else:
            ext = ".jpg"

        target = image_dir / f"{post_id}{suffix}{ext}"
        target.write_bytes(content)
        return target

    except requests.RequestException as exc:
        print(f"Bild konnte nicht geladen werden: {exc}")
        return None



def create_rss_feed(
    username, posts, feed_file, image_dir, public_image_path
):
    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:media": "http://search.yahoo.com/mrss/",
        },
    )
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = f"X-Posts von @{username}"
    ET.SubElement(channel, "link").text = f"https://x.com/{username}"
    ET.SubElement(channel, "description").text = (
        f"RSS-Feed für @{username}"
    )
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(
        datetime.now(timezone.utc), usegmt=True
    )

    for post in posts[:MAX_RSS_POSTS]:
        item = ET.SubElement(channel, "item")

        title = re.sub(r"\s+", " ", post["text"]).strip()[:300]
        ET.SubElement(item, "title").text = title or "Neuer X-Beitrag"
        ET.SubElement(item, "description").text = post["text"]
        ET.SubElement(item, "link").text = post["url"]
        ET.SubElement(
            item, "guid", {"isPermaLink": "false"}
        ).text = post["id"]
        ET.SubElement(item, "pubDate").text = format_datetime(
            parse_created_at(post["created_at"]), usegmt=True
        )

        for index, image_url in enumerate(post["media_urls"]):
            image = download_image(
                image_url, post["id"], index, image_dir
            )
            if image is None:
                continue

            public_url = (
                f"{public_image_path.rstrip('/')}/{image.name}"
            )

            if image.suffix.lower() == ".png":
                content_type = "image/png"
            elif image.suffix.lower() == ".webp":
                content_type = "image/webp"
            elif image.suffix.lower() == ".gif":
                content_type = "image/gif"
            else:
                content_type = "image/jpeg"

            ET.SubElement(
                item,
                "enclosure",
                {
                    "url": public_url,
                    "type": content_type,
                    "length": str(image.stat().st_size),
                },
            )
            ET.SubElement(
                item,
                "{http://search.yahoo.com/mrss/}content",
                {
                    "url": public_url,
                    "medium": "image",
                    "type": content_type,
                },
            )

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(
        feed_file, encoding="utf-8", xml_declaration=True
    )

    print(
        f"{feed_file}: {min(len(posts), MAX_RSS_POSTS)} RSS-Beiträge gespeichert."
    )





def run_account(
    username, output_file, image_dir, public_image_base
):
    account_key = username.lower()
    public_base = public_image_base.rstrip("/")

    # Vor dem API-Abruf den vorhandenen Cache lesen.
    # So zählen neu eintreffende Beiträge nicht versehentlich
    # zum Ausgangsbestand.
    post_cache = load_json(POST_CACHE_FILE, {})
    if not isinstance(post_cache, dict):
        post_cache = {}

    cached_posts = post_cache.get(account_key, [])
    if not isinstance(cached_posts, list):
        cached_posts = []

    cached_ids = [
        int(post["id"])
        for post in cached_posts
        if isinstance(post, dict)
        and str(post.get("id", "")).isdigit()
    ]

    # Startgrenze laden oder sicher initialisieren.
    start_ids = load_json(START_IDS_FILE, {})
    if not isinstance(start_ids, dict):
        start_ids = {}

    if account_key not in start_ids:
        if not cached_ids:
            raise RuntimeError(
                f"Kein vorhandener Post-Cache für @{username}. "
                "Sicherer Neustart abgebrochen. "
                "Start-ID zuerst manuell festlegen."
            )

        start_ids[account_key] = str(max(cached_ids))
        save_json(START_IDS_FILE, start_ids)

        print(
            f"🔒 Startgrenze für @{username}: "
            f"{start_ids[account_key]}"
        )

    start_id = int(start_ids[account_key])

    # Alte Warteschlange vor der ersten Änderung sichern.
    queue = load_json(DISCORD_QUEUE_FILE, {})
    if not isinstance(queue, dict):
        queue = {}

    if not QUEUE_BACKUP_FILE.exists():
        save_json(QUEUE_BACKUP_FILE, queue)
        print(f"🛟 Alte Warteschlange gesichert: {QUEUE_BACKUP_FILE}")

    # Erst nach Festlegung der Startgrenze neue Beiträge abrufen.
    posts = fetch_posts(username)

    queue_posts = []

    for post in posts:
        post_id = str(post.get("id", "")).strip()

        if not post_id.isdigit():
            continue

        # Keine Beiträge aus dem bisherigen Bestand nachsenden.
        if int(post_id) <= start_id:
            continue

        local_images = []

        for index, image_url in enumerate(post.get("media_urls", [])):
            image = download_image(
                image_url, post_id, index, image_dir
            )
            if image:
                local_images.append({
                    "path": str(image),
                    "url": f"{public_base}/{image.name}",
                })

        queue_posts.append({
            "id": post_id,
            "text": post.get("text", ""),
            "created_at": post.get("created_at", ""),
            "url": post.get("url", ""),
            "images": local_images,
            "is_repost": post.get("is_repost", False),
            "is_quote": post.get("is_quote", False),
        })

    queue_posts.sort(
        key=lambda item: int(item["id"]),
        reverse=True,
    )

    # Nur neue Beiträge in die aktive Discord-Warteschlange.
    queue[account_key] = queue_posts
    save_json(DISCORD_QUEUE_FILE, queue)

    print(
        f"📬 @{username}: {len(queue_posts)} Beiträge "
        f"nach der Startgrenze in der Warteschlange."
    )

    create_rss_feed(
        username,
        posts,
        output_file,
        image_dir,
        public_base,
    )
