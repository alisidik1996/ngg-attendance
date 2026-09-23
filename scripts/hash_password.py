"""Generate scrypt password hash untuk membuat/mengubah user manual via SQL.

Pakai algoritma yang sama dengan aplikasi (core.auth.hash_password):
  hashlib.scrypt, salt 16 byte acak, N=2^14, r=8, p=1, dklen=32
  format: scrypt$<salt_hex>$<hash_hex>

Contoh:
  python scripts/hash_password.py
  (lalu ketik password, echo tidak tampil)

  python scripts/hash_password.py --sql --username admin
  (hasil: perintah UPDATE siap tempel di SQL editor Neon)

  python scripts/hash_password.py --verify 'password-anda' 'scrypt$...'
"""

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.auth import hash_password, verify_password  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="Generate scrypt password hash (NGG Attendance)")
    p.add_argument("password", nargs="?", help="Password (jika kosong, akan diminta interaktif)")
    p.add_argument("--sql", action="store_true", help="Output sebagai perintah SQL UPDATE")
    p.add_argument("--username", default="admin", help="Username untuk output SQL (default: admin)")
    p.add_argument("--verify", nargs=2, metavar=("PASSWORD", "HASH"),
                   help="Verifikasi password terhadap hash, keluar 0 jika cocok")
    args = p.parse_args()

    if args.verify:
        ok = verify_password(args.verify[0], args.verify[1])
        print("VALID" if ok else "INVALID")
        sys.exit(0 if ok else 1)

    password = args.password
    if not password:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Ulangi password: ")
        if password != confirm:
            print("Password tidak sama.", file=sys.stderr)
            sys.exit(1)
    if len(password) < 8:
        print("Password minimal 8 karakter.", file=sys.stderr)
        sys.exit(1)

    h = hash_password(password)
    if args.sql:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        safe_user = args.username.replace("'", "''")
        print(f"-- Ganti password user '{safe_user}'")
        print(f"UPDATE users SET password_hash = '{h}', failed_login_count = 0, locked_until = NULL,")
        print(f"  updated_at = '{now}'")
        print(f"WHERE username = '{safe_user}';")
        print()
        print("-- Atau buat user baru:")
        print(
            "INSERT INTO users (username, password_hash, role, is_active, failed_login_count, created_at, updated_at) "
            f"VALUES ('{safe_user}', '{h}', 'admin', 1, 0, '{now}', '{now}');"
        )
    else:
        print(h)


if __name__ == "__main__":
    main()
