
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

STATE_FILE = Path("last_posts.json")
QUEUE_FILE = Path("x_recent_posts.json")
MAX_SENT_IDS = 500

FEEDS = [
    {
        "key": "moscht_coc",
        "old_key": "feed.xml",
        "webhook_env": "DISCORD_WEBHOOK_MOSCHT",
        "display_name": "Moscht Twitter/X",
        "avatar_url": "https://moschtclasher.github.io/Moscht-Twitter/images/confusion_avatar.png",
        "footer": "𝕏 • @moscht_coc",
        "color": 0xFFF533,
        "mention": "<@&1528735528772571137>",
        "emoji": "<a:blitzcnf:1475376256970260582>",
    },
    {
        "key": "confusion_coc",
        "old_key": "feed-confusion.xml",
        "webhook_env": "DISCORD_WEBHOOK_CONFUSION",
        "display_name": "CNF | Twitter/X",
        "avatar_url": "https://moschtclasher.github.io/Moscht-Twitter/images/confusion_avatar.png",
        "footer": "𝕏 • @Confusion_CoC",
        "color": 0xFFF533,
        "mention": "<@&1506407793866047579>",
        "emoji": "<a:blitzcnf:1475376256970260582>",
    },
    {
        "key": "twitch_lurmii",
        "old_key": "feed-lurmii.xml",
        "webhook_env": "DISCORD_WEBHOOK_LURMII",
        "display_name": "Lurmii Twitter/X",
        "avatar_url": "https://moschtclasher.github.io/Moscht-Twitter/images/confusion_avatar.png",
        "footer": "𝕏 • @Twitch_Lurmii",
        "color": 0xFFF533,
        "mention": "<@&1537072600948150352>",
        "emoji": "<a:blitzcnf:1475376256970260582>",
    },
    {
        "key": "clashwithwolfi",
        "old_key": "feed-wolfi.xml",
        "webhook_env": "DISCORD_WEBHOOK_WOLFI",
        "display_name": "Wolfi Twitter/X",
        "avatar_url": "https://moschtclasher.github.io/Moscht-Twitter/images/confusion_avatar.png",
        "footer": "𝕏 • @ClashWithWolfi",
        "color": 0xFFF533,
        "mention": "<@&1541713656839151696>",
        "emoji": "<a:CHEER:1541717896680706048>",
    },
]


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save_state(state):
    cleaned = {
        key: list(dict.fromkeys(str(x) for x in ids))[-MAX_SENT_IDS:]
        for key, ids in state.items()
    }
    STATE_FILE.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def migrate_state(raw_state):
    """Übernimmt auch den bisherigen Status mit RSS-Dateinamen."""
    if not isinstance(raw_state, dict):
        return {}

    state = {}

    for feed in FEEDS:
        current = raw_state.get(feed["key"], [])
        old = raw_state.get(feed["old_key"], [])

        if not isinstance(current, list):
            current = [current] if current else []
        if not isinstance(old, list):
            old = [old] if old else []

        state[feed["key"]] = list(
            dict.fromkeys(str(x) for x in old + current if x)
        )[-MAX_SENT_IDS:]

    return state


def parse_timestamp(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def create_embed(post, feed):
    text = re.sub(
        r"https?://\S+",
        "",
        post.get("text", "")
    ).strip()

    if not text:
        text = "Neuer X-Beitrag"

    text = text[:3800]
    description = f"{text}\n\n🔗 [Beitrag ansehen]({post['url']})"

    embed = {
        "description": description,
        "color": feed["color"],
        "footer": {"text": feed["footer"]},
    }

    timestamp = parse_timestamp(post.get("created_at", ""))
    if timestamp:
        embed["timestamp"] = timestamp

    images = post.get("images") or []
    if images:
        first_image = images[0]
        image_path = first_image.get("path", "")

        if image_path and Path(image_path).is_file():
            embed["image"] = {
                "url": f"attachment://{Path(image_path).name}"
            }
        elif first_image.get("url"):
            embed["image"] = {"url": first_image["url"]}

    return embed


def send_to_discord(post, feed):
    webhook = os.getenv(feed["webhook_env"], "").strip()

    if not webhook:
        print(f"❌ Secret {feed['webhook_env']} fehlt.")
        return False

    role_match = re.search(r"<@&(\d+)>", feed["mention"])
    role_ids = [role_match.group(1)] if role_match else []

    payload = {
        "username": feed["display_name"],
        "avatar_url": feed["avatar_url"],
        "content": f"{feed['mention']} {feed['emoji']}",
        "allowed_mentions": {
            "parse": [],
            "roles": role_ids,
        },
        "embeds": [create_embed(post, feed)],
    }

    images = post.get("images") or []
    image_path = None

    if images and images[0].get("path"):
        candidate = Path(images[0]["path"])
        if candidate.is_file():
            image_path = candidate

    try:
        if image_path:
            with image_path.open("rb") as image_file:
                response = requests.post(
                    webhook,
                    data={
                        "payload_json": json.dumps(
                            payload, ensure_ascii=False
                        )
                    },
                    files={
                        "files[0]": (
                            image_path.name,
                            image_file,
                        )
                    },
                    timeout=30,
                )
        else:
            response = requests.post(
                webhook,
                json=payload,
                timeout=30,
            )

        if 200 <= response.status_code < 300:
            print(f"✅ Gesendet: {post.get('id')}")
            return True

        print(
            f"❌ Discord HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )
        return False

    except requests.RequestException as exc:
        print(f"❌ Netzwerkfehler beim Discord-Versand: {exc}")
        return False


def main():
    print("=" * 60)
    print("Discord Poster gestartet")
    print("=" * 60)

    queue = load_json(QUEUE_FILE, {})
    state = migrate_state(load_json(STATE_FILE, {}))

    if not queue:
        print(
            f"❌ {QUEUE_FILE} fehlt oder ist leer. "
            "Zuerst müssen die vier Bot-Skripte laufen."
        )
        raise RuntimeError("Kein Discord-Beitragsverlauf vorhanden.")

    for feed in FEEDS:
        print(f"\n{'=' * 55}\n{feed['display_name']}\n{'=' * 55}")

        posts = queue.get(feed["key"], [])
        if not posts:
            print("Keine Beiträge im API-Verlauf.")
            continue
            
        sent_ids = {
            str(x) for x in state.get(feed["key"], [])
        }
        
        # Die höchste bereits gespeicherte X-Post-ID dient
        # als Grenze: Ältere Beiträge werden nicht nachträglich gesendet.
        numeric_sent_ids = [
            int(x) for x in sent_ids if x.isdigit()
        ]
        latest_known_id = max(numeric_sent_ids, default=0)
        
        unsent = []
        
        for post in posts:
            post_id = str(post.get("id", "")).strip()
        
            if not post_id or post_id in sent_ids:
                continue
        
            # Nur gültige numerische X-Post-IDs berücksichtigen.
            if not post_id.isdigit():
                continue
        
            # Keine älteren, bisher nicht gespeicherten Beiträge nachsenden.
            if int(post_id) <= latest_known_id:
                print(
                    f"⏭️ Älterer Beitrag übersprungen: {post_id}"
                )
                continue
        
            unsent.append(post)

        # Chronologisch senden: älteste neue Beiträge zuerst.
        unsent.sort(key=lambda post: post.get("created_at", ""))

        # Wenn für diesen Feed kein Versandstatus existiert,
        # nichts automatisch senden. Erst den Status sicher prüfen.
        if not state.get(feed["key"]):
            print(
                f"⚠️ Kein gespeicherter Status für {feed['key']}. "
                "Aus Sicherheitsgründen wird nichts gesendet."
            )
            continue

        print(f"Neue, noch nicht gesendete Beiträge: {len(unsent)}")

        for post in unsent:
            if send_to_discord(post, feed):
                state.setdefault(feed["key"], []).append(
                    str(post["id"])
                )
                state[feed["key"]] = list(
                    dict.fromkeys(state[feed["key"]])
                )[-MAX_SENT_IDS:]
                save_state(state)
            else:
                # Bei einem Fehler hier stoppen, damit die Reihenfolge
                # erhalten bleibt und der Beitrag erneut versucht wird.
                print(
                    f"⚠️ {post.get('id')} bleibt offen. "
                    "Versuch beim nächsten Lauf erneut."
                )
                break

    save_state(state)
    print("\nDiscord-Poster fertig.")


if __name__ == "__main__":
    main()
