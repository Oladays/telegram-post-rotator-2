import os
import json
import random
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"].strip()
NEW_CHANNEL_ID = os.environ["NEW_CHANNEL_ID"].strip()
OLD_CHANNEL_ID = os.environ["OLD_CHANNEL_ID"].strip()

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
POOL_FILE = "pool.json"


def telegram(method, data=None):
    response = requests.post(
        f"{API}/{method}",
        json=data or {},
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise Exception(f"Telegram API error: {result}")

    return result


def load_pool():
    if not os.path.exists(POOL_FILE):
        return {
            "last_update_id": 0,
            "last_posted_id": None,
            "messages": []
        }

    with open(POOL_FILE, "r", encoding="utf-8") as f:
        pool = json.load(f)

    pool.setdefault("last_update_id", 0)
    pool.setdefault("last_posted_id", None)
    pool.setdefault("messages", [])

    return pool


def save_pool(pool):
    with open(POOL_FILE, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2, ensure_ascii=False)


def fetch_new_messages(pool):
    print("====================================")
    print("Checking Telegram for new channel posts...")
    print("Last update ID:", pool["last_update_id"])

    response = requests.get(
        f"{API}/getUpdates",
        params={
            "offset": pool["last_update_id"] + 1,
            "allowed_updates": json.dumps(["channel_post"]),
            "timeout": 10
        },
        timeout=30
    )

    response.raise_for_status()
    data = response.json()

    if not data.get("ok"):
        raise Exception(f"Telegram getUpdates error: {data}")

    updates = data.get("result", [])

    print("Updates received:", len(updates))

    existing_ids = {
        message["id"]
        for message in pool["messages"]
    }

    for update in updates:
        update_id = update["update_id"]

        if update_id > pool["last_update_id"]:
            pool["last_update_id"] = update_id

        post = update.get("channel_post")

        if not post:
            continue

        chat_id = str(post["chat"]["id"]).strip()

        print("Channel:", chat_id)
        print("Message ID:", post["message_id"])

        if chat_id != NEW_CHANNEL_ID:
            print("Skipped: wrong channel")
            continue

        message_id = post["message_id"]

        if message_id in existing_ids:
            print("Skipped: already in pool")
            continue

        text = post.get("text") or post.get("caption") or ""

        media_type = None
        file_id = None

        if post.get("photo"):
            media_type = "photo"
            file_id = post["photo"][-1]["file_id"]

        elif post.get("video"):
            media_type = "video"
            file_id = post["video"]["file_id"]

        elif post.get("animation"):
            media_type = "animation"
            file_id = post["animation"]["file_id"]

        elif post.get("document"):
            media_type = "document"
            file_id = post["document"]["file_id"]

        elif post.get("audio"):
            media_type = "audio"
            file_id = post["audio"]["file_id"]

        elif post.get("voice"):
            media_type = "voice"
            file_id = post["voice"]["file_id"]

        elif text:
            media_type = "text"

        else:
            print("Skipped: unsupported/empty post")
            continue

        pool["messages"].append({
            "id": message_id,
            "text": text,
            "file_id": file_id,
            "media_type": media_type
        })

        existing_ids.add(message_id)

        print("✅ NEW POST ADDED TO POOL")
        print("ID:", message_id)
        print("Type:", media_type)
        print("Caption/Text:", text[:100])

    print("Pool size:", len(pool["messages"]))
    print("Last update ID:", pool["last_update_id"])
    print("====================================")

    return pool


def post_random_message(pool):
    messages = pool["messages"]

    if not messages:
        print("❌ Pool is empty.")
        return pool

    last_posted_id = pool.get("last_posted_id")

    # Don't immediately post the exact same message twice.
    available = [
        message
        for message in messages
        if message["id"] != last_posted_id
    ]

    # If there is only one message, allow it.
    if not available:
        available = messages

    choice = random.choice(available)

    source_message_id = choice["id"]

    print("====================================")
    print("Selected message:", source_message_id)
    print("Type:", choice.get("media_type"))
    print("Text:", choice.get("text", "")[:100])

    # copyMessage is used instead of manually sending the file.
    # This preserves the original media AND its caption.
    result = telegram(
        "copyMessage",
        {
            "chat_id": OLD_CHANNEL_ID,
            "from_chat_id": NEW_CHANNEL_ID,
            "message_id": source_message_id
        }
    )

    if result.get("ok"):
        pool["last_posted_id"] = source_message_id

        print("✅ POSTED SUCCESSFULLY")
        print("Source message:", source_message_id)
        print("Destination:", OLD_CHANNEL_ID)

    print("====================================")

    return pool


if __name__ == "__main__":
    pool = load_pool()

    pool = fetch_new_messages(pool)
    save_pool(pool)

    pool = post_random_message(pool)
    save_pool(pool)

    print("✅ Bot finished successfully.")
