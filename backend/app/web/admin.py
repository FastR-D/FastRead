"""Offline account provisioning; registration is never implicitly public."""
import argparse
import getpass
import json
import os

from .auth import create_user
from .store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--email", required=True)
    parser.add_argument("--workspace", default="我的资料库")
    args = parser.parse_args()
    store = Store(args.root)
    store.initialize()
    password = os.environ.get("FASTREAD_INITIAL_PASSWORD") or getpass.getpass("Password (12+ characters): ")
    print(json.dumps(create_user(store, args.email, password, args.workspace), ensure_ascii=False))


if __name__ == "__main__":
    main()
