import os
import json
import random
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]
NEW_CHANNEL_ID = str(os.environ["NEW_CHANNEL_ID"])
OLD_CHANNEL_ID = str(os.environ["OLD_CHANNEL_ID"])

POOL_FILE = "pool.json"
API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def telegram(method, data):
    url = f"{API}/{method}"
    response = requests.post(url, data=data, timeout=30)

    if not response.ok:
        print(f"Telegram error {response.status_code}: {response.text}")

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
            "messages": []
        }
        save_pool(pool)
        return pool

    with open(POOL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_pool(pool):
    with open(POOL_FILE, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)


def get_media_info(message):
    """
    Extract the media file_id and media type from a Telegram channel post.
    """

    if message.get("photo"):
        # Use the largest photo size
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
    print("========================================")
    print("Checking Telegram for new channel posts...")
    print(f"Last update ID: {pool.get('last_update_id', 0)}")

    params = {
        "offset": pool.get("last_update_id", 0) + 1,
        "timeout": 10,
        "allowed_updates": json.dumps(["channel_post"])
    }

    result = requests.get(
        f"{API}/getUpdates",
        params=params,
        timeout=30
    )

    if not result.ok:
        print("getUpdates error:", result.text)
        result.raise_for_status()

    data = result.json()

    if not data.get("ok"):
        raise Exception(f"getUpdates failed: {data}")

    updates = data.get("result", [])

    print(f"Updates received: {len(updates)}")
    print(f"Pool size before: {len(pool['messages'])}")

    for update in updates:
        update_id = update["update_id"]

        # Always move the update pointer forward
        if update_id > pool.get("last_update_id", 0):
            pool["last_update_id"] = update_id

        message = update.get("channel_post")

        if not message:
            continue

        chat = message.get("chat", {})
        chat_id = str(chat.get("id"))

        # Only collect posts from the configured source channel
        if chat_id != NEW_CHANNEL_ID:
            print(f"Skipping post from channel {chat_id}")
            continue

        message_id = message.get("message_id")

        # Don't add the same Telegram message twice
        already_exists = any(
            str(item.get("id")) == str(message_id)
            for item in pool["messages"]
        )

        if already_exists:
            print(f"Message {message_id} already in pool.")
            continue

        text = message.get("text") or message.get("caption") or ""

        file_id, media_type = get_media_info(message)

        item = {
            "id": message_id,
            "text": text,
            "file_id": file_id,
            "media_type": media_type
        }

        pool["messages"].append(item)

        print("----------------------------------------")
        print(f"Added new message: {message_id}")
        print(f"Type: {media_type or 'text'}")
        print(f"Caption/Text: {text[:100]}")

    print("----------------------------------------")
    print(f"Pool size after: {len(pool['messages'])}")
    print(f"Last update ID: {pool['last_update_id']}")
    print("========================================")

    return pool


def send_message(message):
    """
    Send a stored message to the destination channel.
    First tries copyMessage.
    If Telegram rejects it, falls back to sending the media
    using its file_id.
    """

    message_id = message["id"]
    text = message.get("text") or ""
    file_id = message.get("file_id")
    media_type = message.get("media_type")

    print("========================================")
    print(f"Posting message {message_id}")
    print(f"Media type: {media_type}")
    print(f"Caption length: {len(text)}")

    # -------------------------------------------------
    # 1. Try Telegram copyMessage first
    # -------------------------------------------------

    try:
        print("Trying copyMessage...")

        result = telegram(
            "copyMessage",
            {
                "chat_id": OLD_CHANNEL_ID,
                "from_chat_id": NEW_CHANNEL_ID,
                "message_id": message_id
            }
        )

        print("copyMessage successful.")
        print(f"Telegram message ID: {result.get('message_id')}")

        return True

    except Exception as copy_error:
        print("copyMessage failed.")
        print(str(copy_error))

    # -------------------------------------------------
    # 2. Fallback: send the media directly
    # -------------------------------------------------

    if not file_id:
        print("No media file_id available.")
        print("Trying sendMessage...")

        telegram(
            "sendMessage",
            {
                "chat_id": OLD_CHANNEL_ID,
                "text": text
            }
        )

        print("Text message sent successfully.")
        return True

    try:
        print("Trying direct media upload using file_id...")

        if media_type == "photo":
            method = "sendPhoto"

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "photo": file_id
            }

            if text:
                data["caption"] = text

        elif media_type == "video":
            method = "sendVideo"

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "video": file_id
            }

            if text:
                data["caption"] = text

        elif media_type == "document":
            method = "sendDocument"

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "document": file_id
            }

            if text:
                data["caption"] = text

        elif media_type == "animation":
            method = "sendAnimation"

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "animation": file_id
            }

            if text:
                data["caption"] = text

        elif media_type == "audio":
            method = "sendAudio"

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "audio": file_id
            }

            if text:
                data["caption"] = text

        elif media_type == "voice":
            method = "sendVoice"

            data = {
                "chat_id": OLD_CHANNEL_ID,
                "voice": file_id
            }

            if text:
                data["caption"] = text

        else:
            print("Unknown media type.")
            return False

        telegram(method, data)

        print("Direct media send successful.")
        return True

    except Exception as media_error:
        print("Direct media send also failed.")
        print(str(media_error))
        return False


def post_random_message(pool):
    if not pool["messages"]:
        print("No messages available in pool.")
        return pool

    print("Choosing a random message...")

    # Avoid posting the same message twice in a row
    available = [
        message
        for message in pool["messages"]
        if message["id"] != pool.get("last_posted_id")
    ]

    # If only one message exists, use it
    if not available:
        available = pool["messages"]

    choice = random.choice(available)

    print("----------------------------------------")
    print(f"Selected message: {choice['id']}")
    print(f"Type: {choice.get('media_type')}")
    print(f"Text: {(choice.get('text') or '')[:200]}")
    print("----------------------------------------")

    success = send_message(choice)

    if success:
        pool["last_posted_id"] = choice["id"]
        print(f"Posted message {choice['id']} successfully.")
    else:
        print("Post failed. last_posted_id was NOT changed.")

    return pool


if __name__ == "__main__":
    pool = load_pool()

    pool = fetch_new_messages(pool)

    pool = post_random_message(pool)

    save_pool(pool)

    print("Pool saved successfully.")
