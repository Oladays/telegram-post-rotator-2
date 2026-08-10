import os
import json
import random
import requests
import time

BOT_TOKEN = os.environ["BOT_TOKEN"]
NEW_CHANNEL_ID = str(os.environ["NEW_CHANNEL_ID"])
OLD_CHANNEL_ID = str(os.environ["OLD_CHANNEL_ID"])

POOL_FILE = "pool.json"
API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def telegram(method, data):
    response = requests.post(
        f"{API}/{method}",
        data=data,
        timeout=30
    )

    if not response.ok:
        print(f"Telegram HTTP error {response.status_code}: {response.text}")

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise Exception(f"Telegram API error: {result}")

    return result["result"]


def load_pool():
    if not os.path.exists(POOL_FILE):
        pool = {
            "last_update_id": 0,
            "last_posted_id": None,
            "last_posted_group_id": None,
            "messages": []
        }

        save_pool(pool)
        return pool

    with open(POOL_FILE, "r", encoding="utf-8") as f:
        pool = json.load(f)

    if "last_update_id" not in pool:
        pool["last_update_id"] = 0

    if "last_posted_id" not in pool:
        pool["last_posted_id"] = None

    if "last_posted_group_id" not in pool:
        pool["last_posted_group_id"] = None

    if "messages" not in pool:
        pool["messages"] = []

    return pool


def save_pool(pool):
    with open(POOL_FILE, "w", encoding="utf-8") as f:
        json.dump(
            pool,
            f,
            ensure_ascii=False,
            indent=2
        )


def get_media_info(message):

    if message.get("photo"):
        return message["photo"][-1]["file_id"], "photo"

    if message.get("video"):
        return message["video"]["file_id"], "video"

    if message.get("document"):
        return message["document"]["file_id"], "document"

    if message.get("animation"):
        return message["animation"]["file_id"], "animation"

    if message.get("audio"):
        return message["audio"]["file_id"], "audio"

    if message.get("voice"):
        return message["voice"]["file_id"], "voice"

    return None, None


def fetch_new_messages(pool):

    print("=" * 55)
    print("CHECKING FOR NEW TELEGRAM POSTS")
    print("=" * 55)

    last_update_id = pool.get("last_update_id", 0)

    print("Source channel:", NEW_CHANNEL_ID)
    print("Destination channel:", OLD_CHANNEL_ID)
    print("Last update ID:", last_update_id)

    params = {
        "offset": last_update_id + 1,
        "limit": 100,
        "timeout": 10,
        "allowed_updates": json.dumps(["channel_post"])
    }

    response = requests.get(
        f"{API}/getUpdates",
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise Exception(f"getUpdates failed: {data}")

    updates = data.get("result", [])

    print("Updates received:", len(updates))

    newest_update_id = last_update_id

    # --------------------------------------------------------
    # Temporary album collection.
    #
    # Telegram may deliver the pictures of one album as
    # separate updates. We collect them together here.
    # --------------------------------------------------------

    new_albums = {}

    for update in updates:

        update_id = update.get("update_id")

        if update_id is None:
            continue

        newest_update_id = max(
            newest_update_id,
            update_id
        )

        message = update.get("channel_post")

        if not message:
            continue

        chat_id = str(
            message.get("chat", {}).get("id")
        )

        # ONLY read from NEW CHANNEL
        if chat_id != NEW_CHANNEL_ID:
            print(
                "Skipping different channel:",
                chat_id
            )
            continue

        message_id = message.get("message_id")

        text = (
            message.get("text")
            or message.get("caption")
            or ""
        )

        file_id, media_type = get_media_info(message)

        media_group_id = message.get(
            "media_group_id"
        )

        # ====================================================
        # ALBUM
        # ====================================================

        if media_group_id:

            group_key = str(media_group_id)

            if group_key not in new_albums:
                new_albums[group_key] = []

            new_albums[group_key].append({
                "id": message_id,
                "file_id": file_id,
                "media_type": media_type,
                "text": text
            })

            print(
                f"Album item received: {message_id} "
                f"(group {group_key})"
            )

            continue

        # ====================================================
        # NORMAL SINGLE POST
        # ====================================================

        existing = any(
            str(item.get("id")) == str(message_id)
            for item in pool["messages"]
        )

        if existing:
            print(
                f"Message {message_id} already in pool."
            )
            continue

        if not text and not file_id:
            print(
                f"Skipping empty message {message_id}"
            )
            continue

        pool["messages"].append({
            "type": "single",
            "id": message_id,
            "text": text,
            "file_id": file_id,
            "media_type": media_type
        })

        print(
            f"NEW SINGLE POST ADDED: {message_id}"
        )

    # ========================================================
    # SAVE ALBUMS AS ONE POOL ITEM
    # ========================================================

    for group_id, items in new_albums.items():

        # Sort according to Telegram message ID
        items.sort(
            key=lambda x: int(x["id"])
        )

        # Check whether this album already exists
        album_exists = any(
            str(item.get("media_group_id"))
            == group_id
            for item in pool["messages"]
            if item.get("type") == "album"
        )

        if album_exists:
            print(
                f"Album {group_id} already exists."
            )
            continue

        # Use the first non-empty caption
        album_caption = ""

        for item in items:
            if item.get("text"):
                album_caption = item["text"]
                break

        album = {
            "type": "album",
            "id": f"album_{group_id}",
            "media_group_id": group_id,
            "text": album_caption,
            "items": items
        }

        pool["messages"].append(album)

        print("----------------------------------------")
        print(
            f"NEW ALBUM ADDED: {group_id}"
        )
        print(
            "Album items:",
            len(items)
        )
        print(
            "Caption:",
            album_caption[:150]
        )

    pool["last_update_id"] = newest_update_id

    print("----------------------------------------")
    print(
        "New last update ID:",
        pool["last_update_id"]
    )

    print(
        "Total pool items:",
        len(pool["messages"])
    )

    print("=" * 55)

    return pool


def send_single(message):

    message_id = message["id"]

    print(
        "Posting single message:",
        message_id
    )

    # First try copyMessage.
    try:

        telegram(
            "copyMessage",
            {
                "chat_id": OLD_CHANNEL_ID,
                "from_chat_id": NEW_CHANNEL_ID,
                "message_id": message_id
            }
        )

        print("Single message copied successfully.")

        return True

    except Exception as error:

        print(
            "copyMessage failed:",
            error
        )

    # Fallback
    text = message.get("text") or ""
    file_id = message.get("file_id")
    media_type = message.get("media_type")

    try:

        if media_type == "photo":

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "photo": file_id
            }

            if text:
                data["caption"] = text

            telegram("sendPhoto", data)

        elif media_type == "video":

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "video": file_id
            }

            if text:
                data["caption"] = text

            telegram("sendVideo", data)

        elif media_type == "document":

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "document": file_id
            }

            if text:
                data["caption"] = text

            telegram("sendDocument", data)

        elif media_type == "animation":

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "animation": file_id
            }

            if text:
                data["caption"] = text

            telegram("sendAnimation", data)

        elif media_type == "audio":

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "audio": file_id
            }

            if text:
                data["caption"] = text

            telegram("sendAudio", data)

        elif media_type == "voice":

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "voice": file_id
            }

            if text:
                data["caption"] = text

            telegram("sendVoice", data)

        else:

            telegram(
                "sendMessage",
                {
                    "chat_id": OLD_CHANNEL_ID,
                    "text": text
                }
            )

        print("Single message sent successfully.")

        return True

    except Exception as error:

        print(
            "Fallback failed:",
            error
        )

        return False


def send_album(album):

    items = album.get("items", [])

    if not items:
        print("Album contains no items.")

        return False

    print("=" * 55)
    print("POSTING ALBUM")
    print(
        "Album:",
        album.get("media_group_id")
    )
    print(
        "Items:",
        len(items)
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # We copy every Telegram message belonging to the album.
    #
    # This prevents one picture from being left behind and
    # later treated as a separate random post.
    # --------------------------------------------------------

    successful = 0

    for item in items:

        message_id = item["id"]

        try:

            telegram(
                "copyMessage",
                {
                    "chat_id": OLD_CHANNEL_ID,
                    "from_chat_id": NEW_CHANNEL_ID,
                    "message_id": message_id
                }
            )

            successful += 1

            print(
                f"Copied album item {message_id}"
            )

        except Exception as error:

            print(
                f"Failed album item {message_id}:",
                error
            )

    print(
        f"Album copied: {successful}/{len(items)}"
    )

    return successful == len(items)


def post_random_message(pool):

    if not pool["messages"]:

        print("No messages available.")

        return pool

    print("=" * 55)
    print("CHOOSING RANDOM POST")
    print("=" * 55)

    last_posted_id = pool.get(
        "last_posted_id"
    )

    # --------------------------------------------------------
    # Every album is ONE item in pool["messages"].
    #
    # Therefore the bot can never randomly select one
    # individual picture from an album.
    # --------------------------------------------------------

    available = [
        item
        for item in pool["messages"]
        if item.get("id") != last_posted_id
    ]

    if not available:

        available = pool["messages"]

    choice = random.choice(
        available
    )

    print(
        "Selected:",
        choice.get("id")
    )

    print(
        "Type:",
        choice.get("type")
    )

    # ========================================================
    # ALBUM
    # ========================================================

    if choice.get("type") == "album":

        success = send_album(
            choice
        )

    # ========================================================
    # SINGLE
    # ========================================================

    else:

        success = send_single(
            choice
        )

    if success:

        pool["last_posted_id"] = (
            choice.get("id")
        )

        if choice.get("type") == "album":

            pool["last_posted_group_id"] = (
                choice.get("media_group_id")
            )

        else:

            pool["last_posted_group_id"] = None

        print(
            "POSTED SUCCESSFULLY:",
            choice.get("id")
        )

    else:

        print(
            "POST FAILED."
        )

        print(
            "last_posted_id was NOT changed."
        )

    return pool


def main():

    pool = load_pool()

    # 1. Collect new posts
    pool = fetch_new_messages(
        pool
    )

    # 2. Choose ONE post
    pool = post_random_message(
        pool
    )

    # 3. Save the updated pool
    save_pool(
        pool
    )

    print("=" * 55)
    print("POOL SAVED")
    print("DONE")
    print("=" * 55)


if __name__ == "__main__":
    main()
