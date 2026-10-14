# Backup MikroTik ke R2

Backup dan restore konfigurasi MikroTik ke Cloudflare R2. Setiap siswa punya folder sendiri: `mikrotik/<NAMA_SISWA>/`.

## Persiapan

```
git clone <url-repo>
cd <folder-repo>
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Isi `.env`: nama kamu, IP/user/password router, dan key R2 dari instruktur.

Router harus mengaktifkan SSH:

```
/ip service enable ssh
```

## Menjalankan

```
python server.py
```

Buka http://localhost:3000, lalu klik **Backup sekarang**.

Lewat terminal:

```
python mikrotik.py backup
python mikrotik.py list
python mikrotik.py restore bk-20261014-153000.backup
```

## File backup

- `.backup`: salinan penuh, hanya untuk router dengan model dan versi RouterOS yang sama. Restore membuat router reboot.
- `.rsc`: konfigurasi dalam bentuk teks (`/export`). Bisa dibaca dan di-import ke router lain.
