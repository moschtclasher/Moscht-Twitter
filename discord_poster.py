import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import requests


STATE_FILE = "last_posts.json"

FEEDS = [
    {
        "feed_file": "feed.xml",
        "webhook": os.environ["DISCORD_WEBHOOK_MOSCHT"],
        "display_name": "Moscht CoC",
        "username": "@moscht_coc",
        "history": 5,
        "color": 0x1DA1F2,
    },
    {
        "feed_file": "feed-confusion.xml",
        "webhook": os.environ["DISCORD_WEBHOOK_CONFUSION"],
        "display_name": "Confusion",
        "username": "@confusion",
        "history": 5,
        "color": 0x5865F2,
    },
]


def load_state():
    """Lädt last_posts.json."""

    if not Path(STATE_FILE).exists():
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    """Speichert last_posts.json."""

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def read_feed(feed_file):
    """Liest einen RSS-Feed ein."""

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
