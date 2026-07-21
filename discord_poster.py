import xml.etree.ElementTree as ET
from pathlib import Path

FEEDS = [
    {
        "name": "Moscht",
        "file": "feed.xml",
    },
    {
        "name": "Confusion",
        "file": "feed-confusion.xml",
    },
]


def load_feed(feed_file):
    if not Path(feed_file).exists():
        print(f"❌ {feed_file} nicht gefunden")
        return []

    tree = ET.parse(feed_file)
    root = tree.getroot()

    posts = []

    for item in root.findall("./channel/item"):
        post = {
            "guid": item.findtext("guid", ""),
            "title": item.findtext("title", ""),
            "description": item.findtext("description", ""),
            "link": item.findtext("link", ""),
            "pubDate": item.findtext("pubDate", ""),
        }

        enclosure = item.find("enclosure")

        if enclosure is not None:
            post["image"] = enclosure.attrib.get("url", "")
        else:
            post["image"] = ""

        posts.append(post)

    return posts


def main():
    for feed in FEEDS:

        print("=" * 60)
        print(feed["name"])
        print("=" * 60)

        posts = load_feed(feed["file"])

        print(f"{len(posts)} Beiträge gefunden\n")

        if not posts:
            continue

        newest = posts[0]

        print("Neuester Beitrag")
        print("----------------")
        print(newest["title"])
        print(newest["description"])
        print(newest["link"])
        print(newest["image"])
        print()


if __name__ == "__main__":
    main()
