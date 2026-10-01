# สรุปโครงสร้างและความสามารถของระบบ Backend (DownlodeVDO-Link)

ระบบ Backend พัฒนาด้วยภาษา **Python** โดยใช้ **FastAPI** เป็น Web Framework หลัก มีหน้าที่หลักในการขูดข้อมูล (Scraping), ดาวน์โหลดวิดีโอ/รูปภาพ (Downloading), และให้บริการไฟล์มีเดีย (Media Serving) จากแพลตฟอร์มโซเชียลมีเดียชั้นนำ เช่น **Facebook, Instagram, TikTok, YouTube**

---

## 1. โครงสร้างไฟล์และโมดูลหลัก (Core Modules)

| ไฟล์ / โฟลเดอร์ | หน้าที่หลัก |
| :--- | :--- |
| [`main.py`](file:///c:/Users/opal/Desktop/C++/DownlodeVDO-Link/backend/main.py) | **API Router & Job Orchestrator**: กำหนด Endpoints, จัดการ Background Tasks, จัดการคิวงานดาวน์โหลด (Job Tracking), ตรวจจับประเภท URL และให้บริการไฟล์ดาวน์โหลด |
| [`downloader.py`](file:///c:/Users/opal/Desktop/C++/DownlodeVDO-Link/backend/downloader.py) | **Media Download Engine**: ดาวน์โหลดวิดีโอผ่าน `yt-dlp` พร้อมระบบ Fallback Strategies หลายชั้น และดาวน์โหลดรูปภาพความละเอียดสูง |
| [`scraper.py`](file:///c:/Users/opal/Desktop/C++/DownlodeVDO-Link/backend/scraper.py) | **Deep Headless Scraper**: ใช้ `Playwright` จำลองเบราว์เซอร์ เพื่อเลื่อนฟีด (Infinite Scroll), ดักจับ GraphQL API, ดึง Cookie จากเบราว์เซอร์อัตโนมัติ และสกัดลิงก์วิดีโอ/รูปภาพระดับอัลบั้ม |
| [`requirements.txt`](file:///c:/Users/opal/Desktop/C++/DownlodeVDO-Link/backend/requirements.txt) | Dependencies หลัก เช่น `fastapi`, `uvicorn`, `yt-dlp`, `playwright`, `browser-cookie3`, `curl_cffi` |

---

## 2. ความสามารถหลักของ Backend (Key Capabilities)

### 2.1 รองรับการดาวน์โหลดวิดีโอหลายแพลตฟอร์ม (Multi-Platform Video Downloader)
* **แพลตฟอร์มที่รองรับ**: 
  - **YouTube** (วิดีโอปกติ, Shorts, Playlists, Channels)
  - **Facebook** (Reels, Watch, Post Videos, Shares, กลุ่ม/เพจ)
  - **Instagram** (Reels, Posts, Profiles)
  - **TikTok** (คลิปวิดีโอสั้น)
* **ฟอร์แมตมาตรฐาน**: บังคับแปลงเป็น **MP4 (H.264 / AAC)** เพื่อให้สามารถเปิดบนทุกอุปกรณ์ (รวมถึง Apple / QuickTime) ได้ทันที
* **การจัดการโฟลเดอร์อัตโนมัติ**: แยกเก็บไฟล์เป็นสัดส่วนตามชื่อแชนแนล, เพจ, หรือบัญชีผู้สร้าง ในโฟลเดอร์ `VDO/<ชื่อผู้สร้าง>/...`

### 2.2 ระบบหลบเลี่ยงการบล็อกและการดึง Cookie อัตโนมัติ (Anti-Blocking & Cookie Bypass)
* **Auto-Extract Browser Cookies**: ใช้ `browser-cookie3` ดึง Session Cookies โดยตรงจาก Chrome, Edge, Firefox, Safari ในเครื่องเพื่อข้ามหน้า Login Wall
* **Netscape Cookies Support**: อ่านไฟล์ `cookies.txt` ในโฟลเดอร์ Root อัตโนมัติ (เหมาะสำหรับการรันบน Docker)
* **Multi-Strategy Fallback ใน `yt-dlp`**:
  1. Standard extraction (ดึงตรง)
  2. ดึงผ่าน Chrome session cookies
  3. ดึงผ่าน Safari session cookies
  4. ใช้ TLS Fingerprint Impersonation (`ImpersonateTarget("chrome")` ผ่าน `curl_cffi`) เพื่อเลียนแบบเบราว์เซอร์จริง

### 2.3 การขูดข้อมูลเชิงลึกผ่าน Playwright (Deep Scraper)
* **Facebook Page & Reels Deep Harvester**:
  - ใช้ Headless Chromium เลื่อนฟีดได้สูงสุดถึง 15,000 รอบ
  - **Network Interception**: ดักจับข้อมูลผ่าน GraphQL และ AJAX Response เพื่อเก็บ Video ID และ Reel URL แม้ว่า DOM ในหน้าเว็บจะถูก Unmount ออกไปเมื่อเลื่อนผ่าน
  - **Popup / Login Overlay Removal**: ลบกล่อง Popup แจ้งเตือนให้เข้าสู่ระบบ (Login Dialog) และปลดล็อก CSS Overflow เพื่อให้เลื่อนฟีดต่อได้ต่อเนื่อง
  - ปลดล็อกอาการค้างของ Infinite Scroll ด้วยการขยับ Mouse, เลื่อนขึ้น (PageUp), และเลื่อนลง (End/PageDown)
* **Facebook Photos & Deep Album Traversal**:
  - รองรับการดาวน์โหลดภาพทั้งเพจ
  - ค้นหาอัลบั้มทั้งหมด และข้ามภาพโปรไฟล์/ภาพหน้าปก (Profile & Cover photos) อัตโนมัติผ่านการ Blacklist fbid
  - รองรับการเรียกใช้ `gallery-dl` เพื่อแปลง Facebook Photo Viewer ให้เป็นลิงก์รูปภาพความละเอียดสูงสุด (High-Resolution)
* **Instagram Profile Scraper**:
  - เลื่อนหน้าโปรไฟล์ Instagram เพื่อสกัดคลิป Reels และ Post ทั้งหมด

### 2.4 Smart Copy-Paste & Batch Extraction
* หากผู้ใช้วางข้อความดิบที่มีหลายลิงก์ หรือกด `Ctrl+A / Cmd+A` แล้วก็อปปี้เนื้อหาหน้าเว็บมาวาง ระบบมีฟังก์ชัน Regex ตรวจจับ URL ของวิดีโอทั้งหมด และจัดคิวดาวน์โหลดแบบ Batch ให้โดยอัตโนมัติ

### 2.5 สถาปัตยกรรมการทำงานแบบ Asynchronous & Job Queue
* ใช้งาน `asyncio.to_thread` แยกงานดาวน์โหลดที่กินเวลาออกจาก Main Event Loop ไม่ทำให้เซิร์ฟเวอร์ค้าง
* มีระบบ **In-Memory Job Tracking**:
  - สร้าง `job_id` (UUID) ให้กับทุกงาน
  - รายงานสถานะแบบ Real-time: `starting`, `scraping`, `downloading`, `completed`, `error`
  - นับจำนวนคลิป/ภาพทั้งหมด (`total_videos`), จำนวนที่โหลดเสร็จแล้ว (`completed_videos`), พร้อมข้อความความคืบหน้า (`progress_message`)

---

## 3. รายการ API Endpoints

### 3.1 `POST /download_job` (แนะนำ)
เริ่มงานดาวน์โหลดหรือขูดข้อมูลในเบื้องหลัง (Background Task)
* **Request Body**:
  ```json
  {
    "url": "https://www.facebook.com/reel/123456789",
    "download_type": "video" // หรือ "image"
  }
  ```
* **Response**:
  ```json
  {
    "success": true,
    "job_id": "c3058a5a-85b4-4b57-a3a8-48b030bb4411",
    "status": "starting"
  }
  ```

### 3.2 `GET /jobs/{job_id}`
ตรวจสอบสถานะและความคืบหน้าของงานดาวน์โหลด
* **Response ตัวอย่าง**:
  ```json
  {
    "id": "c3058a5a-85b4-4b57-a3a8-48b030bb4411",
    "status": "downloading",
    "progress_message": "Downloading video 3 of 10 into VDO/PageName folder...",
    "page_name": "PageName",
    "total_videos": 10,
    "completed_videos": 2,
    "items": [
      {
        "filename": "clip_1.mp4",
        "rel_path": "PageName/clip_1.mp4",
        "download_url": "/files/PageName/clip_1.mp4",
        "title": "Video Clip Title"
      }
    ],
    "error": "",
    "download_type": "video"
  }
  ```

### 3.3 `POST /download`
ดาวน์โหลดวิดีโอเดี่ยวแบบ Synchronous (รอจนโหลดเสร็จแล้วส่งผลลัพธ์กลับทันที)

### 3.4 `GET /files/{filepath:path}`
Endpoint สำหรับดาวน์โหลดหรือสตรีมไฟล์มีเดียที่ดาวน์โหลดเสร็จแล้วจากโฟลเดอร์ `VDO/` หรือ `image/`
* มีระบบป้องกัน Path Traversal Security Attack (`os.path.realpath`) ป้องกันการเข้าถึงไฟล์นอกเหนือจากโฟลเดอร์ที่กำหนด

### 3.5 `GET /health`
ตรวจสอบสถานะความพร้อมของระบบ Backend
* **Response**: `{"status": "ok", "service": "VideoDownloaderBackend"}`

---

## 4. โครงสร้างโฟลเดอร์ไฟล์ที่ดาวน์โหลด

```text
DownlodeVDO-Link/
├── VDO/
│   └── <ชื่อเพจหรือครีเอเตอร์>/
│       ├── clip1_12345678.mp4
│       └── clip2_87654321.mp4
└── image/
    └── <ชื่อเพจหรือครีเอเตอร์>/
        ├── photo_001.jpg
        └── photo_002.jpg
```
