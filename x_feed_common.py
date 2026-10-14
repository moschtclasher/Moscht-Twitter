
import os
import json
import time
import html
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone
from email.utils import format_datetime

API_BASE = "https://api.x.com/2"
BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN", "").strip()
CACHE_FILE = Path("x_user_ids.json")
STATE_FILE = Path("x_seen_posts.json")
MAX_POSTS = 3

if not BEARER_TOKEN:
    raise RuntimeError(
        "Der GitHub-Secret X_BEARER_TOKEN ist nicht gesetzt."
    )

SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "User-Agent": "X-to-RSS-Bot/1.0",
})


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def api_get(url, params=None):
    response = SESSION.get(url, params=params, timeout=30)

    if response.status_code == 429:
        raise RuntimeError(
            "X-API-Limit erreicht. Bitte später erneut versuchen."
        )

    response.raise_for_status()
    return response.json()


def get_user_id(username, user_ids):
    if username in user_ids:
        return user_ids[username]

    data = api_get(f"{API_BASE}/users/by/username/{username}")
    user_id = data["data"]["id"]

    user_ids[username] = user_id
    save_json(CACHE_FILE, user_ids)
    return user_id


def get_post_url(post):
    return f"https://x.com/{post.get('username', '')}/status/{post['id']}"


def fetch_posts(username, user_id):
    params = {
        "max_results": 100,
        "exclude": "replies",
        "tweet.fields": "created_at,referenced_tweets,attachments",
        "expansions": (
            "attachments.media_keys,"
            "referenced_tweets.id,"
            "referenced_tweets.id.author_id"
        ),
        "media.fields": "media_key,type,url,preview_image_url,alt_text",
    }

    data = api_get(f"{API_BASE}/users/{user_id}/tweets", params)
    posts = data.get("data", [])
    includes = data.get("includes", {})

    media_by_key = {
        item["media_key"]: item
        for item in includes.get("media", [])
        if "media_key" in item
    }

    referenced_by_id = {
        item["id"]: item
        for item in includes.get("tweets", [])
        if "id" in item
    }

    users_by_id = {
        item["id"]: item
        for item in includes.get("users", [])
        if "id" in item
    }

    normalized = []

    for post in posts:
        refs = post.get("referenced_tweets", [])
        repost = any(r["type"] == "retweeted" for r in refs)
        quote = any(r["type"] == "quoted" for r in refs)

        text = post.get("text", "")
        if repost:
            text = "🔁 Repost: " + text
        elif quote:
            text = "🗨️ Zitierter Post: " + text

        media_urls = []
        attachments = post.get("attachments", {})
        for key in attachments.get("media_keys", []):
            media = media_by_key.get(key, {})
            url = media.get("url") or media.get("preview_image_url")
            if url:
                media_urls.append(url)

        # Bei Zitaten nach Möglichkeit auch Medien des zitierten Posts aufnehmen.
        for ref in refs:
            if ref["type"] == "quoted":
                quoted = referenced_by_id.get(ref["id"], {})
                for key in quoted.get("attachments", {}).get("media_keys", []):
                    media = media_by_key.get(key, {})
                    url = media.get("url") or media.get("preview_image_url")
                    if url and url not in media_urls:
                        media_urls.append(url)

        normalized.append({
            "id": post["id"],
            "text": text,
            "created_at": post.get("created_at", ""),
            "url": f"https://x.com/{username}/status/{post['id']}",
            "media_urls": media_urls,
        })

    normalized.sort(
        key=lambda p: p["created_at"],
        reverse=True
    )
    return normalized


def download_image(url, image_dir, post_id, index):
    image_dir = Path(image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        extension = ".jpg"
        if "png" in content_type:
            extension = ".png"
        elif "webp" in content_type:
            extension = ".webp"
        elif "gif" in content_type:
            extension = ".gif"

        filename = f"{post_id}_{index}{extension}"
        path = image_dir / filename
        path.write_bytes(response.content)
        return filename
    except requests.RequestException as exc:
        print(f"Bild konnte nicht geladen werden: {exc}")
        return None


def build_feed(username, posts, output_file, image_dir, public_image_base):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = f"X – @{username}"
    ET.SubElement(channel, "link").text = f"https://x.com/{username}"
    ET.SubElement(channel, "description").text = f"Beiträge von @{username}"

    for post in posts[:MAX_POSTS]:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = post["text"][:200]
        ET.SubElement(item, "link").text = post["url"]
        ET.SubElement(item, "guid", isPermaLink="false").text = post["id"]

        try:
            dt = datetime.fromisoformat(
                post["created_at"].replace("Z", "+00:00")
            )
            ET.SubElement(item, "pubDate").text = format_datetime(
                dt.astimezone(timezone.utc)
            )
        except (ValueError, TypeError):
            pass

        description_parts = [
            f'<p>{html.escape(post["text"])}</p>'
        ]

        for index, media_url in enumerate(post["media_urls"], start=1):
            filename = download_image(
                media_url, image_dir, post["id"], index
            )
            if filename:
                image_url = public_image_base.rstrip("/") + "/" + filename
                description_parts.append(
                    f'<p><img src="{html.escape(image_url, quote=True)}" '
                    f'alt="Bild zum X-Beitrag" /></p>'
                )

        ET.SubElement(item, "description").text = (
            "<![CDATA[" + "".join(description_parts) + "]]>"
        )

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(output_file, encoding="utf-8", xml_declaration=True)


def run_account(username, output_file, image_dir, public_image_base):
    print(f"Lese X-Konto @{username} ...")

    user_ids = load_json(CACHE_FILE, {})
    seen_posts = load_json(STATE_FILE, {})

    user_id = get_user_id(username, user_ids)
    posts = fetch_posts(username, user_id)

    # RSS immer auf die drei neuesten Beiträge begrenzen.
    build_feed(
        username,
        posts,
        output_file,
        image_dir,
        public_image_base,
    )

    # IDs für eine spätere Discord-Deduplizierung bereitstellen.
    seen_posts.setdefault(username, [])
    current_ids = [p["id"] for p in posts]
    seen_posts[username] = list(
        dict.fromkeys(current_ids + seen_posts[username])
    )[:500]
    save_json(STATE_FILE, seen_posts)

    print(f"{output_file}: {min(len(posts), MAX_POSTS)} Beiträge geschrieben.")
