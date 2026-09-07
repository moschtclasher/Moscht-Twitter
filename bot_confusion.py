import re
import html
import hashlib
import requests
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path


# ==========================================================
# Konfiguration
# ==========================================================

USERNAME = "Confusion_CoC"

PROFILE_URL = f"https://x.com/{USERNAME}"
KEEP_RSS_URL = f"https://keep.md/api/x-rss/{USERNAME}.xml?content=posts"

FEED_FILE = "feed-confusion.xml"

IMAGE_DIR = Path("images/confusion_coc")


# ==========================================================
# HTTP
# ==========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


# ==========================================================
# Keep RSS
# ==========================================================

def get_keep_feed():
    """Lädt den öffentlichen Keep-RSS-Feed."""
    print("Abrufe Keep RSS Feed:")
    print(KEEP_RSS_URL)

    response = requests.get(
        KEEP_RSS_URL,
        headers=HEADERS,
        timeout=30,
    )

    print("HTTP Status:", response.status_code)
    print("Antwortgröße:", len(response.content))

    response.raise_for_status()

    if not response.text.strip():
        raise RuntimeError("Keep lieferte eine leere Antwort.")

    return response.text


def parse_keep_feed(feed_xml):
    """Extrahiert Posts, Bilder, Datum und X-Link aus dem Keep-RSS-Feed."""

    root = ET.fromstring(feed_xml)
    items = root.findall("./channel/item")

    tweets = []

    for item in items:
        link = (item.findtext("link") or "").strip()
        creator = (
            item.findtext("{http://purl.org/dc/elements/1.1/}creator")
            or ""
        ).strip()

        # Keep kann auch Posts anderer Accounts liefern.
        # Deshalb nur den gewünschten Account übernehmen.
        if creator.lower() != f"@{USERNAME}".lower():
            continue

        match = re.search(r"/status/(\d{15,25})", link)

        if not match:
            continue

        tweet_id = match.group(1)

        # ------------------------------------------------------
        # Text
        # ------------------------------------------------------

        text = (
            item.findtext("description")
            or ""
        ).strip()

        text = html.unescape(text)

        # ------------------------------------------------------
        # Datum
        # ------------------------------------------------------

        pub_date = item.findtext("pubDate")
        created_at = None

        if pub_date:
            try:
                created_at = parsedate_to_datetime(pub_date)
            except (TypeError, ValueError):
                pass

        if created_at is None:
            created_at = datetime.now(timezone.utc)

        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        created_at = created_at.astimezone(timezone.utc)

        # ------------------------------------------------------
        # Bilder aus content:encoded
        # ------------------------------------------------------

        encoded = (
            item.findtext(
                "{http://purl.org/rss/1.0/modules/content/}encoded"
            )
            or ""
        )

        image_urls = re.findall(
            r'https://pbs\.twimg\.com/media/[^"\'> ]+',
            encoded,
            flags=re.IGNORECASE,
        )

        clean_images = []
        seen_media_ids = set()

        for image_url in image_urls:
            image_url = html.unescape(image_url)
            image_url = image_url.rstrip(".,!?)]}")

            media_match = re.search(
                r"/media/([^/?]+)",
                image_url,
                flags=re.IGNORECASE,
            )

            if not media_match:
                continue

            media_id = media_match.group(1)

            if media_id in seen_media_ids:
                continue

            seen_media_ids.add(media_id)

            clean_images.append(
                f"https://pbs.twimg.com/media/{media_id}?name=orig"
            )

        print("")
        print("Post:", tweet_id)
        print("Datum:", format_datetime(created_at, usegmt=True))
        print("Text:", text[:150])
        print("Bilder:", len(clean_images))

        tweets.append(
            {
                "id": tweet_id,
                "text": text,
                "created_at": created_at,
                "images": clean_images,
                "url": link,
            }
        )

    # Neueste Posts zuerst.
    tweets.sort(
        key=lambda tweet: tweet["created_at"],
        reverse=True,
    )

    return tweets


# ==========================================================
# Bilder herunterladen
# ==========================================================

def download_image(
    image_url,
    tweet_id,
    index,
    seen_hashes=None,
):
    IMAGE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    base_url = image_url.split("?")[0]

    extension = Path(base_url).suffix.lower()

    if extension not in [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    ]:
        extension = ".jpg"

    if index == 0:
        filename = f"{tweet_id}{extension}"
    else:
        filename = f"{tweet_id}_{index}{extension}"

    target = IMAGE_DIR / filename

    try:
        response = requests.get(
            image_url,
            headers=HEADERS,
            timeout=30,
        )

        response.raise_for_status()

        content_hash = hashlib.sha256(
            response.content
        ).hexdigest()

        if seen_hashes is not None:
            if content_hash in seen_hashes:
                print("ℹ️ Doppeltes Bild erkannt, überspringe:")
                print(image_url)
                return None

            seen_hashes.add(content_hash)

        target.write_bytes(response.content)

        print(
            f"✅ Bild gespeichert: "
            f"{target} "
            f"({len(response.content)} Bytes)"
        )

        return target

    except requests.RequestException as e:
        print("❌ Bild konnte nicht geladen werden:")
        print(image_url)
        print(e)
        return None


# ==========================================================
# RSS Item
# ==========================================================

def create_rss_item(
    channel,
    tweet,
):
    tweet_id = tweet["id"]

    item = ET.SubElement(
        channel,
        "item",
    )

    title = ET.SubElement(
        item,
        "title",
    )

    title.text = re.sub(
        r"\s+",
        " ",
        tweet["text"],
    ).strip()[:300]

    description = ET.SubElement(
        item,
        "description",
    )

    description.text = tweet["text"]

    link = ET.SubElement(
        item,
        "link",
    )

    link.text = tweet.get(
        "url",
        f"https://x.com/{USERNAME}/status/{tweet_id}",
    )

    guid = ET.SubElement(
        item,
        "guid",
        {
            "isPermaLink": "false",
        },
    )

    guid.text = tweet_id

    pub_date = ET.SubElement(
        item,
        "pubDate",
    )

    pub_date.text = format_datetime(
        tweet["created_at"],
        usegmt=True,
    )

    # ------------------------------------------------------
    # Bilder
    # ------------------------------------------------------

    seen_image_hashes = set()

    for index, image_url in enumerate(
        tweet["images"]
    ):
        image = download_image(
            image_url,
            tweet_id,
            index,
            seen_hashes=seen_image_hashes,
        )

        if image is None:
            continue

        public_url = (
            "https://moschtclasher.github.io/"
            "Moscht-Twitter/"
            "images/confusion_coc/"
            f"{image.name}"
        )

        extension = image.suffix.lower()

        mime_type = (
            "image/png"
            if extension == ".png"
            else "image/jpeg"
        )

        ET.SubElement(
            item,
            "enclosure",
            {
                "url": public_url,
                "type": mime_type,
                "length": str(
                    image.stat().st_size
                ),
            },
        )

        ET.SubElement(
            item,
            "{http://search.yahoo.com/mrss/}content",
            {
                "url": public_url,
                "medium": "image",
                "type": mime_type,
            },
        )


# ==========================================================
# RSS Feed
# ==========================================================

def create_feed(tweets):
    rss = ET.Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:media":
                "http://search.yahoo.com/mrss/",
        },
    )

    channel = ET.SubElement(
        rss,
        "channel",
    )

    ET.SubElement(
        channel,
        "title",
    ).text = (
        f"X-Posts von @{USERNAME}"
    )

    ET.SubElement(
        channel,
        "link",
    ).text = PROFILE_URL

    ET.SubElement(
        channel,
        "description",
    ).text = (
        f"Automatisch erzeugter RSS-Feed "
        f"für @{USERNAME}"
    )

    ET.SubElement(
        channel,
        "language",
    ).text = "de"

    ET.SubElement(
        channel,
        "lastBuildDate",
    ).text = format_datetime(
        datetime.now(timezone.utc),
        usegmt=True,
    )

    ET.SubElement(
        channel,
        "generator",
    ).text = "GitHub Actions über Keep RSS"

    for tweet in tweets:
        create_rss_item(
            channel,
            tweet,
        )

    tree = ET.ElementTree(
        rss
    )

    ET.indent(
        tree,
        space="  ",
    )

    tree.write(
        FEED_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )

    print("")
    print(
        f"✅ Feed gespeichert: "
        f"{FEED_FILE}"
    )


# ==========================================================
# Main
# ==========================================================

def main():
    print("=" * 60)
    print(
        f"Keep RSS Feed für @{USERNAME}"
    )
    print("=" * 60)

    feed_xml = get_keep_feed()

    tweets = parse_keep_feed(
        feed_xml
    )

    if not tweets:
        raise RuntimeError(
            f"Keine Posts von @{USERNAME} "
            f"im Keep-Feed gefunden."
        )

    # Nur die 3 neuesten Posts übernehmen.
    tweets = tweets[:3]

    print("")
    print(
        f"Verwende die {len(tweets)} neuesten Posts:"
    )

    for tweet in tweets:
        print(
            f" - {tweet['id']} | "
            f"{format_datetime(tweet['created_at'], usegmt=True)}"
        )

    create_feed(tweets)

    print("")
    print("✅ Fertig.")


if __name__ == "__main__":
    main()
