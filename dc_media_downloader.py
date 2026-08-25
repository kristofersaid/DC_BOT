# ==========================================
# FILE: dc_media_downloader.py
# ==========================================

#!/usr/bin/env python3
import requests
import os
import re
import json
import time
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

BASE_URL = "https://discord.com/api/v9"
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "main_config.json")
TIMEZONE_OFFSET = 2
WEEK_OFFSET = 2


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


SPECIAL_WEEKS = {
    354: {
        "start": datetime(2025, 4, 28, 14, 0),
        "end": datetime(2025, 5, 12, 14, 0),
    },
}


def week_to_date(week_number: int) -> datetime:
    week_1_start_utc = datetime(2018, 7, 30, 14, 0, tzinfo=timezone.utc)
    if week_number in SPECIAL_WEEKS:
        dt = SPECIAL_WEEKS[week_number]["start"]
        return dt.replace(tzinfo=timezone.utc)
    if week_number >= 355:
        adjusted_week = week_number - WEEK_OFFSET + 1
    else:
        adjusted_week = week_number - WEEK_OFFSET
    return week_1_start_utc + timedelta(weeks=adjusted_week)


def week_to_end_date(week_number: int) -> datetime:
    week_1_start_utc = datetime(2018, 7, 30, 14, 0, tzinfo=timezone.utc)
    if week_number in SPECIAL_WEEKS:
        dt = SPECIAL_WEEKS[week_number]["end"]
        return dt.replace(tzinfo=timezone.utc)
    if week_number >= 355:
        adjusted_week = week_number - WEEK_OFFSET + 1
    else:
        adjusted_week = week_number - WEEK_OFFSET
    return week_1_start_utc + timedelta(weeks=adjusted_week + 1)


def extract_channel_id(link: str) -> Optional[int]:
    match = re.search(r"discord\.com/channels/\d+/(\d+)", link)
    return int(match.group(1)) if match else None


def test_connection(token: str):
    headers = {"Authorization": token}
    resp = requests.get(f"{BASE_URL}/users/@me", headers=headers)
    if resp.status_code == 200:
        user = resp.json()
        print(f"[OK] Zalogowany jako: {user.get('username', '?')}")
        return True
    else:
        print(f"[FAIL] Blad autoryzacji: {resp.status_code}")
        return False


def get_channel_info(token: str, channel_id: int):
    headers = {"Authorization": token}
    resp = requests.get(f"{BASE_URL}/channels/{channel_id}", headers=headers)
    if resp.status_code == 200:
        return resp.json()
    return None


def get_messages_before(token: str, channel_id: int, before: str = None, limit: int = 50):
    headers = {"Authorization": token}
    url = f"{BASE_URL}/channels/{channel_id}/messages"
    params = {"limit": limit}
    if before:
        params["before"] = before
    for attempt in range(3):
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 429:
            time.sleep(5)
        else:
            time.sleep(2)
    raise Exception(f"Blad API: {resp.status_code} - {resp.text}")


def get_extension(filename: str) -> str:
    if "." in filename:
        return "." + filename.rsplit(".", 1)[1].lower()
    return ".dat"


def download_attachment(token: str, attachment: dict, output_dir: str, name: str):
    url = attachment["url"]
    headers = {"Authorization": token}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        ext = get_extension(attachment["filename"])
        filepath = os.path.join(output_dir, f"{name}{ext}")
        with open(filepath, "wb") as f:
            f.write(resp.content)
        return filepath
    return None


# ==================== MODE: SINCE DATE (with limit) ====================

def download_since(token, channel_id, start_date, folder_name, folder_suffix, limit=50):
    output_dir = os.path.join(folder_name, folder_suffix)
    os.makedirs(output_dir, exist_ok=True)
    extensions = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
    ch_info = get_channel_info(token, channel_id)
    guild_id = ch_info.get("guild_id") if ch_info else None

    print(f"Pobieranie z kanalu {channel_id}...")
    print(f"Od: {start_date.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Folder: {output_dir}")
    print(f"Limit: {limit} plikow\n")

    all_msgs = []
    before = None
    while True:
        messages = get_messages_before(token, channel_id, before)
        if not messages:
            break
        has = False
        for msg in messages:
            msg_time = datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00"))
            if msg_time >= start_date:
                all_msgs.append((msg_time, msg))
                has = True
            else:
                break
        if not has:
            break
        if len(messages) < 50:
            break
        before = messages[-1]["id"]

    all_msgs.sort(key=lambda x: x[0])
    print(f"Znaleziono {len(all_msgs)} wiadomosci\n")

    count = 0
    idx = 0
    for msg_time, msg in all_msgs:
        if count >= limit:
            break
        for att in msg.get("attachments", []):
            if count >= limit:
                break
            if att["filename"].lower().endswith(extensions):
                idx += 1
                count += 1
                print(f"  [{idx}] {att['filename']}")
                try:
                    name = f"{folder_suffix}_{idx}"
                    path = download_attachment(token, att, output_dir, name)
                    if path:
                        print(f"       [OK] Zapisano: {os.path.basename(path)}")
                except Exception as e:
                    print(f"       [FAIL] Blad: {e}")

    print(f"\nZakonczono. Pobrano {count} plikow do {output_dir}/")


# ==================== MODE: DATE RANGE ====================

def download_range(token, channel_id, start_date, end_date, folder_name, date_name):
    output_dir = os.path.join(folder_name, date_name)
    os.makedirs(output_dir, exist_ok=True)
    extensions = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
    ch_info = get_channel_info(token, channel_id)
    guild_id = ch_info.get("guild_id") if ch_info else None

    print(f"Pobieranie z kanalu {channel_id}...")
    print(f"Od: {start_date.strftime('%d-%m-%Y %H:%M')} do {end_date.strftime('%d-%m-%Y %H:%M')} UTC")
    print(f"Folder: {output_dir}\n")

    downloaded = []
    before = None
    stop = False
    while True:
        messages = get_messages_before(token, channel_id, before)
        if not messages:
            break
        for msg in messages:
            msg_time = datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00"))
            if msg_time < start_date:
                stop = True
                break
            for att in msg.get("attachments", []):
                if att["filename"].lower().endswith(extensions):
                    downloaded.append((msg_time, msg, att))
        if stop:
            break
        if len(messages) < 50:
            break
        before = messages[-1]["id"]

    filtered = [d for d in downloaded if d[0] < end_date]
    filtered.reverse()
    total = len(filtered)
    print(f"Znaleziono {total} zdjec w zakresie\n")

    for i, (msg_time, msg, att) in enumerate(filtered, 1):
        msg_link = f"discord.com/channels/{guild_id or '@me'}/{channel_id}/{msg['id']}"
        print(f"[{i}/{total}] {msg_link}")
        print(f"      Czas: {msg_time.strftime('%Y-%m-%d %H:%M')}")
        print(f"      Plik: {att['filename']}")
        try:
            name = f"{date_name}_{i}"
            path = download_attachment(token, att, output_dir, name)
            if path:
                print(f"      [OK] {os.path.basename(path)}")
        except Exception as e:
            print(f"      [FAIL] Blad: {e}")
        print()

    print(f"\nZakonczono. Pobrano {total} plikow do {output_dir}/")


# ==================== MODE: WEEK (with end date) ====================

def download_week(token, channel_id, start_date, end_date, folder_name, date_name):
    download_range(token, channel_id, start_date, end_date, folder_name, date_name)


# ==================== MODE: LATEST ====================

def download_latest(token, channel_id, folder_name, limit):
    output_dir = folder_name
    os.makedirs(output_dir, exist_ok=True)
    extensions = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
    ch_info = get_channel_info(token, channel_id)
    guild_id = ch_info.get("guild_id") if ch_info else None

    print(f"Pobieranie z kanalu {channel_id}...")
    print(f"Ilosc: {limit} najnowszych zdjec")
    print(f"Folder: {output_dir}\n")

    downloaded = []
    before = None
    while len(downloaded) < limit:
        messages = get_messages_before(token, channel_id, before)
        if not messages:
            break
        for msg in messages:
            for att in msg.get("attachments", []):
                if att["filename"].lower().endswith(extensions):
                    downloaded.append((msg, att))
                    if len(downloaded) >= limit:
                        break
            if len(downloaded) >= limit:
                break
        if len(messages) < 50:
            break
        before = messages[-1]["id"]

    total = min(len(downloaded), limit)
    print(f"Znaleziono {len(downloaded)} zdjec\n")

    for i, (msg, att) in enumerate(downloaded[:limit], 1):
        msg_link = f"discord.com/channels/{guild_id or '@me'}/{channel_id}/{msg['id']}"
        msg_time = datetime.fromisoformat(msg["timestamp"].replace("Z", "+00:00"))
        print(f"[{i}/{total}] {msg_link}")
        print(f"      Czas: {msg_time.strftime('%Y-%m-%d %H:%M')}")
        print(f"      Plik: {att['filename']}")
        try:
            name = f"{i}"
            path = download_attachment(token, att, output_dir, name)
            if path:
                print(f"      [OK] {os.path.basename(path)}")
        except Exception as e:
            print(f"      [FAIL] Blad: {e}")
        print()

    print(f"\nZakonczono. Pobrano {total} plikow do {output_dir}/")


# ==================== MAIN ====================

def main():
    # ==================== GUI MODE ====================
    if os.environ.get("DC_GUI_MODE") == "1":
        mode = os.environ.get("DC_MODE", "since")
        token = os.environ["DC_TOKEN"]
        channel_id = int(os.environ["DC_CHANNEL_ID"])
        folder_name = os.environ["DC_FOLDER_NAME"]
        folder_suffix = os.environ.get("DC_FOLDER_SUFFIX", "")

        print("=" * 50)
        print(f"  Discord Media Downloader -- GUI Mode ({mode})")
        print("=" * 50)

        if not test_connection(token):
            print("Token invalid!")
            sys.exit(1)

        if mode == "since":
            start_date_str = os.environ["DC_START_DATE"]
            limit = int(os.environ.get("DC_LIMIT", "50"))
            start_date = datetime.fromisoformat(start_date_str)
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=timezone.utc)
            download_since(token, channel_id, start_date, folder_name, folder_suffix, limit)

        elif mode == "week":
            start_date_str = os.environ["DC_START_DATE"]
            end_date_str = os.environ["DC_END_DATE"]
            start_date = datetime.fromisoformat(start_date_str)
            end_date = datetime.fromisoformat(end_date_str)
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=timezone.utc)
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)
            download_week(token, channel_id, start_date, end_date, folder_name, folder_suffix)

        elif mode == "range":
            start_date_str = os.environ["DC_START_DATE"]
            end_date_str = os.environ["DC_END_DATE"]
            start_date = datetime.fromisoformat(start_date_str)
            end_date = datetime.fromisoformat(end_date_str)
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=timezone.utc)
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)
            download_range(token, channel_id, start_date, end_date, folder_name, folder_suffix)

        elif mode == "latest":
            limit = int(os.environ.get("DC_LIMIT", "50"))
            download_latest(token, channel_id, folder_name, limit)

        print(f"\n{'=' * 50}")
        print("  All done!")
        print(f"{'=' * 50}")
        return

    # ==================== INTERACTIVE MODE ====================
    print("=== Discord Media Downloader ===")
    print("Uzyj GUI (dc_bot_gui.py) lub uruchom odpowiedni skrypt osobno.")


if __name__ == "__main__":
    main()