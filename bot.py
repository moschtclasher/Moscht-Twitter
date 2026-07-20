import html
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime

USERNAME = "moscht_coc"
OUTPUT_FILE = "feed.xml"
MAX_POSTS = 15

# Öffentliche Instanzen ändern sich häufig.
# Funktionierende Instanzen kannst du später hier ergänzen oder entfernen.
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
]

USER_AGENT = (
    "Mozilla/5.0 (compatible; MoschtRSSBot/1.0; "
    "+https://github.com/moschtclasher/Moscht-Twitter)"
)


def download_feed(instance: str) -> bytes:
    url = f"{instance.rstrip('/')}/{USERNAME}/rss"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        },
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")

        data = response.read()

        if not data:
            raise RuntimeError("Leere Antwort")

        return data


def find_working_feed() -> tuple[str, bytes]:
    errors = []

    for instance in NITTER_INSTANCES:
        try:
            print(f"Teste {instance} ...")
            data = download_feed(instance)

            # Prüfen, ob tatsächlich gültiges XML zurückkam.
            root = ET.fromstring(data)

            if root.tag.lower().endswith("html"):
                raise RuntimeError("HTML statt RSS erhalten")

            if not root.findall(".//item"):
                raise RuntimeError("Keine RSS-Einträge gefunden")

            print(f"Erfolgreich: {instance}")
            return instance, data

        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            RuntimeError,
            ET.ParseError,
        ) as error:
            message = f"{instance}: {error}"
            errors.append(message)
            print(f"Fehler: {message}")

    raise RuntimeError(
        "Keine Nitter-Instanz lieferte einen gültigen Feed:\n"
        + "\n".join(errors)
    )


def text_content(element: ET.Element | None) -> str:
    if element is None:
        return ""

    return "".join(element.itertext()).strip()


def create_own_feed(source_instance: str, source_data: bytes) -> None:
    source_root = ET.fromstring(source_data)
    source_items = source_root.findall(".//item")[:MAX_POSTS]

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = f"X-Posts von @{USERNAME}"
    ET.SubElement(channel, "link").text = f"https://x.com/{USERNAME}"
    ET.SubElement(channel, "description").text = (
        f"Automatisch erzeugter RSS-Feed für @{USERNAME}"
    )
    ET.SubElement(channel, "language").text = "de"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(
        datetime.now(timezone.utc)
    )
    ET.SubElement(channel, "generator").text = (
        f"GitHub Actions über {source_instance}"
    )

    for source_item in source_items:
        title = text_content(source_item.find("title"))
        description = text_content(source_item.find("description"))
        link = text_content(source_item.find("link"))
        guid = text_content(source_item.find("guid")) or link
        pub_date = text_content(source_item.find("pubDate"))

        item = ET.SubElement(channel, "item")

        ET.SubElement(item, "title").text = html.unescape(
            title or f"Neuer Post von @{USERNAME}"
        )
        ET.SubElement(item, "description").text = description
        ET.SubElement(item, "link").text = link

        guid_element = ET.SubElement(item, "guid")
        guid_element.set("isPermaLink", "false")
        guid_element.text = guid

        if pub_date:
            ET.SubElement(item, "pubDate").text = pub_date

    ET.indent(rss, space="  ")

    tree = ET.ElementTree(rss)
    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )

    print(f"{OUTPUT_FILE} mit {len(source_items)} Beiträgen erstellt.")


def main() -> None:
    try:
        instance, source_data = find_working_feed()
        create_own_feed(instance, source_data)

    except Exception as error:
        print(f"Abruf fehlgeschlagen: {error}", file=sys.stderr)

        # Bestehenden Feed nicht löschen oder überschreiben.
        if os.path.exists(OUTPUT_FILE):
            print("Bestehende feed.xml bleibt unverändert.")
            return

        sys.exit(1)


if __name__ == "__main__":
    main()
