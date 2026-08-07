import os
import json
import random
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]
NEW_CHANNEL_ID = os.environ["NEW_CHANNEL_ID"].strip()
OLD_CHANNEL_ID = os.environ["OLD_CHANNEL_ID"].strip()

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
POOL_FILE = "pool.json"


def load_pool():
    with open(POOL_FILE, "r") as f:
        pool = json.load(f)

    pool.setdefault("last_posted_id", None)
    return pool


def save_pool(pool):
    with open(POOL_FILE, "w") as f:
        json.dump(pool, f, indent=2)


def fetch_new_messages(pool):
    print("====================================")
    print("Checking Telegram for new updates...")
    print("Last update ID:", pool["last_update_id"])

    resp = requests.get(
        f"{API}/getUpdates",
        params={
            "offset": pool["last_update_id"] + 1,
            "allowed_updates": json.dumps(["channel_post"])
        }
    ).json()

    print("Telegram Response:")
    print(json.dumps(resp, indent=2))

    for update in resp.get("result", []):
        print("Received Update:")
        print(json.dumps(update, indent=2))

        pool["last_update_id"] = update["update_id"]

        post = update.get("channel_post")
        if not post:
            print("Skipped: Not a channel post.")
            continue

        chat_id = str(post["chat"]["id"]).strip()
        print("Channel ID:", chat_id)

        if chat_id != NEW_CHANNEL_ID:
            print("Skipped: Wrong channel.")
            continue

        text = post.get("text") or post.get("caption") or ""
        photo = post.get("photo")
        video = post.get("video")

        file_id = None
        media_type = None

        if photo:
            file_id = photo[-1]["file_id"]
            media_type = "photo"
        elif video:
            file_id = video["file_id"]
            media_type = "video"

        if text or file_id:
            pool["messages"].append({
                "id": post["message_id"],
                "text": text,
                "file_id": file_id,
                "media_type": media_type
            })

            print("✅ Added message to pool:")
            print(text[:80] if text else f"[{media_type}]")

    print("Pool size:", len(pool["messages"]))
    print("====================================")

    return pool


def post_random_message(pool):
    if not pool["messages"]:
        print("Pool is empty.")
        return pool

    print(f"Choosing randomly from {len(pool['messages'])} messages...")

    available = [
        msg for msg in pool["messages"]
        if msg["id"] != pool.get("last_posted_id")
    ]

    if not available:
        available = pool["messages"]

    choice = random.choice(available)

    if choice.get("media_type") == "photo":
        requests.post(
            f"{API}/sendPhoto",
            json={
                "chat_id": OLD_CHANNEL_ID,
                "photo": choice["file_id"],
                "caption": choice.get("text", "")
            }
        ).raise_for_status()

    elif choice.get("media_type") == "video":
        requests.post(
            f"{API}/sendVideo",
            json={
                "chat_id": OLD_CHANNEL_ID,
                "video": choice["file_id"],
                "caption": choice.get("text", "")
            }
        ).raise_for_status()

    else:
        requests.post(
            f"{API}/sendMessage",
            json={
                "chat_id": OLD_CHANNEL_ID,
                "text": choice["text"]
            }
        ).raise_for_status()

    pool["last_posted_id"] = choice["id"]

    print("Posted:")
    print(choice.get("text", "")[:80] or f"[{choice.get('media_type')}]")

    return pool


if __name__ == "__main__":
    pool = load_pool()
    pool = fetch_new_messages(pool)
    pool = post_random_message(pool)
    save_pool(pool)
