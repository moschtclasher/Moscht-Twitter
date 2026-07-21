import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

STATE_FILE = "last_posts.json"

FEEDS = [
    {
        "feed": "feed.xml",
        "webhook": os.environ["DISCORD_WEBHOOK_MOSCHT"],
        "name": "Moscht CoC",
        "history": 5,
        "color": 0x1DA1F2,
    },
    {
        "feed": "feed-confusion.xml",
        "webhook": os.environ["DISCORD_WEBHOOK_CONFUSION"],
        "name": "Confusion",
        "history": 5,
        "color": 0x5865F2,
    },
]


def load_state():
    if not Path(STATE_FILE).exists():
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def read_feed(filename):
    tree = ET.parse(filename)
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
            def send_to_discord(post, webhook, feed):
    """Sendet einen Beitrag als Discord-Embed."""

    embed = {
        "title": post["title"] or "Neuer X-Post",
        "description": post["description"],
        "url": post["link"],
        "color": feed["color"],
        "timestamp": None,
    }

    if post["image"]:
        embed["image"] = {
            "url": post["image"]
        }

    payload = {
        "username": feed["name"],
        "embeds": [embed],
    }

    response = requests.post(
        webhook,
        json=payload,
        timeout=30,
    )

    if response.status_code == 204:
        print(f"✅ {post['guid']} gesendet")
    else:
        print(
            f"❌ Discord Fehler {response.status_code}"
        )
        print(response.text)


def process_feed(feed, state):

    print(f"\n===== {feed['feed']} =====")

    posts = read_feed(feed["feed"])

    if not posts:
        print("Keine Beiträge gefunden.")
        return

    last_guid = state.get(feed["feed"])

    #
    # Erster Start
    #
    if last_guid is None:

        print("Erster Start.")

        history = list(
            reversed(
                posts[: feed["history"]]
            )
        )

        for post in history:
            send_to_discord(
                post,
                feed["webhook"],
                feed,
            )

        state[feed["feed"]] = posts[0]["guid"]
        return

    #
    # Neue Beiträge sammeln
    #
    new_posts = []

    for post in posts:

        if post["guid"] == last_guid:
            break

        new_posts.append(post)

    if not new_posts:

        print("Keine neuen Beiträge.")
        return

    #
    # Vom ältesten zum neuesten posten
    #
    for post in reversed(new_posts):

        send_to_discord(
            post,
            feed["webhook"],
            feed,
        )

    state[feed["feed"]] = posts[0]["guid"]


def main():

    state = load_state()

    for feed in FEEDS:

        process_feed(
            feed,
            state,
        )

    save_state(state)


if __name__ == "__main__":
    main()
        )

    return posts
