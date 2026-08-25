import re
import html
import hashlib
import requests
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path


# ==========================================================
# Konfiguration
# ==========================================================

USERNAME = "moscht_coc"

PROFILE_URL = f"https://x.com/{USERNAME}"
FEED_FILE = "feed.xml"
IMAGE_DIR = Path(f"images/{USERNAME}")

# Wie viele Tweets vom Profil zunächst untersucht werden
MAX_PROFILE_TWEETS = 5

# Wie viele Tweets tatsächlich in den Feed kommen
MAX_FEED_TWEETS = 3


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
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


# ==========================================================
# X Profil
# ==========================================================

def get_profile_html():

    print("Abrufe X-Profil:")
    print(PROFILE_URL)

    response = requests.get(
        PROFILE_URL,
        headers=HEADERS,
        timeout=30,
    )

    print("HTTP Status:", response.status_code)
    print("Antwortgröße:", len(response.content))

    response.raise_for_status()

    if not response.text.strip():
        raise RuntimeError(
            "X lieferte eine leere Antwort."
        )

    return response.text


# ==========================================================
# Tweet IDs
# ==========================================================

def extract_tweet_ids(profile_html):

    pattern = (
        rf"/{re.escape(USERNAME)}/status/(\d{{15,25}})"
    )

    ids = re.findall(
        pattern,
        profile_html,
        flags=re.IGNORECASE,
    )

    # Doppelte IDs entfernen,
    # Reihenfolge aus dem HTML beibehalten
    ids = list(dict.fromkeys(ids))

    print(
        f"Gefundene Tweet-IDs: {len(ids)}"
    )

    for tweet_id in ids:
        print(" -", tweet_id)

    return ids


# ==========================================================
# Tweet abrufen
# ==========================================================

def get_tweet(tweet_id):

    url = (
        f"https://x.com/{USERNAME}/status/{tweet_id}"
    )

    print("")
    print("Abrufe Tweet:")
    print(url)

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    print(
        "HTTP Status:",
        response.status_code,
    )

    response.raise_for_status()

    return response.text


# ==========================================================
# Tweet-Typ erkennen
# ==========================================================

def detect_tweet_type(tweet_html):

    """
    Versucht anhand verschiedener Hinweise im X-HTML
    zwischen Original, Repost und Quote-Repost zu unterscheiden.

    Wichtig:
    X verändert die HTML-Struktur gelegentlich.
    Deshalb werden mehrere unterschiedliche Hinweise geprüft.
    """

    lower_html = tweet_html.lower()

    # ------------------------------------------------------
    # Diagnose: relevante Begriffe
    # ------------------------------------------------------

    repost_keywords = [
        "retweeted",
        "reposted",
        "retweet",
        "repost",
    ]

    quote_keywords = [
        "quote",
        "quoted",
        "quote tweet",
        "quoted_status",
    ]

    repost_hits = [
        keyword
        for keyword in repost_keywords
        if keyword in lower_html
    ]

    quote_hits = [
        keyword
        for keyword in quote_keywords
        if keyword in lower_html
    ]

    # ------------------------------------------------------
    # Strukturierte Daten untersuchen
    # ------------------------------------------------------

    structured_repost = False
    structured_quote = False

    structured_patterns_repost = [
        r'"retweeted_status"',
        r'"retweeted_status_result"',
        r'"repost"',
        r'"is_retweet"\s*:\s*true',
        r'"retweeted"\s*:\s*true',
    ]

    structured_patterns_quote = [
        r'"quoted_status"',
        r'"quoted_status_result"',
        r'"quote_status"',
        r'"is_quote_status"\s*:\s*true',
        r'"quoted"\s*:\s*true',
    ]

    for pattern in structured_patterns_repost:
        if re.search(
            pattern,
            tweet_html,
            flags=re.IGNORECASE,
        ):
            structured_repost = True
            break

    for pattern in structured_patterns_quote:
        if re.search(
            pattern,
            tweet_html,
            flags=re.IGNORECASE,
        ):
            structured_quote = True
            break

    # ------------------------------------------------------
    # Ergebnis
    # ------------------------------------------------------

    if structured_quote:
        tweet_type = "quote"

    elif structured_repost:
        tweet_type = "repost"

    elif repost_hits and not quote_hits:
        tweet_type = "repost"

    elif quote_hits:
        tweet_type = "quote"

    else:
        tweet_type = "original"

    # ------------------------------------------------------
    # Diagnose ausgeben
    # ------------------------------------------------------

    print("Typ:", tweet_type)

    print(
        "Diagnose:",
        f"Repost-Hinweise={repost_hits or '-'}, "
        f"Quote-Hinweise={quote_hits or '-'}, "
        f"strukturierter Repost={structured_repost}, "
        f"strukturierter Quote={structured_quote}",
    )

    return tweet_type


# ==========================================================
# Tweet-Daten aus HTML
# ==========================================================

def extract_tweet_data(tweet_html, tweet_id):

    # ------------------------------------------------------
    # Tweet-Typ
    # ------------------------------------------------------

    tweet_type = detect_tweet_type(
        tweet_html
    )

    # ------------------------------------------------------
    # Text
    # ------------------------------------------------------

    text = ""

    text_patterns = [
        r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"',
        r'<meta[^>]+name="twitter:description"[^>]+content="([^"]*)"',
        r'<meta[^>]+name="description"[^>]+content="([^"]*)"',
    ]

    for pattern in text_patterns:

        match = re.search(
            pattern,
            tweet_html,
            flags=re.IGNORECASE,
        )

        if match:

            text = html.unescape(
                match.group(1)
            ).strip()

            if text:
                break

    # ------------------------------------------------------
    # Falls Attribute andersherum stehen
    # ------------------------------------------------------

    if not text:

        reverse_patterns = [
            r'<meta[^>]+content="([^"]*)"[^>]+property="og:description"',
            r'<meta[^>]+content="([^"]*)"[^>]+name="twitter:description"',
        ]

        for pattern in reverse_patterns:

            match = re.search(
                pattern,
                tweet_html,
                flags=re.IGNORECASE,
            )

            if match:

                text = html.unescape(
                    match.group(1)
                ).strip()

                if text:
                    break

    # ------------------------------------------------------
    # t.co Links auflösen
    # ------------------------------------------------------

    tco_links = re.findall(
        r"https://t\.co/[A-Za-z0-9]+",
        text,
    )

    for tco_url in tco_links:

        try:

            response = requests.get(
                tco_url,
                headers=HEADERS,
                timeout=15,
                allow_redirects=True,
            )

            final_url = response.url

            if final_url and final_url != tco_url:

                text = text.replace(
                    tco_url,
                    final_url,
                )

        except requests.RequestException:
            pass

    # ------------------------------------------------------
    # Bilder
    # ------------------------------------------------------

    image_urls = re.findall(
        r'https://pbs\.twimg\.com/media/[^"\'&<> ]+',
        tweet_html,
        flags=re.IGNORECASE,
    )

    clean_images = []
    seen_media_ids = set()

    for image_url in image_urls:

        if not image_url:
            continue

        image_url = html.unescape(
            image_url
        )

        image_url = image_url.rstrip(
            ".,!?)]}"
        )

        match = re.search(
            r"/media/([^/?]+)",
            image_url,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        media_id = match.group(1)

        if media_id in seen_media_ids:
            continue

        seen_media_ids.add(
            media_id
        )

        image_url = (
            "https://pbs.twimg.com/media/"
            f"{media_id}?name=orig"
        )

        clean_images.append(
            image_url
        )

    # ------------------------------------------------------
    # Datum
    # ------------------------------------------------------

    created_at = None

    date_patterns = [
        r'<meta[^>]+property="article:published_time"[^>]+content="([^"]*)"',
        r'<meta[^>]+property="og:updated_time"[^>]+content="([^"]*)"',
    ]

    for pattern in date_patterns:

        match = re.search(
            pattern,
            tweet_html,
            flags=re.IGNORECASE,
        )

        if match:

            value = html.unescape(
                match.group(1)
            ).strip()

            try:

                created_at = datetime.fromisoformat(
                    value.replace(
                        "Z",
                        "+00:00",
                    )
                )

                break

            except ValueError:
                pass

    if created_at is None:

        created_at = datetime.now(
            timezone.utc
        )

    if created_at.tzinfo is None:

        created_at = created_at.replace(
            tzinfo=timezone.utc
        )

    created_at = created_at.astimezone(
        timezone.utc
    )

    # ------------------------------------------------------
    # Ausgabe
    # ------------------------------------------------------

    print(
        "Typ:",
        tweet_type,
    )

    print(
        "Text:",
        text[:150],
    )

    print(
        "Bilder:",
        len(clean_images),
    )

    return {
        "id": tweet_id,
        "text": text,
        "created_at": created_at,
        "images": clean_images,
        "type": tweet_type,
    }


# ==========================================================
# Bild herunterladen
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

    extension = Path(
        base_url
    ).suffix.lower()

    if extension not in [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    ]:
        extension = ".jpg"

    if index == 0:

        filename = (
            f"{tweet_id}{extension}"
        )

    else:

        filename = (
            f"{tweet_id}_{index}{extension}"
        )

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

                print(
                    "ℹ️ Doppeltes Bild erkannt, überspringe:"
                )

                print(image_url)

                return None

            seen_hashes.add(
                content_hash
            )

        target.write_bytes(
            response.content
        )

        print(
            f"✅ Bild gespeichert: "
            f"{target} "
            f"({len(response.content)} Bytes)"
        )

        return target

    except requests.RequestException as e:

        print(
            "❌ Bild konnte nicht geladen werden:"
        )

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

    # ------------------------------------------------------
    # Titel
    # ------------------------------------------------------

    title = ET.SubElement(
        item,
        "title",
    )

    title.text = re.sub(
        r"\s+",
        " ",
        tweet["text"],
    ).strip()[:300]

    # ------------------------------------------------------
    # Beschreibung
    # ------------------------------------------------------

    description = ET.SubElement(
        item,
        "description",
    )

    description.text = tweet["text"]

    # ------------------------------------------------------
    # Link
    # ------------------------------------------------------

    link = ET.SubElement(
        item,
        "link",
    )

    link.text = (
        f"https://x.com/"
        f"{USERNAME}/status/"
        f"{tweet_id}"
    )

    # ------------------------------------------------------
    # GUID
    # ------------------------------------------------------

    guid = ET.SubElement(
        item,
        "guid",
        {
            "isPermaLink": "false"
        },
    )

    guid.text = tweet_id

    # ------------------------------------------------------
    # Datum
    # ------------------------------------------------------

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

        # Dynamischer GitHub-Pages-Pfad
        public_url = (
            "https://moschtclasher.github.io/"
            "Moscht-Twitter/"
            f"{image.as_posix()}"
        )

        extension = image.suffix.lower()

        if extension == ".png":
            mime_type = "image/png"

        elif extension == ".webp":
            mime_type = "image/webp"

        else:
            mime_type = "image/jpeg"

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
            "{http://search.yahoo.com/mrss/}"
            "content",
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
    ).text = (
        "GitHub Actions über X"
    )

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
        f"X Direkt Feed für @{USERNAME}"
    )

    print("=" * 60)

    # ------------------------------------------------------
    # Profil abrufen
    # ------------------------------------------------------

    profile_html = get_profile_html()

    tweet_ids = extract_tweet_ids(
        profile_html
    )

    if not tweet_ids:

        raise RuntimeError(
            "Keine Tweet-IDs gefunden."
        )

    # ------------------------------------------------------
    # Tweets untersuchen
    # ------------------------------------------------------

    tweets = []

    for tweet_id in tweet_ids[
        :MAX_PROFILE_TWEETS
    ]:

        try:

            tweet_html = get_tweet(
                tweet_id
            )

            tweet = extract_tweet_data(
                tweet_html,
                tweet_id,
            )

            tweets.append(
                tweet
            )

        except Exception as e:

            print(
                f"❌ Tweet {tweet_id} "
                f"konnte nicht verarbeitet werden:"
            )

            print(e)

    if not tweets:

        raise RuntimeError(
            "Keine Tweets konnten verarbeitet werden."
        )

    # ------------------------------------------------------
    # Nach Datum sortieren
    # ------------------------------------------------------

    tweets.sort(
        key=lambda tweet: tweet["created_at"],
        reverse=True,
    )

    # ------------------------------------------------------
    # Nur die gewünschten neuesten Tweets
    # ------------------------------------------------------

    tweets = tweets[
        :MAX_FEED_TWEETS
    ]

    print("")

    print(
        f"Verwende die {len(tweets)} "
        f"neuesten Tweets:"
    )

    for tweet in tweets:

        print(
            " -",
            tweet["id"],
            "|",
            format_datetime(
                tweet["created_at"],
                usegmt=True,
            ),
            "|",
            tweet["type"],
        )

    # ------------------------------------------------------
    # Feed erstellen
    # ------------------------------------------------------

    create_feed(
        tweets
    )

    print("")
    print("✅ Fertig.")


if __name__ == "__main__":
    main()
