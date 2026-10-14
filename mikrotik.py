"""Backup/restore MikroTik ke R2, satu folder per siswa: mikrotik/<nama>/

python mikrotik.py backup                 -> backup router di .env (MT_*) ke mikrotik/<NAMA_SISWA>/
python mikrotik.py list                   -> daftar backup milik sendiri di R2
python mikrotik.py restore <file>         -> file milik sendiri dari R2 ke router, load (router reboot)
"""
import datetime
import os
import sys
import tempfile

import boto3
import paramiko

DIR = os.path.dirname(os.path.abspath(__file__))
for line in open(os.path.join(DIR, ".env")):
    if "=" in line and not line.lstrip().startswith("#"):
        k, v = line.strip().split("=", 1)
        os.environ.setdefault(k, v)

E = os.environ
PREFIX = "mikrotik/"
EXTS = (".backup", ".rsc")
s3 = boto3.client("s3", endpoint_url=E["R2_ENDPOINT"], region_name="auto",
                  aws_access_key_id=E["R2_ACCESS_KEY"], aws_secret_access_key=E["R2_SECRET_KEY"])


NAMA = E.get("NAMA_SISWA", "").strip()


def check_nama():
    if not NAMA or "/" in NAMA:
        raise ValueError("isi NAMA_SISWA di .env (tanpa tanda /)")


def router_from_env():
    return {"host": E["MT_HOST"], "port": int(E.get("MT_PORT", 22)), "user": E["MT_USER"], "password": E["MT_PASS"]}


def ssh(r):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # ponytail: trust-on-first-use, pin host key if router is on untrusted network
    c.connect(r["host"], port=int(r.get("port", 22)), username=r["user"], password=r["password"], timeout=15)
    return c


def run(c, cmd, stdin=None):
    i, o, e = c.exec_command(cmd)
    if stdin:
        i.write(stdin)
        i.flush()
    out = o.read().decode() + e.read().decode()
    print(f"> {cmd}\n{out}".rstrip())
    return out


def enc():
    p = E.get("MT_BACKUP_PASS")
    return f'password="{p}"' if p else "dont-encrypt=yes"


def backup(r):
    check_nama()
    name = f"bk-{datetime.datetime.now():%Y%m%d-%H%M%S}"
    c = ssh(r)
    try:
        run(c, f"/system backup save name={name} {enc()}")
        run(c, f"/export file={name}")
        sftp = c.open_sftp()
        with tempfile.TemporaryDirectory() as d:
            for ext in EXTS:
                local = os.path.join(d, name + ext)
                sftp.get(name + ext, local)
                s3.upload_file(local, E["R2_BUCKET"], f"{PREFIX}{NAMA}/{name}{ext}")
                print(f"uploaded {PREFIX}{NAMA}/{name}{ext}")
        run(c, f'/file remove [find name~"{name}"]')
    finally:
        c.close()


def objects():
    """hanya file di folder milik sendiri: mikrotik/<NAMA_SISWA>/"""
    check_nama()
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=E["R2_BUCKET"], Prefix=f"{PREFIX}{NAMA}/"):
        yield from page.get("Contents", [])


def restore(fname, r):
    """fname = nama file di folder sendiri, contoh: 'bk-20261014-153000.backup'"""
    check_nama()
    if "/" in fname or not fname.endswith(EXTS):
        raise ValueError("file tidak valid: harus file .backup/.rsc di folder sendiri")
    c = ssh(r)
    try:
        with tempfile.TemporaryDirectory() as d:
            local = os.path.join(d, fname)
            s3.download_file(E["R2_BUCKET"], f"{PREFIX}{NAMA}/{fname}", local)
            if fname.endswith(".rsc"):
                # tunggu interface siap setelah reset, kalau tidak baris yang menyebut ether/wlan bisa gagal
                with open(local, encoding="utf-8", errors="replace") as f:
                    script = f.read()
                with open(local, "w", encoding="utf-8", newline="\n") as f:
                    f.write(":delay 15s\n" + script)
            c.open_sftp().put(local, fname)
        if fname.endswith(".backup"):
            p = E.get("MT_BACKUP_PASS")
            run(c, f"/system backup load name={fname}" + (f' password="{p}"' if p else ""), stdin="y\n")
        else:
            # .rsc hanya menambah config, jadi router dikosongkan dulu lalu menjalankan .rsc setelah reboot
            run(c, f"/system reset-configuration no-defaults=yes keep-users=yes run-after-reset={fname}", stdin="y\n")
        print("router akan reboot, tunggu 1-2 menit")
    finally:
        c.close()


if __name__ == "__main__":
    cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("", [])
    if cmd == "backup":
        backup(router_from_env())
    elif cmd == "list":
        for o in objects():
            print(f"{o['LastModified'].astimezone():%Y-%m-%d %H:%M}  {o['Size']:>10}  {o['Key'].rsplit('/', 1)[-1]}")
    elif cmd == "restore" and args:
        if input(f"Restore {args[0]} ke {E['MT_HOST']}? Konfigurasi router akan ditimpa. Ketik YA: ") != "YA":
            sys.exit("dibatalkan")
        restore(args[0], router_from_env())
    else:
        sys.exit(__doc__)
