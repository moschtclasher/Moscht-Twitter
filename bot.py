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

    # Doppelte IDs entfernen, Reihenfolge beibehalten
    ids = list(dict.fromkeys(ids))

    print(
        f"Gefundene Tweet-IDs: {len(ids)}"
    )

    for tweet_id in ids:
        print(" -", tweet_id)

    return ids
# ==========================================================
# Tweet-Typ erkennen
# ==========================================================

def detect_tweet_type(tweet_html, tweet_id):

    """
    Untersucht die HTML-Seite eines einzelnen Tweets.

    Statt nach allgemeinen Wörtern wie 'repost' oder 'quote'
    zu suchen, werden eingebettete Tweet-IDs analysiert.
    """

    # ------------------------------------------------------
    # Alle Tweet-URLs im HTML finden
    # ------------------------------------------------------

    pattern = (
        r'https?://(?:www\.)?x\.com/'
        r'[A-Za-z0-9_]+/'
        r'status/'
        r'(\d{15,25})'
    )

    embedded_ids = re.findall(
        pattern,
        tweet_html,
        flags=re.IGNORECASE,
    )

    # Doppelte entfernen
    embedded_ids = list(
        dict.fromkeys(embedded_ids)
    )

    # Eigene ID entfernen
    referenced_ids = [
        value
        for value in embedded_ids
        if value != tweet_id
    ]

    print(
        "Eingebettete Tweet-IDs:",
        len(embedded_ids),
    )

    for value in embedded_ids:
        print(
            " -",
            value,
            "(eigener Tweet)"
            if value == tweet_id
            else "(verknüpfter Tweet)",
        )

    # ------------------------------------------------------
    # Quote / Repost anhand eingebetteter Tweets
    # ------------------------------------------------------

    if referenced_ids:

        print(
            "Typ: quote"
        )

        print(
            "Erkennung: verknüpfter Tweet gefunden"
        )

        return "quote"

    # ------------------------------------------------------
    # Keine weitere Tweet-ID
    # ------------------------------------------------------

    print(
        "Typ: original"
    )

    print(
        "Erkennung: keine weitere Tweet-ID gefunden"
    )

    return "original"
    # ------------------------------------------------------
    # Echte Quote-Tweet-Strukturen
    # ------------------------------------------------------

    quote_patterns = [
        r'"quoted_status"\s*:',
        r'"quoted_status_result"\s*:',
        r'"quoted_tweet"\s*:',
        r'"is_quote_status"\s*:\s*true',
    ]

    for pattern in quote_patterns:

        if re.search(
            pattern,
            html_lower,
            flags=re.IGNORECASE,
        ):

            print(
                "Typ: quote"
            )

            print(
                "Erkennung:",
                pattern,
            )

            return "quote"

    # ------------------------------------------------------
    # Kein eindeutiger Hinweis
    # ------------------------------------------------------

    print(
        "Typ: original"
    )

    print(
        "Erkennung: keine eindeutige "
        "Repost-/Quote-Struktur gefunden"
    )

    return "original"


# ==========================================================
# Tweet-Daten aus HTML
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

def extract_tweet_data(tweet_html, tweet_id):

    # ------------------------------------------------------
    # Tweet-Typ
    # ------------------------------------------------------

    tweet_type = detect_tweet_type(
        tweet_html,
        tweet_id,
    )

    # ------------------------------------------------------
    # Text
    # ------------------------------------------------------
    # ------------------------------------------------------
    # DEBUG: Relevante X-Strukturen anzeigen
    # ------------------------------------------------------

    print("")
    print("========== X-TWEET DEBUG ==========")

    debug_patterns = [
        r'"retweeted_status_id_str":"([^"]+)"',
        r'"retweeted_status_id":"([^"]+)"',
        r'"quoted_status_id_str":"([^"]+)"',
        r'"quoted_status_id":"([^"]+)"',
        r'"is_quote_status":(true|false)',
        r'"retweeted":(true|false)',
        r'"legacy":\{',
        r'"quoted_status":\{',
        r'"retweeted_status":\{',
        r'"full_text":"([^"]{1,200})"',
    ]

    for pattern in debug_patterns:
        matches = re.findall(
            pattern,
            tweet_html,
            flags=re.IGNORECASE,
        )

        if matches:
            print(
                f"DEBUG {pattern}:"
            )

            for match in matches[:10]:
                print(
                    "  ",
                    match,
                )

    print("========== END DEBUG ==========")

    
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
    # ======================================================
    # DEBUG: Profilseite auf Repost-/Quote-Hinweise prüfen
    # ======================================================

    print("")
    print("========== PROFIL DEBUG ==========")

    debug_terms = [
        "retweeted",
        "retweet",
        "repost",
        "quoted",
        "quote",
        "QuoteTweet",
        "retweeted_status",
        "quoted_status",
    ]

    profile_lower = profile_html.lower()

    for term in debug_terms:
        count = profile_lower.count(term.lower())

        print(
            f"{term}: {count} Treffer"
        )

    print("========== END PROFIL DEBUG ==========")

    
    tweet_ids = extract_tweet_ids(
        profile_html
    )
    print("")
    print("========== STRUKTURIERTER REPOST DEBUG ==========")
    
    # Alle Vorkommen von "retweeted_status" untersuchen
    matches = list(
        re.finditer(
            r"retweeted_status",
            profile_html,
            flags=re.IGNORECASE,
        )
    )
    
    print(
        f"Gefundene retweeted_status-Strukturen: {len(matches)}"
    )
    
    for index, match in enumerate(matches, start=1):
    
        start = max(0, match.start() - 300)
        end = min(
            len(profile_html),
            match.end() + 1500,
        )
    
        context = profile_html[start:end]
    
        # Tweet-IDs aus diesem Strukturblock holen
        context_ids = re.findall(
            r"\b\d{15,25}\b",
            context,
        )
    
        context_ids = list(
            dict.fromkeys(context_ids)
        )
    
        print("")
        print(
            f"--- retweeted_status #{index} ---"
        )
    
        print(
            "Gefundene IDs:",
            context_ids,
        )
    
        # Nur die ersten relevanten IDs ausgeben
        for value in context_ids[:10]:
            print(
                "  ID:",
                value,
            )
    
    print("")
    print("========== END STRUKTURIERTER REPOST DEBUG ==========")
    
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
