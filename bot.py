import re
import html
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error


# ==========================================================
# Konfiguration
# ==========================================================

USERNAME = "moscht_coc"

FEED_FILE = "feed.xml"
IMAGE_DIR = Path("images/moscht_coc")

PROFILE_URL = f"https://x.com/{USERNAME}"

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
]


# ==========================================================
# Nitter
# ==========================================================

def get_feed():

    errors = []

    for instance in NITTER_INSTANCES:

        url = f"{instance}/{USERNAME}/rss"

        print("")
        print(f"Teste {instance} ...")

        try:

            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(X11; Linux x86_64) "
                        "AppleWebKit/537.36 "
                        "Chrome/131 Safari/537.36"
                    )
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=30,
            ) as response:
            
                data = response.read()
            
            print("HTTP Status:", response.status)
            print("Antwortgröße:", len(data))
            print(
                "Content-Type:",
                response.headers.get("Content-Type")
            )
            
            if not data.strip():
            
                raise RuntimeError(
                    "Nitter lieferte eine leere Antwort."
                )
            
            # Prüfen, ob tatsächlich XML geliefert wurde
            try:
            
                ET.fromstring(data)
            
            except ET.ParseError as e:
            
                raise RuntimeError(
                    f"Nitter lieferte kein gültiges XML: {e}"
                )
            
            print(
                f"✅ Gültiger Nitter-RSS-Feed: "
                f"{instance}"
            )
            
            return data

        except Exception as e:

            error = (
                f"{instance}: {e}"
            )

            print(
                f"Fehler: {error}"
            )

            errors.append(error)

    raise RuntimeError(
        "Keine Nitter-Instanz lieferte "
        "einen gültigen Feed:\n\n"
        + "\n".join(errors)
    )


# ==========================================================
# Bilder
# ==========================================================

def extract_image_urls(item):

    urls = []

    # enclosure
    enclosure = item.find("enclosure")

    if enclosure is not None:

        url = enclosure.attrib.get(
            "url",
            "",
        )

        if url:
            urls.append(url)

    # media:content
    media = item.find(
        "{http://search.yahoo.com/mrss/}content"
    )

    if media is not None:

        url = media.attrib.get(
            "url",
            "",
        )

        if url and url not in urls:
            urls.append(url)

    return urls


def download_image(url, tweet_id, index):

    IMAGE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    clean_url = html.unescape(
        url.split("?")[0]
    )

    extension = Path(
        clean_url
    ).suffix.lower()

    if extension not in [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
    ]:
        extension = ".jpg"

    # Erstes Bild immer mit der normalen Tweet-ID
    if index == 0:

        filename = (
            f"{tweet_id}.jpg"
        )

    else:

        filename = (
            f"{tweet_id}_{index}"
            f"{extension}"
        )

    target = IMAGE_DIR / filename

    try:

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "Chrome/131 Safari/537.36"
                )
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:

            content = response.read()

        target.write_bytes(
            content
        )

        print(
            f"✅ Bild gespeichert: "
            f"{target} "
            f"({len(content)} Bytes)"
        )

        return target

    except Exception as e:

        print(
            f"❌ Bild konnte nicht geladen werden:"
            f" {url}"
        )

        print(e)

        return None


# ==========================================================
# Datum
# ==========================================================

def parse_date(value):

    if not value:
        return datetime.now(
            timezone.utc
        )

    try:

        from email.utils import (
            parsedate_to_datetime
        )

        dt = parsedate_to_datetime(
            value
        )

        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:

        print(
            f"⚠️ Datum konnte nicht gelesen "
            f"werden: {value}"
        )

        return datetime.now(
            timezone.utc
        )


# ==========================================================
# RSS verarbeiten
# ==========================================================

def parse_nitter_feed(data):

    root = ET.fromstring(data)

    items = root.findall(
        "./channel/item"
    )

    print(
        f"{len(items)} Beiträge von "
        f"@{USERNAME} gefunden."
    )

    return items


def create_rss_item(channel, source_item):

    guid = source_item.findtext(
        "guid",
        "",
    ).strip()

    if not guid:

        link = source_item.findtext(
            "link",
            "",
        )

        match = re.search(
            r"/status/(\d+)",
            link or "",
        )

        if match:
            guid = match.group(1)

    if not guid:
        return

    title = (
        source_item.findtext(
            "title",
            "",
        )
        or ""
    )

    description = (
        source_item.findtext(
            "description",
            "",
        )
        or ""
    )

    link = (
        source_item.findtext(
            "link",
            "",
        )
        or ""
    )

    pub_date = (
        source_item.findtext(
            "pubDate",
            "",
        )
        or ""
    )

    image_urls = extract_image_urls(
        source_item
    )

    downloaded_images = []

    for index, image_url in enumerate(
        image_urls
    ):

        image = download_image(
            image_url,
            guid,
            index,
        )

        if image:

            downloaded_images.append(
                image
            )

    item = ET.SubElement(
        channel,
        "item",
    )

    ET.SubElement(
        item,
        "title",
    ).text = re.sub(
        r"\s+",
        " ",
        title,
    ).strip()[:300]

    ET.SubElement(
        item,
        "description",
    ).text = description

    ET.SubElement(
        item,
        "link",
    ).text = link

    ET.SubElement(
        item,
        "guid",
        {
            "isPermaLink": "false"
        },
    ).text = guid

    ET.SubElement(
        item,
        "pubDate",
    ).text = pub_date

    for image in downloaded_images:

        public_url = (
            "https://moschtclasher.github.io/"
            "Moscht-Twitter/"
            "images/moscht_coc/"
            f"{image.name}"
        )

        if image.suffix.lower() == ".png":

            mime_type = "image/png"

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
# Feed erstellen
# ==========================================================

def create_feed(items):

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
        "GitHub Actions über Nitter"
    )

    for source_item in items:

        create_rss_item(
            channel,
            source_item,
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
        f"Nitter X Feed für @{USERNAME}"
    )

    print("=" * 60)

    try:

        data = get_feed()

        items = parse_nitter_feed(
            data
        )

        if not items:

            print(
                "⚠️ Keine Beiträge gefunden."
            )

            return

        create_feed(
            items
        )

        print("")
        print("✅ Fertig.")

    except Exception as e:

        print(
            f"❌ Abruf fehlgeschlagen: {e}"
        )

        print(
            f"Bestehende {FEED_FILE} "
            "bleibt unverändert."
        )


if __name__ == "__main__":

    main()
