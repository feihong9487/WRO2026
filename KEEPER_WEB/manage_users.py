#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
manage_users.py — 管理監控網站團隊頁的帳號

  python manage_users.py add <帳號>      新增或改密碼（會要你輸入兩次密碼，畫面不顯示）
  python manage_users.py remove <帳號>   刪除帳號
  python manage_users.py list            列出帳號

密碼只存 PBKDF2-SHA256 雜湊值，存在 data/users.json。這個檔案不要傳到 GitHub。
改完不用重開伺服器，下次登入就生效。已經登入的人要等登出或 12 小時過期。
"""

import getpass
import hashlib
import json
import os
import secrets
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("DATA_DIR", os.path.join(HERE, "data"))
PATH = os.path.join(DATA, "users.json")
ITER = 240_000


def load():
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"users": {}}


def save(d):
    os.makedirs(DATA, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("add", "remove", "list"):
        print(__doc__)
        sys.exit(1)
    d = load()
    cmd = sys.argv[1]
    if cmd == "list":
        names = sorted(d["users"])
        print("\n".join(names) if names else "還沒有任何帳號")
        return
    if len(sys.argv) < 3:
        print(f"用法：python manage_users.py {cmd} <帳號>")
        sys.exit(1)
    name = sys.argv[2].strip()
    if cmd == "remove":
        if d["users"].pop(name, None) is None:
            print(f"沒有 {name} 這個帳號")
            sys.exit(1)
        save(d)
        print(f"已刪除 {name}")
        return
    pw = getpass.getpass(f"{name} 的密碼（至少 10 個字）：")
    if len(pw) < 10:
        print("密碼太短，至少要 10 個字")
        sys.exit(1)
    if getpass.getpass("再輸入一次：") != pw:
        print("兩次輸入的密碼不一樣")
        sys.exit(1)
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, ITER)
    existed = name in d["users"]
    d["users"][name] = {"salt": salt.hex(), "hash": h.hex(), "iter": ITER}
    save(d)
    print(f"已{'更新' if existed else '新增'}帳號 {name}")


if __name__ == "__main__":
    main()
