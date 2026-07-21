import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

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
        "history": 5,
        "color": 0x1DA1F2,
    },
    {
        "feed_file": "feed-confusion.xml",
        "webhook": os.environ["DISCORD_WEBHOOK_CONFUSION"],
        "display_name": "CNF | Twitter/X",
        "avatar_url": "https://moschtclasher.github.io/Moscht-Twitter/images/confusion_avatar.png",
        "history": 5,
        "color": 0x5865F2,
    },
]


# ==========================================================
# State
# ==========================================================

def load_state():
    """Lädt den zuletzt geposteten Stand."""

    if not Path(STATE_FILE).exists():
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    """Speichert den zuletzt geposteten Stand."""

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ==========================================================
# RSS Feed
# ==========================================================

def read_feed(feed_file):
    """Liest einen RSS Feed."""

    tree = ET.parse(feed_file)
    root = tree.getroot()

    posts = []

    for item in root.findall("./channel/item"):

        enclosure = item.find("enclosure")

        image = ""

        if enclosure is not None:
            image = enclosure.attrib.get("url", "")

        posts.append(
            {
                "guid": item.findtext("guid", ""),
                "title": item.findtext("title", ""),
                "description": item.findtext("description", ""),
                "link": item.findtext("link", ""),
                "pubDate": item.findtext("pubDate", ""),
                "image": image,
            }
        )

    return posts
    # ==========================================================
# Discord
# ==========================================================

def create_embed(post, feed):
    """Erstellt ein Discord-Embed."""

    embed = {
        "description": post["description"] or "",
        "url": post["link"],
        "color": feed["color"],
    }

    if post["image"]:
        embed["image"] = {
            "url": post["image"]
        }

    return embed


def send_to_discord(post, feed):
    """Sendet einen Beitrag an Discord."""

    payload = {
        "username": feed["display_name"],
        "avatar_url": feed["avatar_url"],
        "embeds": [
            create_embed(post, feed)
        ]
    }

    try:
        response = requests.post(
            feed["webhook"],
            json=payload,
            timeout=30,
        )

        if response.status_code == 204:
            print(f"✅ Gesendet: {post['guid']}")
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

    last_guid = state.get(feed["feed_file"])

    # ------------------------------------------------------
    # Erster Start
    # ------------------------------------------------------

    if last_guid is None:

        print("➡️ Erster Start - sende letzte Beiträge")

        history_posts = list(
            reversed(
                posts[:feed["history"]]
            )
        )

        for post in history_posts:

            send_to_discord(
                post,
                feed,
            )

        state[feed["feed_file"]] = posts[0]["guid"]

        return

    # ------------------------------------------------------
    # Neue Beiträge finden
    # ------------------------------------------------------

    new_posts = []

    for post in posts:

        if post["guid"] == last_guid:
            break

        new_posts.append(post)

    if not new_posts:
        print("Keine neuen Beiträge.")
        return

    print(f"{len(new_posts)} neue Beiträge gefunden.")

    for post in reversed(new_posts):

        send_to_discord(
            post,
            feed,
        )

    state[feed["feed_file"]] = posts[0]["guid"]
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
