import os
import json
import random
import requests


BOT_TOKEN = os.environ["BOT_TOKEN"]
NEW_CHANNEL_ID = str(os.environ["NEW_CHANNEL_ID"])
OLD_CHANNEL_ID = str(os.environ["OLD_CHANNEL_ID"])

POOL_FILE = "pool.json"

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ============================================================
# TELEGRAM API
# ============================================================

def telegram(method, **kwargs):

    response = requests.post(
        f"{API}/{method}",
        json=kwargs,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(
            f"Telegram API error: {data}"
        )

    return data["result"]


# ============================================================
# POOL
# ============================================================

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

    with open(
        POOL_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        pool = json.load(f)

    # Make sure older pool files get the new fields
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

    with open(
        POOL_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            pool,
            f,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# MEDIA INFORMATION
# ============================================================

def get_media_info(message):

    if message.get("photo"):

        photo = message["photo"][-1]

        return (
            photo["file_id"],
            "photo"
        )

    if message.get("video"):

        return (
            message["video"]["file_id"],
            "video"
        )

    if message.get("document"):

        return (
            message["document"]["file_id"],
            "document"
        )

    if message.get("animation"):

        return (
            message["animation"]["file_id"],
            "animation"
        )

    if message.get("audio"):

        return (
            message["audio"]["file_id"],
            "audio"
        )

    if message.get("voice"):

        return (
            message["voice"]["file_id"],
            "voice"
        )

    return None, None


# ============================================================
# FETCH NEW POSTS FROM NEW CHANNEL
# ============================================================

def fetch_new_messages(pool):

    print("=" * 55)
    print("TELEGRAM POST ROTATOR")
    print("=" * 55)

    print("CHECKING SOURCE CHANNEL")
    print("Source:", NEW_CHANNEL_ID)
    print("Destination:", OLD_CHANNEL_ID)

    last_update_id = pool.get(
        "last_update_id",
        0
    )

    print(
        "Last update:",
        last_update_id
    )

    offset = last_update_id + 1

    updates = telegram(
        "getUpdates",
        offset=offset,
        limit=100,
        allowed_updates=["channel_post"]
    )

    print(
        "Updates received:",
        len(updates)
    )

    print(
        "Pool size before:",
        len(pool["messages"])
    )

    newest_update_id = last_update_id

    for update in updates:

        update_id = update.get(
            "update_id"
        )

        if update_id is None:
            continue

        # Always move the pointer forward
        newest_update_id = max(
            newest_update_id,
            update_id
        )

        post = update.get(
            "channel_post"
        )

        if not post:
            continue

        chat = post.get(
            "chat",
            {}
        )

        chat_id = str(
            chat.get("id")
        )

        message_id = post.get(
            "message_id"
        )

        print("----------------------------------------")
        print("Channel:", chat_id)
        print("Message ID:", message_id)

        # ONLY FETCH FROM NEW CHANNEL
        if chat_id != NEW_CHANNEL_ID:

            print(
                "Skipped: different channel"
            )

            continue

        if message_id is None:
            continue

        # Don't add duplicates
        existing_ids = {
            str(item.get("id"))
            for item in pool["messages"]
        }

        if str(message_id) in existing_ids:

            print(
                "Already in pool:",
                message_id
            )

            continue

        # Text or caption
        text = (
            post.get("text")
            or post.get("caption")
            or ""
        )

        # Media
        file_id, media_type = get_media_info(
            post
        )

        # Telegram album ID
        media_group_id = post.get(
            "media_group_id"
        )

        # Ignore completely empty messages
        if not text and not file_id:

            print(
                "Skipped: empty post"
            )

            continue

        new_message = {
            "id": message_id,
            "text": text,
            "file_id": file_id,
            "media_type": media_type,
            "media_group_id": media_group_id
        }

        pool["messages"].append(
            new_message
        )

        print(
            "NEW POST ADDED:",
            message_id
        )

        print(
            "Type:",
            media_type or "text"
        )

        print(
            "Media group:",
            media_group_id or "None"
        )

        print(
            "Text:",
            text[:150]
        )

    # IMPORTANT
    # Move update pointer only after processing everything
    pool["last_update_id"] = newest_update_id

    print("----------------------------------------")

    print(
        "Updated last_update_id:",
        pool["last_update_id"]
    )

    print(
        "Pool size after:",
        len(pool["messages"])
    )

    print("=" * 55)

    return pool


# ============================================================
# SEND NORMAL SINGLE MESSAGE
# ============================================================

def send_message(message):

    message_id = message["id"]

    print("=" * 55)
    print("POSTING SINGLE MESSAGE")
    print(
        "Message:",
        message_id
    )

    print(
        "Destination:",
        OLD_CHANNEL_ID
    )

    # --------------------------------------------------------
    # Try copyMessage first
    # --------------------------------------------------------

    try:

        result = telegram(
            "copyMessage",
            chat_id=OLD_CHANNEL_ID,
            from_chat_id=NEW_CHANNEL_ID,
            message_id=message_id
        )

        print(
            "copyMessage successful."
        )

        print(
            "New message ID:",
            result.get("message_id")
        )

        return True

    except Exception as error:

        print(
            "copyMessage failed:"
        )

        print(error)

    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------

    text = message.get(
        "text"
    ) or ""

    file_id = message.get(
        "file_id"
    )

    media_type = message.get(
        "media_type"
    )

    if not file_id:

        if not text:

            print(
                "Nothing to send."
            )

            return False

        telegram(
            "sendMessage",
            chat_id=OLD_CHANNEL_ID,
            text=text
        )

        print(
            "Text message sent successfully."
        )

        return True

    try:

        if media_type == "photo":

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "photo": file_id
            }

            if text:
                data["caption"] = text

            telegram(
                "sendPhoto",
                **data
            )

        elif media_type == "video":

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "video": file_id
            }

            if text:
                data["caption"] = text

            telegram(
                "sendVideo",
                **data
            )

        elif media_type == "document":

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "document": file_id
            }

            if text:
                data["caption"] = text

            telegram(
                "sendDocument",
                **data
            )

        elif media_type == "animation":

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "animation": file_id
            }

            if text:
                data["caption"] = text

            telegram(
                "sendAnimation",
                **data
            )

        elif media_type == "audio":

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "audio": file_id
            }

            if text:
                data["caption"] = text

            telegram(
                "sendAudio",
                **data
            )

        elif media_type == "voice":

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "voice": file_id
            }

            if text:
                data["caption"] = text

            telegram(
                "sendVoice",
                **data
            )

        else:

            print(
                "Unknown media type."
            )

            return False

        print(
            "Direct media send successful."
        )

        return True

    except Exception as error:

        print(
            "Direct media send failed:"
        )

        print(error)

        return False


# ============================================================
# SEND ALBUM / MULTIPLE PICTURES
# ============================================================

def send_album(album):

    print("=" * 55)
    print("POSTING ALBUM")
    print(
        "Pictures:",
        len(album)
    )

    print(
        "Destination:",
        OLD_CHANNEL_ID
    )

    media = []

    for index, message in enumerate(album):

        file_id = message.get(
            "file_id"
        )

        media_type = message.get(
            "media_type"
        )

        text = message.get(
            "text"
        ) or ""

        if not file_id:
            continue

        # Telegram media groups support photo/video
        if media_type not in (
            "photo",
            "video"
        ):

            print(
                "Skipping unsupported album media:",
                media_type
            )

            continue

        item = {
            "type": media_type,
            "media": file_id
        }

        # Caption goes on the first item
        if index == 0 and text:

            item["caption"] = text

        media.append(
            item
        )

    if not media:

        print(
            "No usable album media."
        )

        return False

    try:

        result = telegram(
            "sendMediaGroup",
            chat_id=OLD_CHANNEL_ID,
            media=json.dumps(media)
        )

        print(
            "ALBUM POSTED SUCCESSFULLY."
        )

        print(
            "Items sent:",
            len(result)
        )

        return True

    except Exception as error:

        print(
            "Album posting failed:"
        )

        print(error)

        return False


# ============================================================
# RANDOM POST SELECTION
# ============================================================

def post_random_message(pool):

    if not pool["messages"]:

        print(
            "No messages available."
        )

        return pool

    print("=" * 55)
    print("CHOOSING A RANDOM POST")

    last_posted_id = pool.get(
        "last_posted_id"
    )

    last_posted_group_id = pool.get(
        "last_posted_group_id"
    )

    # --------------------------------------------------------
    # Build groups that have already been posted
    # --------------------------------------------------------

    available = []

    for message in pool["messages"]:

        message_id = str(
            message.get("id")
        )

        group_id = message.get(
            "media_group_id"
        )

        # Don't immediately post the exact same message
        if (
            last_posted_id is not None
            and message_id == str(last_posted_id)
        ):
            continue

        # Don't pick another picture from the album
        # that was just posted
        if (
            group_id
            and last_posted_group_id
            and str(group_id)
            == str(last_posted_group_id)
        ):
            continue

        available.append(
            message
        )

    # If everything was filtered out,
    # allow the pool again
    if not available:

        available = pool["messages"]

    choice = random.choice(
        available
    )

    media_group_id = choice.get(
        "media_group_id"
    )

    # ========================================================
    # ALBUM
    # ========================================================

    if media_group_id:

        album = [
            message
            for message in pool["messages"]
            if str(
                message.get("media_group_id")
            )
            == str(media_group_id)
        ]

        # Keep original Telegram order
        album.sort(
            key=lambda x: int(
                x["id"]
            )
        )

        print("----------------------------------------")

        print(
            "ALBUM DETECTED"
        )

        print(
            "Media group:",
            media_group_id
        )

        print(
            "Pictures:",
            len(album)
        )

        success = send_album(
            album
        )

        if success:

            # Store the whole album as posted
            pool["last_posted_id"] = album[-1]["id"]

            pool["last_posted_group_id"] = (
                media_group_id
            )

            print(
                "Album marked as posted."
            )

        else:

            print(
                "Album failed."
            )

        return pool

    # ========================================================
    # NORMAL SINGLE POST
    # ========================================================

    print("----------------------------------------")

    print(
        "SINGLE POST"
    )

    print(
        "Selected message:",
        choice["id"]
    )

    print(
        "Type:",
        choice.get("media_type")
    )

    print(
        "Text:",
        (
            choice.get("text")
            or ""
        )[:150]
    )

    success = send_message(
        choice
    )

    if success:

        pool["last_posted_id"] = (
            choice["id"]
        )

        pool["last_posted_group_id"] = None

        print(
            "POSTED SUCCESSFULLY:",
            choice["id"]
        )

    else:

        print(
            "Post failed."
        )

    return pool


# ============================================================
# MAIN
# ============================================================

def main():

    pool = load_pool()

    # Fetch new posts from NEW CHANNEL
    pool = fetch_new_messages(
        pool
    )

    # Randomly select and post to OLD CHANNEL
    pool = post_random_message(
        pool
    )

    # Save everything
    save_pool(
        pool
    )

    print("=" * 55)
    print("POOL SAVED SUCCESSFULLY")
    print("DONE")
    print("=" * 55)


if __name__ == "__main__":

    main()
