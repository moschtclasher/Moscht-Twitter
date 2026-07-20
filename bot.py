import html
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urljoin

USERNAME = "moscht_coc"
OUTPUT_FILE = "feed.xml"
MAX_POSTS = 15

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
]

USER_AGENT = (
    "Mozilla/5.0 (compatible; MoschtRSSBot/1.0; "
    "+https://github.com/moschtclasher/Moscht-Twitter)"
)

MEDIA_NAMESPACE = "http://search.yahoo.com/mrss/"
ET.register_namespace("media", MEDIA_NAMESPACE)


def download_feed(instance: str) -> bytes:
    url = f"{instance.rstrip('/')}/{USERNAME}/rss"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/rss+xml, application/xml, "
                "text/xml;q=0.9, */*;q=0.8"
            ),
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


def get_description_html(source_item: ET.Element) -> str:
    description_element = source_item.find("description")

    if description_element is None or description_element.text is None:
        return ""

    return description_element.text.strip()


def strip_html(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    return html.unescape(value).strip()


def extract_image_url(
    description_html: str,
    source_instance: str,
) -> str:
    if not description_html:
        return ""

    # Zuerst normale Bilder suchen.
    match = re.search(
        r'<img[^>]+src=["\']([^"\']+)["\']',
        description_html,
        flags=re.IGNORECASE,
    )

    # Falls es ein Video ist, kann ein Vorschaubild als poster vorliegen.
    if not match:
        match = re.search(
            r'<video[^>]+poster=["\']([^"\']+)["\']',
            description_html,
            flags=re.IGNORECASE,
        )

    if not match:
        return ""

    image_url = html.unescape(match.group(1)).strip()

    # Relative Nitter-Adresse in eine vollständige URL umwandeln.
    return urljoin(
        source_instance.rstrip("/") + "/",
        image_url,
    )


def convert_post_link(link: str, source_instance: str) -> str:
    if not link:
        return f"https://x.com/{USERNAME}"

    instance = source_instance.rstrip("/")

    if link.startswith(instance):
        return "https://x.com" + link[len(instance):]

    return link


def create_own_feed(
    source_instance: str,
    source_data: bytes,
) -> None:
    source_root = ET.fromstring(source_data)
    source_items = source_root.findall(".//item")[:MAX_POSTS]

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = (
        f"X-Posts von @{USERNAME}"
    )
    ET.SubElement(channel, "link").text = (
        f"https://x.com/{USERNAME}"
    )
    ET.SubElement(channel, "description").text = (
        f"Automatisch erzeugter RSS-Feed für @{USERNAME}"
    )
    ET.SubElement(channel, "language").text = "de"
    ET.SubElement(channel, "lastBuildDate").text = (
        format_datetime(datetime.now(timezone.utc))
    )
    ET.SubElement(channel, "generator").text = (
        f"GitHub Actions über {source_instance}"
    )

    image_count = 0

    for source_item in source_items:
        title = text_content(source_item.find("title"))
        description_html = get_description_html(source_item)
        description_text = strip_html(description_html)

        source_link = text_content(source_item.find("link"))
        link = convert_post_link(source_link, source_instance)

        guid = text_content(source_item.find("guid")) or link
        pub_date = text_content(source_item.find("pubDate"))

        image_url = extract_image_url(
            description_html,
            source_instance,
        )

        item = ET.SubElement(channel, "item")

        ET.SubElement(item, "title").text = html.unescape(
            title or f"Neuer Post von @{USERNAME}"
        )
        ET.SubElement(item, "description").text = description_text
        ET.SubElement(item, "link").text = link

        guid_element = ET.SubElement(item, "guid")
        guid_element.set("isPermaLink", "false")
        guid_element.text = guid

        if pub_date:
            ET.SubElement(item, "pubDate").text = pub_date

        if image_url:
            image_count += 1

            enclosure = ET.SubElement(item, "enclosure")
            enclosure.set("url", image_url)
            enclosure.set("type", "image/jpeg")
            enclosure.set("length", "0")

            media_content = ET.SubElement(
                item,
                f"{{{MEDIA_NAMESPACE}}}content",
            )
            media_content.set("url", image_url)
            media_content.set("medium", "image")
            media_content.set("type", "image/jpeg")

    ET.indent(rss, space="  ")

    tree = ET.ElementTree(rss)
    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )

    print(
        f"{OUTPUT_FILE} mit {len(source_items)} Beiträgen "
        f"und {image_count} Bildern erstellt."
    )


def main() -> None:
    try:
        instance, source_data = find_working_feed()
        create_own_feed(instance, source_data)

    except Exception as error:
        print(
            f"Abruf fehlgeschlagen: {error}",
            file=sys.stderr,
        )

        if os.path.exists(OUTPUT_FILE):
            print("Bestehende feed.xml bleibt unverändert.")
            return

        sys.exit(1)


if __name__ == "__main__":
    main()
