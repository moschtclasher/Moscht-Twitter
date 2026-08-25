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

    # Doppelte IDs entfernen
    ids = list(dict.fromkeys(ids))

    print(
        f"Gefundene Tweet-IDs: {len(ids)}"
    )

    for tweet_id in ids:
        print(" -", tweet_id)

    return ids

# ==========================================================
# DEBUG: Alle "repost"-Vorkommen im Profil-HTML untersuchen
# ==========================================================

def debug_repost_context(profile_html):

    print("")
    print("=" * 60)
    print("========== REPOST CONTEXT DEBUG ==========")
    print("=" * 60)

    matches = list(
        re.finditer(
            r"repost",
            profile_html,
            flags=re.IGNORECASE,
        )
    )

    print(
        f'Gefundene "repost"-Vorkommen: {len(matches)}'
    )

    for index, match in enumerate(matches, start=1):

        print("")
        print("-" * 60)
        print(
            f"REPOST VORKOMMEN #{index}"
        )
        print("-" * 60)

        # --------------------------------------------------
        # Kontext um das "repost"-Vorkommen
        # --------------------------------------------------

        start = max(
            0,
            match.start() - 1500,
        )

        end = min(
            len(profile_html),
            match.end() + 3000,
        )

        context = profile_html[start:end]

        print("HTML-KONTEXT:")
        print(context)

        # --------------------------------------------------
        # Tweet-IDs aus diesem Kontext
        # --------------------------------------------------

        ids = re.findall(
            r"\b\d{15,25}\b",
            context,
        )

        ids = list(
            dict.fromkeys(ids)
        )

        print("")
        print("Gefundene IDs im Kontext:")

        if ids:

            for value in ids:
                print(
                    "  ",
                    value,
                )

        else:

            print(
                "  keine"
            )

        # --------------------------------------------------
        # X-Tweet-URLs
        # --------------------------------------------------

        tweet_urls = re.findall(
            r'https?://(?:www\.)?x\.com/'
            r'[A-Za-z0-9_]+/'
            r'status/'
            r'\d{15,25}',
            context,
            flags=re.IGNORECASE,
        )

        tweet_urls = list(
            dict.fromkeys(tweet_urls)
        )

        print("")
        print("Gefundene Tweet-URLs:")

        if tweet_urls:

            for url in tweet_urls:
                print(
                    "  ",
                    url,
                )

        else:

            print(
                "  keine"
            )

        # --------------------------------------------------
        # screen_name
        # --------------------------------------------------

        usernames = re.findall(
            r'"screen_name"\s*:\s*"([^"]+)"',
            context,
            flags=re.IGNORECASE,
        )

        usernames = list(
            dict.fromkeys(usernames)
        )

        print("")
        print("Gefundene screen_name-Werte:")

        if usernames:

            for username in usernames:
                print(
                    "  @",
                    username,
                    sep="",
                )

        else:

            print(
                "  keine"
            )

        # --------------------------------------------------
        # Benutzer-URLs
        # --------------------------------------------------

        user_urls = re.findall(
            r'https?://(?:www\.)?x\.com/'
            r'[A-Za-z0-9_]+',
            context,
            flags=re.IGNORECASE,
        )

        user_urls = list(
            dict.fromkeys(user_urls)
        )

        print("")
        print("Gefundene X-User-URLs:")

        if user_urls:

            for url in user_urls:
                print(
                    "  ",
                    url,
                )

        else:

            print(
                "  keine"
            )

    print("")
    print("=" * 60)
    print("========== END REPOST CONTEXT DEBUG ==========")
    print("=" * 60)

# ==========================================================
# DEBUG: Repost-Strukturen im Profil untersuchen
# ==========================================================

def debug_profile_reposts(profile_html, profile_tweet_ids):
    """
    Sucht die retweeted_status-Strukturen in der Profilantwort
    und zeigt die darin enthaltenen Tweet-/User-Daten.

    Diese Funktion verändert keine Daten und entscheidet auch
    noch nicht, ob etwas tatsächlich ein Repost ist.
    """

    print("")
    print("=" * 60)
    print("========== REPOST DEBUG ==========")
    print("=" * 60)

    matches = list(
        re.finditer(
            r'"retweeted_status"',
            profile_html,
            flags=re.IGNORECASE,
        )
    )

    print(
        f'Gefundene "retweeted_status"-Strukturen: {len(matches)}'
    )

    if not matches:
        print("Keine retweeted_status-Strukturen gefunden.")
        print("=" * 60)
        print("========== END REPOST DEBUG ==========")
        return

    for index, match in enumerate(matches, start=1):

        # --------------------------------------------------
        # Einen ausreichend großen Bereich um die Struktur
        # herum betrachten.
        # --------------------------------------------------

        start = max(
            0,
            match.start() - 1500,
        )

        end = min(
            len(profile_html),
            match.end() + 8000,
        )

        block = profile_html[start:end]

        print("")
        print("-" * 60)
        print(
            f"REPOST-BLOCK #{index}"
        )
        print("-" * 60)

        print(
            "Blockgröße:",
            len(block),
        )

        # --------------------------------------------------
        # Alle 15-25-stelligen Zahlen/IDs suchen
        # --------------------------------------------------

        ids = re.findall(
            r"\b\d{15,25}\b",
            block,
        )

        ids = list(
            dict.fromkeys(ids)
        )

        print("")
        print("Tweet-/Objekt-IDs:")

        for value in ids:

            marker = ""

            if value in profile_tweet_ids:
                marker = " <-- PROFIL-TWEET"

            print(
                f"  {value}{marker}"
            )

        # --------------------------------------------------
        # Usernames / screen_names
        # --------------------------------------------------

        usernames = re.findall(
            r'"screen_name"\s*:\s*"([^"]+)"',
            block,
            flags=re.IGNORECASE,
        )

        usernames = list(
            dict.fromkeys(usernames)
        )

        print("")
        print("screen_name:")

        if usernames:

            for username in usernames:
                print(
                    "  @",
                    username,
                    sep="",
                )

        else:

            print(
                "  keine gefunden"
            )

        # --------------------------------------------------
        # Relevante Struktur-Schlüssel
        # --------------------------------------------------

        structure_patterns = [
            r'"retweeted_status"',
            r'"retweeted_status_result"',
            r'"quoted_tweet"',
            r'"quoted_status"',
            r'"rest_id"\s*:',
            r'"legacy"\s*:',
            r'"full_text"\s*:',
            r'"user_results"\s*:',
            r'"core"\s*:',
            r'"result"\s*:',
            r'"user"\s*:',
        ]

        print("")
        print("Struktur-Hinweise:")

        for pattern in structure_patterns:

            count = len(
                re.findall(
                    pattern,
                    block,
                    flags=re.IGNORECASE,
                )
            )

            if count:

                print(
                    f"  {pattern}: {count}"
                )

        # --------------------------------------------------
        # Nach sichtbaren Repost-Hinweisen suchen
        # --------------------------------------------------

        text_patterns = [
            r'repost',
            r'retweet',
            r'reposted',
            r'reposted_by',
            r'retweeted_by',
            r'original',
        ]

        print("")
        print("Text-/Repost-Hinweise:")

        found_text_hint = False

        for pattern in text_patterns:

            matches_text = re.findall(
                pattern,
                block,
                flags=re.IGNORECASE,
            )

            if matches_text:

                found_text_hint = True

                print(
                    f'  "{pattern}": '
                    f'{len(matches_text)} Treffer'
                )

        if not found_text_hint:

            print(
                "  keine zusätzlichen Hinweise"
            )

        # --------------------------------------------------
        # Ausschnitt mit retweeted_status ausgeben
        # --------------------------------------------------

        context_start = max(
            0,
            match.start() - 500,
        )

        context_end = min(
            len(profile_html),
            match.end() + 3000,
        )

        context = profile_html[
            context_start:context_end
        ]

        print("")
        print("HTML-Ausschnitt:")
        print("-" * 60)

        print(context)

        print("-" * 60)

    print("")
    print("=" * 60)
    print("========== END REPOST DEBUG ==========")
    print("=" * 60)

# ==========================================================
# Tweet-Typen aus Profil-HTML bestimmen
# ==========================================================

def detect_profile_tweet_types(profile_html, tweet_ids):
    """
    Versucht, die Tweet-Typen anhand der X-Strukturen
    im Profil-HTML zu bestimmen.

    Wichtig:
    Ein Treffer von 'retweeted_status' irgendwo im
    Profil-HTML wird NICHT automatisch einem Tweet
    zugeordnet.

    Deshalb wird nur dann ein Typ gesetzt, wenn eine
    Tweet-ID in einem ausreichend kleinen JSON-Kontext
    zusammen mit eindeutigen Quote-/Retweet-Strukturen
    gefunden wird.
    """

    result = {
        tweet_id: "original"
        for tweet_id in tweet_ids
    }

    print("")
    print("========== PROFIL TWEET TYPEN ==========")

    # ------------------------------------------------------
    # Für jeden bekannten Profil-Tweet suchen wir seinen
    # direkten Kontext im HTML.
    # ------------------------------------------------------

    for tweet_id in tweet_ids:

        positions = [
            match.start()
            for match in re.finditer(
                re.escape(tweet_id),
                profile_html,
            )
        ]

        detected = "original"

        for position in positions:

            # Nicht den gesamten Profil-HTML-Bereich nehmen.
            # Ein kleiner Kontext verhindert möglichst,
            # dass benachbarte Tweets vermischt werden.
            start = max(
                0,
                position - 5000,
            )

            end = min(
                len(profile_html),
                position + 5000,
            )

            context = profile_html[
                start:end
            ]

            # --------------------------------------------------
            # Quote
            # --------------------------------------------------

            quote_patterns = [
                r'"quoted_tweet"\s*:',
                r'"quoted_tweet_result"\s*:',
                r'"quoted_status"\s*:',
                r'"quoted_status_result"\s*:',
                r'"is_quote_status"\s*:\s*true',
            ]

            if any(
                re.search(
                    pattern,
                    context,
                    flags=re.IGNORECASE,
                )
                for pattern in quote_patterns
            ):

                detected = "quote"
                break

            # --------------------------------------------------
            # Repost
            # --------------------------------------------------

            repost_patterns = [
                r'"retweeted_status"\s*:',
                r'"retweeted_status_result"\s*:',
                r'"retweeted_status_id_str"\s*:',
                r'"retweeted_status_id"\s*:',
            ]

            if any(
                re.search(
                    pattern,
                    context,
                    flags=re.IGNORECASE,
                )
                for pattern in repost_patterns
            ):

                detected = "repost"
                break

        result[tweet_id] = detected

        print(
            f"Profil-Typ {tweet_id}: {detected}"
        )

    print(
        "========== END PROFIL TWEET TYPEN =========="
    )

    return result

# ==========================================================
# Tweet-Typ erkennen
# ==========================================================

def detect_tweet_type(tweet_html, tweet_id):
    """
    Erkennt den Tweet-Typ anhand eindeutig vorhandener
    Strukturen im HTML der einzelnen Tweet-Seite.

    Wenn keine eindeutige Struktur vorhanden ist,
    wird der Tweet als original behandelt.
    """

    print("")
    print("========== X-TWEET DEBUG ==========")

    # ------------------------------------------------------
    # HTML normalisieren
    # ------------------------------------------------------

    html_lower = tweet_html.lower()

    # ------------------------------------------------------
    # Debug
    # ------------------------------------------------------

    debug_patterns = [
        r'"retweeted_status_id_str"\s*:\s*"([^"]+)"',
        r'"retweeted_status_id"\s*:\s*"([^"]+)"',
        r'"quoted_status_id_str"\s*:\s*"([^"]+)"',
        r'"quoted_status_id"\s*:\s*"([^"]+)"',
        r'"is_quote_status"\s*:\s*(true|false)',
        r'"quoted_status"\s*:',
        r'"quoted_status_result"\s*:',
        r'"quoted_tweet"\s*:',
        r'"retweeted_status"\s*:',
        r'"retweeted_status_result"\s*:',
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

    # ------------------------------------------------------
    # Quote Tweet
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
            tweet_html,
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
    # Retweet
    # ------------------------------------------------------

    repost_patterns = [
        r'"retweeted_status"\s*:',
        r'"retweeted_status_result"\s*:',
        r'"retweeted_status_id_str"\s*:',
        r'"retweeted_status_id"\s*:',
    ]

    for pattern in repost_patterns:

        if re.search(
            pattern,
            tweet_html,
            flags=re.IGNORECASE,
        ):

            print(
                "Typ: repost"
            )

            print(
                "Erkennung:",
                pattern,
            )

            return "repost"

    # ------------------------------------------------------
    # Original
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

def extract_tweet_data(
    tweet_html,
    tweet_id,
    detected_type=None,
):

    # ------------------------------------------------------
    # Tweet-Typ
    # ------------------------------------------------------

    if detected_type is not None:
    
        tweet_type = detected_type
    
    else:
    
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

    debug_repost_context(
        profile_html
    )
    debug_profile_reposts(
        profile_html,
        tweet_ids,
    )
    
    if not tweet_ids:
    
        raise RuntimeError(
            "Keine Tweet-IDs gefunden."
        )
    
    profile_tweet_types = detect_profile_tweet_types(
        profile_html,
        tweet_ids,
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
                detected_type=profile_tweet_types.get(
                    tweet_id,
                    "original",
                ),
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
