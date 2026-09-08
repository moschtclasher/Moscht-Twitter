import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

# ==========================================================
# Konfiguration
# ==========================================================

STATE_FILE = "last_posts.json"

FEEDS = [
    {
        "feed_file": "feed.xml",
        "webhook": os.environ["DISCORD_WEBHOOK_MOSCHT"],
        "display_name": "Moscht Twitter/X",
        "avatar_url": "https://moschtclasher.github.io/Moscht-Twitter/images/confusion_avatar.png",
        "footer": "𝕏 • @moscht_coc",
        "history": 5,
        "color": 0xFFF533,
        "mention": "<@&1528735528772571137>",
        "emoji": "<a:blitzcnf:1475376256970260582>",
    },
    {
        "feed_file": "feed-confusion.xml",
        "webhook": os.environ["DISCORD_WEBHOOK_CONFUSION"],
        "display_name": "CNF | Twitter/X",
        "avatar_url": "https://moschtclasher.github.io/Moscht-Twitter/images/confusion_avatar.png",
        "footer": "𝕏 • @Confusion_CoC",
        "history": 5,
        "color": 0xFFF533,
        "mention": "<@&1506407793866047579>",
        "emoji": "<a:blitzcnf:1475376256970260582>",
    },
    {
        "feed_file": "feed-lurmii.xml",
        "webhook": os.environ["DISCORD_WEBHOOK_LURMII"],
        "display_name": "Lurmii Twitter/X",
        "avatar_url": "https://moschtclasher.github.io/Moscht-Twitter/images/confusion_avatar.png",
        "footer": "𝕏 • @Twitch_Lurmii",
        "history": 5,
        "color": 0xFFF533,
        "mention": "<@&1537072600948150352>",
        "emoji": "<a:blitzcnf:1475376256970260582>",
    },
        {
        "feed_file": "feed-wolfi.xml",
        "webhook": os.environ["DISCORD_WEBHOOK_WOLFI"],
        "display_name": "Wolfi Twitter/X",
        "avatar_url": "https://moschtclasher.github.io/Moscht-Twitter/images/confusion_avatar.png",
        "footer": "𝕏 • @ClashWithWolfi",
        "history": 5,
        "color": 0xFFF533,
        "mention": "<@&1541713656839151696>",
        "emoji": "<a:CHEER:1541717896680706048>",
    },
]


# ==========================================================
# State
# ==========================================================

MAX_SENT_IDS = 100


def load_state():
    """Lädt die bereits erfolgreich gesendeten Tweet-IDs."""
    if not Path(STATE_FILE).exists():
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # Neues Format: {feed_file: [guid, guid, ...]}
        if isinstance(raw, dict):
            normalized = {}
            for feed_file, value in raw.items():
                if isinstance(value, list):
                    normalized[feed_file] = [str(x) for x in value][-MAX_SENT_IDS:]
                elif value:
                    # Altes Format kompatibel übernehmen.
                    normalized[feed_file] = [str(value)]
                else:
                    normalized[feed_file] = []
            return normalized

    except Exception as e:
        print(f"⚠️ Konnte {STATE_FILE} nicht lesen: {e}")

    return {}


def save_state(state):
    """Speichert die bereits erfolgreich gesendeten Tweet-IDs."""
    clean_state = {
        feed_file: list(dict.fromkeys(ids))[-MAX_SENT_IDS:]
        for feed_file, ids in state.items()
    }

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_state, f, indent=2, ensure_ascii=False)


def get_post_id(post):
    """Ermittelt eine stabile ID für einen X-Post."""
    guid = (post.get("guid") or "").strip()
    if guid:
        match = re.search(r"/status/(\d+)", guid)
        if match:
            return match.group(1)

        # Bei bereits numerischer GUID direkt verwenden.
        if guid.isdigit():
            return guid

        return guid

    link = (post.get("link") or "").strip()
    match = re.search(r"/status/(\d+)", link)
    if match:
        return match.group(1)

    return ""


def mark_as_sent(state, feed_file, post):
    """Markiert einen Post erst nach erfolgreichem Discord-Versand als gesendet."""
    post_id = get_post_id(post)
    if not post_id:
        return

    sent_ids = state.setdefault(feed_file, [])
    if post_id not in sent_ids:
        sent_ids.append(post_id)

    # State begrenzen, damit last_posts.json nicht unendlich wächst.
    state[feed_file] = sent_ids[-MAX_SENT_IDS:]


# ==========================================================
# RSS Feed
# ==========================================================

def read_feed(feed_file):
    """Liest einen RSS-Feed ein."""

    tree = ET.parse(feed_file)
    root = tree.getroot()

    posts = []

    for item in root.findall("./channel/item"):
        image = ""

        # Erstes Enclosure verwenden
        enclosure = item.find("enclosure")
        if enclosure is not None:
            image = enclosure.attrib.get("url", "")

        # Falls kein Enclosure existiert:
        # erstes media:content verwenden
        if not image:
            media = item.find(
                "{http://search.yahoo.com/mrss/}content"
            )

            if media is not None:
                image = media.attrib.get("url", "")

        title = item.findtext("title", "") or ""
        link = item.findtext("link", "") or ""

        # Repost erkennen
        repost_match = re.match(
            r"^RT by @([A-Za-z0-9_]+):",
            title,
            flags=re.IGNORECASE,
        )

        is_repost = repost_match is not None
        reposted_by = repost_match.group(1) if repost_match else ""

        # Tatsächlichen Autor aus dem X-Link auslesen
        author_match = re.search(
            r"https?://(?:www\.)?(?:x\.com|twitter\.com)/([A-Za-z0-9_]+)/status/",
            link,
            flags=re.IGNORECASE,
        )

        original_author = author_match.group(1) if author_match else ""

        image_file = ""

        if image:
            image_name = Path(image).name

            if feed_file == "feed.xml":
                candidate = Path("images/moscht_coc") / image_name
            elif feed_file == "feed-confusion.xml":
                candidate = Path("images/confusion_coc") / image_name
            elif feed_file == "feed-lurmii.xml":
                candidate = Path("images/twitch_lurmii") / image_name
            elif feed_file == "feed-wolfi.xml":
                candidate = Path("images/clashofwolfi") / image_name
            else:
                candidate = None

            if candidate and candidate.exists():
                image_file = str(candidate)
        
        posts.append(
            {
                "guid": item.findtext("guid", "") or "",
                "title": title,
                "description": item.findtext("description", "") or "",
                "link": link,
                "pubDate": item.findtext("pubDate", "") or "",
                "image": image,
                "image_file": image_file,
                "is_repost": is_repost,
                "reposted_by": reposted_by,
                "original_author": original_author,
            }
        )

    return posts
    # ==========================================================
# Discord
# ==========================================================
def parse_timestamp(pub_date):
    """Wandelt RSS-Datum in ISO-8601 für Discord um."""

    if not pub_date:
        return None

    try:
        dt = parsedate_to_datetime(pub_date)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc).isoformat()

    except Exception:
        return None


# ===== HIER EINFÜGEN =====

def clean_description(text, post):
    """Bereinigt und formatiert den Tweettext."""

    if not text:
        return ""

    # Zeilenumbrüche vereinheitlichen
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # --------------------------------------------------
    # Repost ohne eigenen Kommentar
    # --------------------------------------------------
    if post.get("is_repost"):
        username = post.get("original_author")

        # Fallback, falls der Autor nicht aus dem Link gelesen werden konnte
        if not username:
            username = post.get("reposted_by", "")

        if username:
            text = (
                f"🔁 **Repost von @{username}**\n\n"
                f"{text}"
            )

    # --------------------------------------------------
    # Quote-Post erkennen
    # --------------------------------------------------
    else:
        quote_match = re.search(
            r"^(.*?)\n+(.+?) \(@([A-Za-z0-9_]+)\)\n+(.*)$",
            text,
            flags=re.DOTALL,
        )

        if quote_match:
            comment = quote_match.group(1).strip()
            username = quote_match.group(3).strip()
            quoted = quote_match.group(4).strip()

            text = (
                f"{comment}\n\n"
                "──────────────────\n\n"
                f"🔁 **Repost von @{username}**\n\n"
                f"{quoted}"
            )

    # --------------------------------------------------
    # Nitter-/X-/Twitter-Links entfernen
    # --------------------------------------------------
    text = re.sub(
        r"\n*—?\s*https?://(?:nitter\.[^\s]+|(?:www\.)?x\.com|(?:www\.)?twitter\.com)/\S+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Maximal eine Leerzeile
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
    

def create_embed(post, feed):
    """Erstellt ein Discord-Embed."""

    embed = {
        "description": (
            clean_description(
                post["description"],
                post
            )
            + f"\n\n🔗 [Beitrag ansehen]({post['link']})"
        ),
        "url": post["link"],
        "color": feed["color"],
        "timestamp": parse_timestamp(post["pubDate"]),
        "footer": {
            "text": feed["footer"]
        },
    }

    if post.get("image_file"):
        filename = Path(post["image_file"]).name
    
        embed["image"] = {
            "url": f"attachment://{filename}"
        }
    elif post["image"]:
        embed["image"] = {
            "url": post["image"]
        }

    return embed


def send_to_discord(post, feed):
    """Sendet einen Beitrag an Discord."""

    payload = {
        "username": feed["display_name"],
        "avatar_url": feed["avatar_url"],
        "content": f"{feed['mention']} {feed['emoji']}",
        "embeds": [
            create_embed(post, feed)
        ]
    }

    try:
        if post.get("image_file"):
            image_path = Path(post["image_file"])
        
            with image_path.open("rb") as image_file:
                files = {
                    "files[0]": (
                        image_path.name,
                        image_file,
                    )
                }
        
                data = {
                    "payload_json": json.dumps(payload)
                }
        
                response = requests.post(
                    feed["webhook"],
                    data=data,
                    files=files,
                    timeout=30,
                )
        
        else:
            response = requests.post(
                feed["webhook"],
                json=payload,
                timeout=30,
            )

        if 200 <= response.status_code < 300:
            print(f"✅ Gesendet: {get_post_id(post)}")
            return True

        print(f"❌ Discord Fehler: {response.status_code}")
        print(response.text)
        return False

    except requests.RequestException as e:
        print(f"❌ Netzwerkfehler: {e}")
        return False


# ==========================================================
# Feed Verarbeitung
# ==========================================================

def process_feed(feed, state):
    print("")
    print("=" * 60)
    print(feed["feed_file"])
    print("=" * 60)

    posts = read_feed(feed["feed_file"])

    if not posts:
        print("Keine Beiträge gefunden.")
        return

    feed_file = feed["feed_file"]
    sent_ids = set(state.get(feed_file, []))

    # Nur Posts senden, deren Tweet-ID noch nicht erfolgreich gesendet wurde.
    unsent_posts = []
    for post in posts:
        post_id = get_post_id(post)

        if not post_id:
            print(f"⚠️ Keine Tweet-ID gefunden: {post.get('link', '')}")
            continue

        if post_id not in sent_ids:
            unsent_posts.append(post)

    # Bei einem komplett neuen Feed nicht den gesamten Feed spammen,
    # sondern nur die konfigurierte Historie.
    if not sent_ids:
        posts_to_send = list(reversed(unsent_posts[:feed["history"]]))
        print(f"➡️ Erster Start - sende bis zu {len(posts_to_send)} Beiträge")
    else:
        posts_to_send = list(reversed(unsent_posts))
        print(f"➡️ {len(posts_to_send)} noch nicht gesendete Beiträge gefunden.")

    if not posts_to_send:
        print("Keine neuen Beiträge.")
        return

    for post in posts_to_send:
        post_id = get_post_id(post)

        print(f"📤 Sende Tweet {post_id} ...")

        if send_to_discord(post, feed):
            # Nur bei HTTP 204 als erfolgreich markieren.
            mark_as_sent(state, feed_file, post)
            save_state(state)
            print(f"💾 Als gesendet gespeichert: {post_id}")
        else:
            # Nicht als gesendet markieren -> nächster Lauf kann erneut versuchen.
            print(f"⚠️ Nicht gespeichert, da Versand fehlgeschlagen: {post_id}")


# ==========================================================
# Main
# ==========================================================

def main():
    print("=" * 60)
    print("Discord Poster gestartet")
    print("=" * 60)

    state = load_state()

    for feed in FEEDS:
        try:
            process_feed(feed, state)
        except Exception as e:
            print(f"❌ Fehler in {feed['feed_file']}: {e}")

    save_state(state)

    print("")
    print("✅ Fertig.")


if __name__ == "__main__":
    main()
