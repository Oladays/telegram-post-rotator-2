import os
import json
import random
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]
NEW_CHANNEL_ID = str(os.environ["NEW_CHANNEL_ID"])
OLD_CHANNEL_ID = str(os.environ["OLD_CHANNEL_ID"])

POOL_FILE = "pool.json"
API = f"https://api.telegram.org/bot{BOT_TOKEN}"


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


def load_pool():

    if not os.path.exists(POOL_FILE):

        return {
            "last_update_id": 0,
            "last_posted_id": None,
            "messages": []
        }

    with open(POOL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


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
        photo = message["photo"][-1]
        return photo["file_id"], "photo"

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
    print("TELEGRAM POST ROTATOR")
    print("=" * 55)

    print("CHECKING SOURCE CHANNEL")
    print("Source:", NEW_CHANNEL_ID)
    print("Destination:", OLD_CHANNEL_ID)

    last_update_id = pool.get(
        "last_update_id",
        0
    )

    print("Last update:", last_update_id)

    offset = last_update_id + 1

    updates = telegram(
        "getUpdates",
        offset=offset,
        limit=100,
        allowed_updates=["channel_post"]
    )

    print("Updates received:", len(updates))

    newest_update_id = last_update_id

    for update in updates:

        update_id = update.get("update_id")

        if update_id is None:
            continue

        # ALWAYS move the update pointer forward.
        newest_update_id = max(
            newest_update_id,
            update_id
        )

        post = update.get("channel_post")

        if not post:
            continue

        chat = post.get("chat", {})
        chat_id = str(chat.get("id"))

        print("----------------------------------------")
        print("Channel:", chat_id)
        print("Message ID:", post.get("message_id"))

        # ONLY FETCH FROM NEW CHANNEL
        if chat_id != NEW_CHANNEL_ID:

            print("Skipped: different channel")
            continue

        message_id = post.get("message_id")

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

        text = (
            post.get("text")
            or post.get("caption")
            or ""
        )

        file_id, media_type = get_media_info(post)

        # Ignore completely empty posts
        if not text and not file_id:

            print("Skipped: empty post")
            continue

        new_message = {
            "id": message_id,
            "text": text,
            "file_id": file_id,
            "media_type": media_type
        }

        pool["messages"].append(new_message)

        print("NEW POST ADDED:", message_id)
        print(
            "Type:",
            media_type or "text"
        )
        print(
            "Text:",
            text[:150]
        )

    # IMPORTANT:
    # Save the newest Telegram update we processed.
    pool["last_update_id"] = newest_update_id

    print("----------------------------------------")
    print(
        "Updated last_update_id:",
        pool["last_update_id"]
    )

    print(
        "Pool size:",
        len(pool["messages"])
    )

    print("=" * 55)

    return pool


def send_message(message):

    message_id = message["id"]

    print("=" * 55)
    print("POSTING TO OLD CHANNEL")
    print("Message:", message_id)
    print("Destination:", OLD_CHANNEL_ID)

    # Try copyMessage first.
    try:

        result = telegram(
            "copyMessage",
            chat_id=OLD_CHANNEL_ID,
            from_chat_id=NEW_CHANNEL_ID,
            message_id=message_id
        )

        print(
            "copyMessage successful:",
            result.get("message_id")
        )

        return True

    except Exception as error:

        print("copyMessage failed:")
        print(error)

    # Fallback to direct media sending.

    text = message.get("text") or ""
    file_id = message.get("file_id")
    media_type = message.get("media_type")

    if not file_id:

        if not text:
            print("Nothing to send.")
            return False

        telegram(
            "sendMessage",
            chat_id=OLD_CHANNEL_ID,
            text=text
        )

        print("Text message sent successfully.")

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

            print("Unknown media type.")
            return False

        print("Direct media send successful.")

        return True

    except Exception as error:

        print("Direct media send failed:")
        print(error)

        return False


def post_random_message(pool):

    if not pool["messages"]:

        print("No messages available.")
        return pool

    print("=" * 55)
    print("CHOOSING A RANDOM POST")

    last_posted_id = pool.get(
        "last_posted_id"
    )

    available = [
        message
        for message in pool["messages"]
        if str(message.get("id"))
        != str(last_posted_id)
    ]

    if not available:

        available = pool["messages"]

    choice = random.choice(
        available
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
        (choice.get("text") or "")[:150]
    )

    success = send_message(choice)

    if success:

        pool["last_posted_id"] = choice["id"]

        print(
            "POSTED SUCCESSFULLY:",
            choice["id"]
        )

    else:

        print(
            "POST FAILED."
        )

    return pool


def main():

    pool = load_pool()

    pool = fetch_new_messages(pool)

    pool = post_random_message(pool)

    save_pool(pool)

    print("=" * 55)
    print("DONE")
    print("=" * 55)


if __name__ == "__main__":
    main()
