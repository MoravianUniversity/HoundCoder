#!/usr/bin/env python3
"""Seed the first admin user directly in the DB (bypasses the HTTP API)."""
import argparse
import time
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from app import db
from app.security import encode_jwt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Email address of the admin to create")
    args = parser.parse_args()

    db.init_db()

    if db.get_user(args.email) is not None:
        print(f"User {args.email} already exists", file=sys.stderr)
        raise SystemExit(1)

    now = int(time.time())
    db.create_user(args.email, is_admin=True, created_at=now)
    db.create_token(args.email, now)

    print(encode_jwt(args.email, now))


if __name__ == "__main__":
    main()
