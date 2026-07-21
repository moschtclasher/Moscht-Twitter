import html
import mimetypes
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

USERNAME = "Confusion_CoC"
OUTPUT_FILE = "feed-confusion.xml"
MAX_POSTS = 15

# An deine GitHub-Daten angepasst
GITHUB_USERNAME = "moschtclasher"
GITHUB_REPOSITORY = "Moscht-Twitter"

PAGES_BASE_URL = (
    f"https://{GITHUB_USERNAME}.github.io/{GITHUB_REPOSITORY}"
)

IMAGES_DIRECTORY = Path("images/confusion_coc")

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
]

USER_AGENT = (
    "Mozilla/5.0 (compatible; MoschtRSSBot/1.0; "
    f"+https://github.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY})"
)

MEDIA_NAMESPACE = "http://search.yahoo.com/mrss/"
ET.register_namespace("media", MEDIA_NAMESPACE)


def create_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/rss+xml, application/xml, "
                "text/xml, image/avif, image/webp, "
                "image/apng, image/*, */*;q=0.8"
            ),
        },
    )


def download_feed(instance: str) -> bytes:
    url = f"{instance.rstrip('/')}/{USERNAME}/rss"

    with urllib.request.urlopen(
        create_request(url),
        timeout=25,
    ) as response:
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
    element = source_item.find("description")

    if element is None or element.text is None:
        return ""

    return element.text.strip()


def strip_html(value: str) -> str:
    value = re.sub(
        r"<br\s*/?>",
        "\n",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"<[^>]+>", "", value)

    return html.unescape(value).strip()


def extract_image_url(
    description_html: str,
    source_instance: str,
) -> str:
    if not description_html:
        return ""

    match = re.search(
        r'<img[^>]+src=["\']([^"\']+)["\']',
        description_html,
        flags=re.IGNORECASE,
    )

    # Vorschaubild eines Videos
    if not match:
        match = re.search(
            r'<video[^>]+poster=["\']([^"\']+)["\']',
            description_html,
            flags=re.IGNORECASE,
        )

    if not match:
        return ""

    image_url = html.unescape(match.group(1)).strip()

    return urljoin(
        source_instance.rstrip("/") + "/",
        image_url,
    )


def normalize_post_link(
    link: str,
    source_instance: str,
) -> str:
    if not link:
        return f"https://x.com/{USERNAME}"

    instance = source_instance.rstrip("/")

    if link.startswith(instance):
        link = "https://x.com" + link[len(instance):]

    # Nitter hängt teilweise #m an
    return link.removesuffix("#m")


def safe_post_id(guid: str, link: str) -> str:
    candidate = guid or link

    status_match = re.search(
        r"/status/(\d+)",
        candidate,
    )

    if status_match:
        return status_match.group(1)

    cleaned = re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        candidate,
    )

    return cleaned[:100] or "unknown"


def extension_from_response(
    image_url: str,
    content_type: str,
) -> str:
    normalized_type = content_type.split(";")[0].strip().lower()

    known_extensions = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/avif": ".avif",
    }

    if normalized_type in known_extensions:
        return known_extensions[normalized_type]

    guessed = mimetypes.guess_extension(normalized_type)

    if guessed:
        return ".jpg" if guessed == ".jpe" else guessed

    path_extension = Path(
        urlparse(image_url).path
    ).suffix.lower()

    if path_extension in {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".avif",
    }:
        return ".jpg" if path_extension == ".jpeg" else path_extension

    return ".jpg"


def download_image(
    image_url: str,
    post_id: str,
) -> tuple[str, str] | None:
    try:
        with urllib.request.urlopen(
            create_request(image_url),
            timeout=30,
        ) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")

            content_type = response.headers.get(
                "Content-Type",
                "image/jpeg",
            )

            if not content_type.lower().startswith("image/"):
                raise RuntimeError(
                    f"Kein Bild erhalten: {content_type}"
                )

            data = response.read()

            if not data:
                raise RuntimeError("Leere Bilddatei")

        extension = extension_from_response(
            image_url,
            content_type,
        )

        filename = f"{post_id}{extension}"
        output_path = IMAGES_DIRECTORY / filename
        output_path.write_bytes(data)

        public_url = (
            f"{PAGES_BASE_URL}/{output_path.as_posix()}"
        )

        print(
            f"Bild gespeichert: {output_path} "
            f"({len(data)} Bytes)"
        )

        return public_url, content_type.split(";")[0]

    except (
        urllib.error.HTTPError,
        urllib.error.URLError,
        TimeoutError,
        RuntimeError,
        OSError,
    ) as error:
        print(
            f"Bild konnte nicht geladen werden: "
            f"{image_url}: {error}"
        )
        return None


def prepare_images_directory() -> None:
    # Der Ordner wird bei jedem Lauf neu aufgebaut.
    # Dadurch sammeln sich nicht unbegrenzt alte Bilder an.
    if IMAGES_DIRECTORY.exists():
        shutil.rmtree(IMAGES_DIRECTORY)

    IMAGES_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )


def create_own_feed(
    source_instance: str,
    source_data: bytes,
) -> None:
    source_root = ET.fromstring(source_data)
    source_items = source_root.findall(".//item")[:MAX_POSTS]

    prepare_images_directory()

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(
        channel,
        "title",
    ).text = f"X-Posts von @{USERNAME}"

    ET.SubElement(
        channel,
        "link",
    ).text = f"https://x.com/{USERNAME}"

    ET.SubElement(
        channel,
        "description",
    ).text = (
        f"Automatisch erzeugter RSS-Feed für @{USERNAME}"
    )

    ET.SubElement(channel, "language").text = "de"

    ET.SubElement(
        channel,
        "lastBuildDate",
    ).text = format_datetime(
        datetime.now(timezone.utc)
    )

    ET.SubElement(
        channel,
        "generator",
    ).text = (
        f"GitHub Actions über {source_instance}"
    )

    image_count = 0

    for source_item in source_items:
        title = text_content(
            source_item.find("title")
        )

        description_html = get_description_html(
            source_item
        )
        description_text = strip_html(
            description_html
        )

        original_link = text_content(
            source_item.find("link")
        )
        link = normalize_post_link(
            original_link,
            source_instance,
        )

        guid = (
            text_content(source_item.find("guid"))
            or link
        )

        pub_date = text_content(
            source_item.find("pubDate")
        )

        post_id = safe_post_id(guid, link)

        original_image_url = extract_image_url(
            description_html,
            source_instance,
        )

        public_image_url = ""
        image_content_type = "image/jpeg"

        if original_image_url:
            downloaded = download_image(
                original_image_url,
                post_id,
            )

            if downloaded:
                public_image_url = downloaded[0]
                image_content_type = downloaded[1]
                image_count += 1

        item = ET.SubElement(channel, "item")

        ET.SubElement(
            item,
            "title",
        ).text = html.unescape(
            title or f"Neuer Post von @{USERNAME}"
        )

        ET.SubElement(
            item,
            "description",
        ).text = description_text

        ET.SubElement(item, "link").text = link

        guid_element = ET.SubElement(
            item,
            "guid",
        )
        guid_element.set(
            "isPermaLink",
            "false",
        )
        guid_element.text = guid

        if pub_date:
            ET.SubElement(
                item,
                "pubDate",
            ).text = pub_date

        if public_image_url:
            image_path = IMAGES_DIRECTORY / Path(public_image_url).name
            image_size = image_path.stat().st_size

            enclosure = ET.SubElement(
                item,
                "enclosure",
            )
            enclosure.set(
                "url",
                public_image_url,
            )
            enclosure.set(
                "type",
                image_content_type,
            )
            enclosure.set(
                "length",
                str(image_size),
            )

            media_content = ET.SubElement(
                item,
                f"{{{MEDIA_NAMESPACE}}}content",
            )
            media_content.set(
                "url",
                public_image_url,
            )
            media_content.set(
                "medium",
                "image",
            )
            media_content.set(
                "type",
                image_content_type,
            )

    ET.indent(rss, space="  ")

    tree = ET.ElementTree(rss)
    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )

    print(
        f"{OUTPUT_FILE} mit {len(source_items)} Beiträgen "
        f"und {image_count} lokal gespeicherten Bildern erstellt."
    )


def main() -> None:
    try:
        instance, source_data = find_working_feed()
        create_own_feed(
            instance,
            source_data,
        )

    except Exception as error:
        print(
            f"Abruf fehlgeschlagen: {error}",
            file=sys.stderr,
        )

        if os.path.exists(OUTPUT_FILE):
            print(
                "Bestehende feed.xml bleibt unverändert."
            )
            return

        sys.exit(1)


if __name__ == "__main__":
    main()
