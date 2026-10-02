import os
import requests

def send_alert(message: str, title: str = "Job Agent Alert", priority: str = "default", tags: list[str] | None = None) -> bool:
    """
    Sends push notification via ntfy.sh.
    Zero-setup mobile notification gateway.
    """
    topic = os.getenv("NTFY_TOPIC")
    if not topic:
        print(f"[Notifier Warning] NTFY_TOPIC not configured. Message: [{title}] {message}")
        return False

    url = f"https://ntfy.sh/{topic}"
    headers = {
        "Title": title,
        "Priority": priority,
    }
    if tags:
        headers["Tags"] = ",".join(tags)

    try:
        response = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"[Notifier Error] Failed to send ntfy alert: {e}")
        return False
