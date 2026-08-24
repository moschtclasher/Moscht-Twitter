import os
import re
import html
from datetime import datetime, timezone
from pathlib import Path
from email.utils import format_datetime

import requests
import xml.etree.ElementTree as ET


# ==========================================================
# Konfiguration
# ==========================================================

USERNAME = "Twitch_Lurmii"

API_URL = "https://api.sorsa.io/v3/search-tweets"

API_KEY = os.environ["SORSA_API_KEY"]

FEED_FILE = "feed-lurmii.xml"

IMAGE_DIR = Path("images/twitch_lurmii")

PROFILE_URL = f"https://x.com/{USERNAME}"


# ==========================================================
# Sorsa API
# ==========================================================

def get_tweets():
    """Holt die neuesten Tweets über Sorsa."""

    headers = {
        "ApiKey": API_KEY,
        "Content-Type": "application/json",
    }

    data = {
        "query": f"from:{USERNAME}",
        "order": "latest",
    }

    response = requests.post(
        API_URL,
        headers=headers,
        json=data,
        timeout=30,
    )

    print("Sorsa HTTP:", response.status_code)

    if response.status_code != 200:
        print(response.text)
        raise RuntimeError(
            f"Sorsa API Fehler: HTTP {response.status_code}"
        )

    result = response.json()

    tweets = result.get("tweets", [])

    print(f"{len(tweets)} Tweets von @{USERNAME} gefunden.")

    return tweets


# ==========================================================
# Hilfsfunktionen
# ==========================================================

def get_tweet_id(tweet):
    """Ermittelt die Tweet-ID."""

    return str(
        tweet.get("id")
        or tweet.get("rest_id")
        or ""
    )


def get_text(tweet):
    """Ermittelt den Tweettext."""

    return (
        tweet.get("full_text")
        or tweet.get("text")
        or ""
    ).strip()


def get_created_at(tweet):
    """Ermittelt das Erstellungsdatum."""

    value = (
        tweet.get("created_at")
        or tweet.get("createdAt")
        or ""
    )

    return value


def parse_date(value):
    """Wandelt Sorsa-Datum in datetime um."""

    if not value:
        return datetime.now(timezone.utc)

    formats = [
        "%a %b %d %H:%M:%S %z %Y",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return dt.astimezone(timezone.utc)

        except ValueError:
            pass

    print(f"⚠️ Datum konnte nicht gelesen werden: {value}")

    return datetime.now(timezone.utc)


# ==========================================================
# Bilder
# ==========================================================

def extract_image_urls(tweet, text):
    """Ermittelt Bild-URLs aus Tweet-Daten und Tweettext."""

    urls = []

    # ------------------------------------------------------
    # Medienobjekt aus API
    # ------------------------------------------------------

    media = tweet.get("media")

    if isinstance(media, list):

        for item in media:

            if not isinstance(item, dict):
                continue

            media_url = (
                item.get("media_url_https")
                or item.get("media_url")
                or item.get("url")
            )

            if media_url:
                urls.append(media_url)

    # ------------------------------------------------------
    # Bilder direkt aus dem Text
    # ------------------------------------------------------

    text_urls = re.findall(
        r"https?://pbs\.twimg\.com/media/[^\s]+",
        text,
    )

    urls.extend(text_urls)

    # ------------------------------------------------------
    # Duplikate entfernen
    # ------------------------------------------------------

    result = []

    for url in urls:

        url = html.unescape(url)

        # X hängt manchmal Satzzeichen an URLs
        url = url.rstrip(".,!?)]}")

        if url not in result:
            result.append(url)

    return result


def download_image(url, tweet_id, index):
    """Lädt ein Tweet-Bild nach GitHub herunter."""

    IMAGE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Dateiendung bestimmen
    clean_url = url.split("?")[0]

    extension = Path(clean_url).suffix.lower()

    if extension not in [".jpg", ".jpeg", ".png", ".webp"]:
        extension = ".jpg"

    filename = (
        f"{tweet_id}.jpg"
        if index == 0
        else f"{tweet_id}_{index}{extension}"
    )

    target = IMAGE_DIR / filename

    try:

        response = requests.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "Chrome/131 Safari/537.36"
                )
            },
            timeout=30,
        )

        response.raise_for_status()

        target.write_bytes(response.content)

        print(
            f"✅ Bild gespeichert: {target} "
            f"({len(response.content)} Bytes)"
        )

        return target

    except requests.RequestException as e:

        print(
            f"❌ Bild konnte nicht geladen werden: "
            f"{url}"
        )

        print(e)

        return None


# ==========================================================
# RSS
# ==========================================================

def create_rss_item(channel, tweet):
    """Erstellt einen RSS-Eintrag."""

    tweet_id = get_tweet_id(tweet)
    text = get_text(tweet)
    created_at = parse_date(
        get_created_at(tweet)
    )

    tweet_url = (
        f"https://x.com/{USERNAME}/status/{tweet_id}"
    )

    # ------------------------------------------------------
    # Bild-URLs
    # ------------------------------------------------------

    image_urls = extract_image_urls(
        tweet,
        text,
    )

    downloaded_images = []

    for index, image_url in enumerate(image_urls):

        image = download_image(
            image_url,
            tweet_id,
            index,
        )

        if image:
            downloaded_images.append(image)

    # ------------------------------------------------------
    # RSS Item
    # ------------------------------------------------------

    item = ET.SubElement(
        channel,
        "item",
    )

    title = ET.SubElement(
        item,
        "title",
    )

    # RSS-Titel auf eine Zeile begrenzen
    title_text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    title.text = title_text[:300]

    description = ET.SubElement(
        item,
        "description",
    )

    description.text = text

    link = ET.SubElement(
        item,
        "link",
    )

    link.text = tweet_url

    guid = ET.SubElement(
        item,
        "guid",
        {
            "isPermaLink": "false"
        },
    )

    guid.text = tweet_id

    pub_date = ET.SubElement(
        item,
        "pubDate",
    )

    pub_date.text = format_datetime(
        created_at,
        usegmt=True,
    )

    # ------------------------------------------------------
    # Bilder
    # ------------------------------------------------------

    if downloaded_images:

        for image in downloaded_images:

            public_url = (
                "https://moschtclasher.github.io/"
                "Moscht-Twitter/"
                f"images/twitch_lurmii/"
                f"{image.name}"
            )

            enclosure = ET.SubElement(
                item,
                "enclosure",
                {
                    "url": public_url,
                    "type": (
                        "image/png"
                        if image.suffix.lower() == ".png"
                        else "image/jpeg"
                    ),
                    "length": str(
                        image.stat().st_size
                    ),
                },
            )

            media = ET.SubElement(
                item,
                "{http://search.yahoo.com/mrss/}"
                "content",
                {
                    "url": public_url,
                    "medium": "image",
                    "type": (
                        "image/png"
                        if image.suffix.lower() == ".png"
                        else "image/jpeg"
                    ),
                },
            )


# ==========================================================
# RSS Feed erstellen
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

    title = ET.SubElement(
        channel,
        "title",
    )

    title.text = (
        f"X-Posts von @{USERNAME}"
    )

    link = ET.SubElement(
        channel,
        "link",
    )

    link.text = PROFILE_URL

    description = ET.SubElement(
        channel,
        "description",
    )

    description.text = (
        f"Automatisch erzeugter RSS-Feed "
        f"für @{USERNAME}"
    )

    language = ET.SubElement(
        channel,
        "language",
    )

    language.text = "de"

    last_build = ET.SubElement(
        channel,
        "lastBuildDate",
    )

    last_build.text = format_datetime(
        datetime.now(timezone.utc),
        usegmt=True,
    )

    generator = ET.SubElement(
        channel,
        "generator",
    )

    generator.text = (
        "GitHub Actions über Sorsa API"
    )

    # ------------------------------------------------------
    # Tweets
    # ------------------------------------------------------

    # Sorsa liefert normalerweise neueste zuerst.
    # Für RSS behalten wir diese Reihenfolge.
    for tweet in tweets:

        tweet_id = get_tweet_id(tweet)

        if not tweet_id:
            print(
                "⚠️ Tweet ohne ID übersprungen."
            )
            continue

        create_rss_item(
            channel,
            tweet,
        )

    # ------------------------------------------------------
    # XML speichern
    # ------------------------------------------------------

    tree = ET.ElementTree(rss)

    ET.indent(
        tree,
        space="  ",
    )

    tree.write(
        FEED_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )

    print(
        f"✅ Feed gespeichert: {FEED_FILE}"
    )


# ==========================================================
# Main
# ==========================================================

def main():

    print("=" * 60)
    print(
        f"Sorsa X Feed für @{USERNAME}"
    )
    print("=" * 60)

    tweets = get_tweets()

    if not tweets:
        print(
            "⚠️ Keine Tweets gefunden."
        )
        return

    create_feed(tweets)

    print("")
    print("✅ Fertig.")


if __name__ == "__main__":
    main()
