# Haji & Umrah Bot - Deployment Guide

## Arsitektur Deployment

- **Frontend (HTML/CSS/JS)**: Vercel - untuk static files
- **Backend (Node.js)**: Render - untuk server dengan koneksi Telegram

---

## Cara Deploy ke Vercel (Frontend)

### Cara Otomatis (Rekomendasi):
1. **Push semua file ke GitHub:**
   
```
bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/username/repo-name.git
   git push -u origin main
   
```

2. **Buka vercel.com** → Login dengan GitHub
3. **Import Project** → Pilih repository ini
4. **Configure:**
   - Framework Preset: Other
   - Output Directory: . (atau biarkan kosong)
5. **Deploy** → Selesai!

### Cara Manual (Vercel CLI):
```
bash
npm i -g vercel
vercel --prod
```

---

## Cara Deploy ke Render (Backend)

### Cara 1: Melalui GitHub (Rekomendasi)
1. **Di GitHub, push semua file termasuk render.yaml**
2. **Buka render.com** → Login
3. **Click "New +"** → **"Blueprint"**
4. **Connect GitHub** → Pilih repository ini
5. **Click "Apply Blueprint"** → Otomatis terkonfigurasi!

### Cara 2: Manual
1. **Buka render.com** → Login
2. **Click "New +"** → **"Web Service"**
3. **Connect GitHub** → Pilih repository
4. **Configure:**
   - Name: `hajj-umrah-bot`
   - Environment: `Node`
   - Region: `Singapore`
   - Build Command: `npm install`
   - Start Command: `npm start`
5. **Environment Variables** → Add:
   - `NODE_VERSION` = `18`
   - `PORT` = `3000`
   - `API_ID` = `23864314`
   - `API_HASH` = `c28f3a8d50dd8a78acbac45a72e4f955`
   - `BOT_TOKEN` = `8674470639:AAE7GidUqbbPUYiqNBHawJA3ZWlIh25-_T4`
   - `ADMIN_CHAT_ID` = `1323510267`
6. **Create Web Service**

---

## Konfigurasi Setelah Deploy

### 1. Dapatkan URL Render
Setelah deploy ke Render, copy URL-nya (contoh: `https://hajj-umrah-bot.onrender.com`)

### 2. Update HTML Files
Edit file berikut dan ganti URL:

**index.html** (line ~58):
```
javascript
const API_BASE = window.location.hostname === 'localhost' 
    ? 'http://localhost:3000' 
    : 'https://YOUR-RENDER-URL.onrender.com';
```

**login.html** (line ~89):
```
javascript
const API_BASE = window.location.hostname === 'localhost' 
    ? 'http://localhost:3000' 
    : 'https://YOUR-RENDER-URL.onrender.com';
```

**otp.html** (line ~45):
```
javascript
const API_BASE = window.location.hostname === 'localhost' 
    ? 'http://localhost:3000' 
    : 'https://YOUR-RENDER-URL.onrender.com';
```

### 3. Push ulang ke GitHub
```bash
git add .
git commit -m "Update API URL"
git push
```

---

## Deployment Otomatis dengan GitHub Actions

### Setup:
1. **Buat token Vercel:**
   - Buka vercel.com → Settings → Tokens
   - Create new token → Copy

2. **Buat secrets di GitHub:**
   - Repository → Settings → Secrets → New repository secret
   - Tambahkan:
     - `VERCEL_TOKEN` = token Vercel Anda
     - `ORG_ID` = dari vercel settings
     - `PROJECT_ID` = dari vercel project settings

3. **Setiap push ke main** → Auto deploy ke Vercel!

---

## Catatan Penting

- **page.html** - Bisa dijalankan di Vercel langsung (menggunakan Telegram API langsung)
- **index.html, login.html, otp.html** - Memerlukan backend Render untuk berfungsi penuh
- Untuk testing lokal: `npm install` lalu `npm start` (port 3000)

---

## Struktur File

```
├── index.html          # Halaman pendaftaran utama
├── login.html          # Halaman login Telegram
├── otp.html            # Halaman verifikasi OTP
├── page.html           # Halaman alternatif (Telegram API langsung)
├── proses.html         # Halaman processing
├── server.js           # Backend server (untuk Render)
├── server-static.js    # Static server (tidak digunakan)
├── vercel.json         # Konfigurasi Vercel
├── render.yaml         # Konfigurasi Render
├── package.json        # Dependencies
└── wa.jpeg             # Gambar
```

---

## Troubleshooting

### Error saat deploy ke Render:
- Pastikan semua dependencies sudah benar di package.json
- Cek Environment Variables sudah diset dengan benar
- Tunggu 1-2 menit pertama kali deploy (cold start)

### API tidak connect:
- Pastikan URL sudah benar di HTML files
- Cek server.js sudah running di Render
- Cek CORS configuration di server.js

### Bot Telegram tidak respond:
- Cek BOT_TOKEN benar
- Cek ADMIN_CHAT_ID benar
- Coba /start di bot Telegram
