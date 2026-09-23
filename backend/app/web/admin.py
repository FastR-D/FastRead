"""Offline account provisioning; registration is never implicitly public."""
import argparse
import getpass
import json
import os

from .auth import create_user
from .store import Store
from .local_accounts import issue_credential


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--email", required=True)
    parser.add_argument("--workspace", default="我的资料库")
    parser.add_argument("--action", choices=["create", "invite", "recovery"], default="create")
    args = parser.parse_args()
    store = Store(args.root)
    store.initialize()
    if args.action != "create":
        # Deliberate operator output: deliver this one-time secret privately.
        print(json.dumps({"kind": args.action, "token": issue_credential(store, args.action, args.email), "expires_in": 3600}))
        return
    password = os.environ.get("FASTREAD_INITIAL_PASSWORD") or getpass.getpass("Password (12+ characters): ")
    print(json.dumps(create_user(store, args.email, password, args.workspace), ensure_ascii=False))


if __name__ == "__main__":
    main()
