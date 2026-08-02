# 🎬 Simple Multi-Platform Video Downloader

![React](https://img.shields.io/badge/Frontend-React%20%2F%20Vite-61DAFB?logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI%20%2F%20Python-009688?logo=fastapi&logoColor=white)
![yt-dlp](https://img.shields.io/badge/Engine-yt--dlp%20%2B%20FFmpeg-FF0000?logo=youtube&logoColor=white)
![Docker](https://img.shields.io/badge/Deploy-Docker%20Compose-2496ED?logo=docker&logoColor=white)

เว็บแอปพลิเคชัน (Web Application) สไตล์โมเดิร์น น้ำหนักเบา สำหรับดาวน์โหลดและเก็บถาวรวิดีโอ (Personal Video Archival) จากโซเชียลมีเดียชั้นนำ ขับเคลื่อนด้วย **Python FastAPI** และ **yt-dlp** พร้อมระบบประมวลผลวิดีโอผ่าน **FFmpeg** เพื่อให้วิดีโอที่โหลดมาสามารถเล่นได้ทุกแพลตฟอร์ม รวมถึงอุปกรณ์ Apple (macOS/iOS) โดยไม่มีปัญหาสัญญาณเสียงหรือภาพหาย หน้าจออินเตอร์เฟซพัฒนาด้วย **React (Vite)** ดีไซน์ Modern Dark-mode เรียบหรู

---

## ✨ คุณสมบัติเด่น (Features)

* 🌐 **รองรับหลายแพลตฟอร์มชั้นนำ (Multi-Platform Support):** สามารถดาวน์โหลดวิดีโอจาก **YouTube, TikTok, Facebook** และ **Instagram** ในคุณภาพสูงสุดเท่าที่เป็นไปได้
* 🔄 **ระบบพยายามดาวน์โหลดอัตโนมัติ (Intelligent Fallback Strategies):** มีกลไกป้องกันการล้มเหลวในการดาวน์โหลดและลดอัตราการถูกบล็อค โดยไล่ลำดับกลยุทธ์ 4 단계โดยอัตโนมัติ:
  1. ดาวน์โหลดแบบมาตรฐาน (Standard Extraction)
  2. ดึง Session Cookies จากแท็บเบราว์เซอร์ **Chrome**
  3. ดึง Session Cookies จากแท็บเบราว์เซอร์ **Safari**
  4. จำลองการเชื่อมต่อ TLS แบบเบราว์เซอร์ Chrome (TLS Impersonation)
* 🍎 **เข้ากันได้กับ Apple / iOS 100% (Universal Codec):** แปลงและคัดกรองสตรีมให้อยู่ในฟอร์แมต **H.264 (MP4) + AAC (M4A)** โดยอัตโนมัติ ทำให้หมดปัญหาโหลดวิดีโอมาแล้วเปิดใน QuickTime / iPad / iPhone ไม่ได้
* 🍪 **รองรับวิดีโอส่วนบุคคล (Restricted / Private Videos):** สามารถวางไฟล์ `cookies.txt` ในโฟลเดอร์โปรเจกต์ เพื่อเข้าสู่ระบบและดาวน์โหลดวิดีโอเฉพาะที่จำกัดสิทธิ์ได้อย่างง่ายดาย
* 🐳 **รันง่ายจบในคำสั่งเดียวด้วย Docker (Multi-stage Build):** คอนเทนเนอร์แพ็กมาครบทั้ง Frontend, Backend และแคนดิดต FFmpeg ภายในตัว ไม่ต้องติดตั้ง Dependencies ให้ยุ่งยากบนเครื่องหลัก
* 📁 **เก็บบันทึกตรงลงโฟลเดอร์หลัก:** เชื่อมต่อ Volume วิดีโอที่โหลดจะถูกจัดเก็บเข้าโฟลเดอร์ `VDO/` ในคอมพิวเตอร์ของคุณโดยอัตโนมัติ พร้อมตั้งชื่อไฟล์และจัดการอักษรพิเศษอย่างปลอดภัย

---

## 🚀 แพลตฟอร์มและโดเมนที่รองรับ (Supported Platforms)

| แพลตฟอร์ม | โดเมนที่รองรับ | ตัวอย่างลิงก์ |
| :--- | :--- | :--- |
| 🔴 **YouTube** | `youtube.com`, `youtu.be` | `https://www.youtube.com/watch?v=...`, `https://youtu.be/...` |
| 🎵 **TikTok** | `tiktok.com` | `https://www.tiktok.com/@user/video/...` |
| 🔵 **Facebook** | `facebook.com`, `fb.watch` | `https://www.facebook.com/share/v/...`, `https://fb.watch/...` |
| 📸 **Instagram** | `instagram.com` | `https://www.instagram.com/p/...`, `https://www.instagram.com/reels/...` |

---

## 🐳 การใช้งานด้วย Docker (แนะนำ - Quickstart)

วิธีการที่สะดวกที่สุดสำหรับทั้งเซิร์ฟเวอร์และคอมพิวเตอร์ส่วนบุคคล โดยไม่จำเป็นต้องติดตั้ง Python, Node.js หรือ FFmpeg ลงบนตัวเครื่อง

### 1. สั่งรันด้วย Docker Compose
ที่โฟลเดอร์หลักของโปรเจกต์ (ที่ไฟล์ `docker-compose.yml` ตั้งอยู่) เปิดรันคำสั่ง:
```bash
docker compose up -d
```

* 🌐 เปิดหน้าเบราว์เซอร์ไปที่: **[http://localhost:8000](http://localhost:8000)** (หรือแทนที่ด้วย IP ของเซิร์ฟเวอร์ เช่น `http://192.168.x.x:8000`)
* 📂 วิดีโอที่ถูกดาวน์โหลดจะบันทึกอยู่ในโฟลเดอร์ **`VDO/`** ภายนอก Docker บนเครื่องของคุณทันที
* 🛑 ต้องการปิดใช้งานบริการ สั่ง: `docker compose down`

---

## 🍪 การดาวน์โหลดวิดีโอแบบส่วนบุคคล / ต้องล็อกอิน (Optional: Cookies Setup)

หากคุณต้องการดาวน์โหลดวิดีโอที่มีการจำกัดการเข้าถึง (เช่น วิดีโอส่วนบุคคล หรือวิดีโอที่ต้องล็อกอินเพื่อรับชมบน Instagram / Facebook / Private Reels):
1. ติดตั้งส่วนขยายเบราว์เซอร์ เช่น **Get cookies.txt LOCALLY** บน Chrome หรือ Firefox
2. เข้าไปที่เว็บไซต์เป้าหมาย แล้วเลือกล็อกอินให้เรียบร้อย จากนั้น Export คุกกี้ออกมาในชื่อไฟล์ **`cookies.txt`** (รูปแบบ Netscape HTTP Cookie File format)
3. นำไฟล์ `cookies.txt` มาวางไว้ในโฟลเดอร์หลัก (Root directory) ของโปรเจกต์
4. (*สำหรับ Docker*) เปิดไฟล์ `docker-compose.yml` แล้วลบเครื่องหมาย `#` ออกจากบรรทัดนี้เพื่อเปิดใช้งาน:
   ```yaml
   # - ./cookies.txt:/app/cookies.txt:ro
   ```
   จากนั้นรันคำสั่ง `docker compose up -d --force-recreate` อีกครั้ง ระบบจะอ่านคุกกี้ให้อัตโนมัติ

---

## 💻 การพัฒนาระบบและรันแบบ Manual (Local Development Setup)

สำหรับนักพัฒนาที่ต้องการปรับแต่งโค้ดหรือรันระบบแบบ Local โดยไม่ผ่าน Docker

### 1. ความต้องการของระบบ (Prerequisites)
* **Python** 3.10 ขึ้นไป
* **Node.js** 18 ขึ้นไป
* **FFmpeg** (จำเป็นมาก สำหรับการรวมไฟล์ภาพและเสียง):
  * **macOS:** `brew install ffmpeg`
  * **Ubuntu/Debian:** `sudo apt update && sudo apt install -y ffmpeg`
  * **Windows:** ดาวน์โหลดจากเว็บ FFmpeg แล้วตั้งค่า System Environment Variable (`PATH`)

### 2. รันระบบหลังบ้าน (Backend Server)
เปิด Terminal แล้วรันคำสั่งในโฟลเดอร์โปรเจกต์:
```bash
cd backend

# สร้างและเปิดใช้งาน Virtual Environment (แนะนำ)
python3 -m venv .venv
source .venv/bin/activate  # สำหรับ Windows ใช้: .venv\Scripts\activate

# ติดตั้ง Libraries ต่างๆ ที่จำเป็น
pip install -r requirements.txt

# สั่งรันเซิร์ฟเวอร์ด้วย Uvicorn
uvicorn main:app --reload --port 8000
```
*(Backend จะทำงานอยู่ที่ http://localhost:8000 และ API docs อยู่ที่ http://localhost:8000/docs)*

### 3. รันระบบหน้าบ้าน (Frontend UI)
เปิด Terminal อีกหนึ่งหน้าต่าง (หรือ Tab ใหม่):
```bash
cd frontend

# ติดตั้ง Node Modules
npm install

# รันโฮมเพจจำลอง (Vite Dev Server)
npm run dev
```
*(เปิดเบราว์เซอร์ไปที่ **http://localhost:5173** เพื่อใช้งานระบบ)*

---

## 📁 โครงสร้างโปรเจกต์ (Directory Structure)

```
AutoDownload-VDO/
├── 📂 VDO/                  # โฟลเดอร์จัดเก็บวิดีโอที่ดาวน์โหลดมา (เชื่อมต่อ Volume กับ Docker)
├── 📂 backend/              # เซิร์ฟเวอร์ Python FastAPI & ตรรกะการประมวลผล yt-dlp
│   ├── downloader.py        # Logic การดาวน์โหลด, ตั้งค่าสตรีม H264/AAC และระบบ Fallbacks
│   ├── main.py              # FastAPI Controllers, API Endpoints, และ Static Files Serving
│   └── requirements.txt     # รายการ Python Dependencies
├── 📂 frontend/             # เว็บแอปพลิเคชัน React (Vite)
│   ├── src/                 # ซอร์สโค้ด UI สไตล์ Modern Dark-mode & Animations
│   └── package.json         # รายการ Node Dependencies & Configurations
├── 🐳 Dockerfile            # สคริปต์ Multi-stage Docker Build (Node Builder + Python Runtime + FFmpeg)
├── 🐳 docker-compose.yml    # สคริปต์การตั้งค่าและการรันระบบทั้งหมดใน Docker ด้วยคำสั่งเดียว
└── 📄 README.md             # เอกสารคู่มือระบบนี้
```

---

## ⚖️ คำชี้แจง (Disclaimer)

โปรดใช้งานแอปพลิเคชันนี้เพื่อจุดประสงค์ในการศึกษา หรือเก็บถาวรวิดีโอส่วนตัวและเนื้อหาที่คุณได้รับสิทธิ์ตามกฎหมายเท่านั้น ผู้ใช้งานควารปฏิบัติตามกฎและข้อตกลงการใช้งาน (Terms of Service) ของแพลตฟอร์มต่างๆ อย่างเคร่งครัด ผู้พัฒนาไม่มีส่วนรับผิดชอบในการนำซอฟต์แวร์นี้ไปใช้งานในทางที่ละเมิดลิขสิทธิ์
# DownlodeVDO-Link
