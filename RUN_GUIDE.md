# 📖 คู่มือการรันระบบ (System Run Guide)
> **DownlodeVDO-Link: Simple Multi-Platform Video Downloader & Processing Suite**

คู่มือนี้สรุปขั้นตอนและวิธีการรันระบบทั้งหมดในโปรเจกต์ ทั้งการเปิดใช้งานหน้าเว็บ (Web UI), การสั่งรันผ่านคำสั่ง (CLI), การรันผ่าน Docker, และการใช้สคริปต์เสริมต่าง ๆ เช่น การดึงคลิป, การแปลงไฟล์ และการแต่งวิดีโอ

---

## 📑 สารบัญ
1. [สิ่งที่ต้องมีก่อนเริ่มใช้งาน (Prerequisites)](#1-สิ่งที่ต้องมีก่อนเริ่มใช้งาน-prerequisites)
2. [วิธีรันระบบหลัก (Web Application & Backend)](#2-วิธีรันระบบหลัก-web-application--backend)
   - [วิธีที่ 1: รันแบบคลิกเดียว (แนะนำสำหรับ Windows)](#วิธีที่-1-รันแบบคลิกเดียวจบ-1-click-start-แนะนำสำหรับ-windows)
   - [วิธีที่ 2: รันผ่าน Terminal / Command Line](#วิธีที่-2-รันผ่าน-terminal--command-line)
   - [วิธีที่ 3: รันผ่าน Docker Compose](#วิธีที่-3-รันผ่าน-docker-compose)
3. [การเข้าใช้งานระบบหน้าเว็บ (Web UI)](#3-การเข้าใช้งานระบบหน้าเว็บ-web-ui)
4. [การใช้งานสคริปต์และเครื่องมือเสริม (Tools & Automation)](#4-การใช้งานสคริปต์และเครื่องมือเสริม-tools--automation)
   - [4.1 สคริปต์ดึงลิงก์ Facebook Reels จำนวนมาก (Reels Dumper)](#41-สคริปต์ดึงลิงก์-facebook-reels-จำนวนมาก-reels-dumper)
   - [4.2 การดึง Cookie สำหรับคลิปที่ต้องล็อกอิน (Cookies Setup)](#42-การดึง-cookie-สำหรับคลิปที่ต้องล็อกอิน-cookies-setup)
   - [4.3 สคริปต์แปลง/แต่งวิดีโอแบบกลุ่ม (Batch Processing & Anti-Detection)](#43-สคริปต์แปลงแต่งวิดีโอแบบกลุ่ม-batch-processing--anti-detection)
   - [4.4 สคริปต์โพสต์วิดีโออัตโนมัติลง Facebook (Facebook Autoposter)](#44-สคริปต์โพสต์วิดีโออัตโนมัติลง-facebook-facebook-autoposter)
5. [โครงสร้างโฟลเดอร์สำหรับเก็บไฟล์](#5-โครงสร้างโฟลเดอร์สำหรับเก็บไฟล์)
6. [การแก้ไขปัญหาที่พบบ่อย (Troubleshooting)](#6-การแก้ไขปัญหาที่พบบ่อย-troubleshooting)

---

## 1. สิ่งที่ต้องมีก่อนเริ่มใช้งาน (Prerequisites)

สำหรับการรันบนคอมพิวเตอร์โดยตรง (Local Windows):

* **Python:** เวอร์ชัน 3.10 ขึ้นไป
* **FFmpeg:** ติดตั้งและเซ็ตใน Environment Variable (`PATH`) เพื่อรวมภาพและเสียงเป็น MP4 (H.264/AAC)
* **Playwright Browsers:** สำหรับฟังก์ชันขูดข้อมูลหน้าเว็บอัตโนมัติ
* **Node.js (ทางเลือก):** สำหรับนักพัฒนาที่ต้องการแก้ไขซอร์สโค้ดหน้าบ้าน React (Vite)

> [!TIP]
> ตรวจสอบความพร้อมของระบบได้ด้วยคำสั่ง:
> ```powershell
> python --version
> ffmpeg -version
> ```

หากยังไม่ได้ติดตั้ง Library ที่จำเป็น ให้รันคำสั่ง:
```powershell
pip install -r backend/requirements.txt
playwright install chromium
```

---

## 2. วิธีรันระบบหลัก (Web Application & Backend)

### วิธีที่ 1: รันแบบคลิกเดียวจบ (1-Click Start) *(แนะนำสำหรับ Windows)*

1. ไปที่โฟลเดอร์โปรเจกต์ `DownlodeVDO-Link`
2. ดับเบิ้ลคลิกไฟล์ **`start.bat`**
3. ระบบจะทำงานดังนี้:
   - สตาร์ตเซิร์ฟเวอร์ FastAPI และ Web Interface ที่พอร์ต `8000`
   - เปิดหน้าเบราว์เซอร์ไปที่ **http://localhost:8000** ให้ทันทีอัตโนมัติ

---

### วิธีที่ 2: รันผ่าน Terminal / Command Line

#### 2.1 รัน Backend แบบ Production / Single-Port (รวมหน้าเว็บในตัว)
ระบบ Backend ถูกตั้งค่าให้เสิร์ฟหน้าเว็บ React (จากโฟลเดอร์ `frontend/dist`) ผ่านพอร์ต 8000 ได้ทันที:

```powershell
# เปิด Terminal ที่โฟลเดอร์โปรเจกต์
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
* **เข้าหน้าเว็บได้ที่:** [http://localhost:8000](http://localhost:8000)
* **เข้าดู API Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)

#### 2.2 รันสำหรับนักพัฒนา Frontend (Vite Dev Server มี Hot-Reload)
หากต้องการแก้ไขโค้ดหน้าเว็บใน `frontend/src`:

```powershell
# หน้าต่างที่ 1: รัน Backend
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# หน้าต่างที่ 2: รัน Frontend Vite Server
cd frontend
npm run dev
```
* **เข้าพัฒนาหน้าเว็บได้ที่:** [http://localhost:5173](http://localhost:5173)

---

### วิธีที่ 3: รันผ่าน Docker Compose

หากมี **Docker Desktop** สามารถรันทั้งระบบได้โดยไม่ต้องติดตั้ง Python หรือ FFmpeg:

```bash
# สั่งสตาร์ตระบบในโหมด Background
docker compose up -d

# ดู Log การทำงาน
docker compose logs -f

# หยุดการทำงาน
docker compose down
```
* **เข้าหน้าเว็บได้ที่:** [http://localhost:8000](http://localhost:8000)
* วิดีโอจะถูกบันทึกมายังโฟลเดอร์ `VDO/` ในคอมพิวเตอร์ของคุณอัตโนมัติ

---

## 3. การเข้าใช้งานระบบหน้าเว็บ (Web UI)

เมื่อเปิด [http://localhost:8000](http://localhost:8000) จะพบหน้าต่างดาวน์โหลด:

1. **URL Input:** วางลิงก์วิดีโอ (รองรับทั้งลิงก์เดี่ยว, หลายลิงก์พร้อมกัน, หรือคัดลอกข้อความยาว ๆ มาวาง)
   - แพลตฟอร์มที่รองรับ: **TikTok, Facebook, Instagram, YouTube**
2. **ตัวเลือกเสริม (Video Enhancements):**
   - 🔄 **Flip Horizontally:** พลิกวิดีโอกลับด้านซ้าย-ขวา
   - ✨ **Boost Brightness & Contrast:** ปรับภาพสว่างและคอนทราสต์เล็กน้อย
   - 🛡️ **Anti-Detection Suite:** เปิดระบบ 6-layer หลบเลี่ยงการตรวจจับลิขสิทธิ์ / ลายพิมพ์ดิจิทัล (สปีด, พิทช์เสียง, คลื่นเสียง)
   - ✍️ **Watermark:** พิมพ์ข้อความลายน้ำ ระบุตำแหน่ง และความโปร่งใส
3. กดปุ่ม **Start Download** แล้วระบบจะแสดงแถบสถานะ (Progress Bar) และดาวน์โหลดเก็บลงโฟลเดอร์ [VDO](file:///c:/Users/opal/Desktop/C++/DownlodeVDO-Link/VDO) ทันที

---

## 4. การใช้งานสคริปต์และเครื่องมือเสริม (Tools & Automation)

### 4.1 สคริปต์ดึงลิงก์ Facebook Reels จำนวนมาก (Reels Dumper)
ใช้เมื่อต้องการดึงลิงก์ Reels จากเพจหรือโปรไฟล์ Facebook ทั้งหมดออกมาเป็นไฟล์ข้อความ:

* **วิธีที่ 1:** ดับเบิ้ลคลิกไฟล์ `run_dumper.bat`
* **วิธีที่ 2:** รันคำสั่งผ่าน Command Line:
  ```powershell
  python dump_fb_reels.py "https://www.facebook.com/profile.php?id=100050575355583&sk=reels_tab"
  ```
* **ผลลัพธ์:** ลิงก์ทั้งหมดจะถูกบันทึกลงไฟล์ `reels_links.txt` แบบเรียลไทม์ พร้อมหยุดอัตโนมัติเมื่อสิ้นสุดคลิปของครีเอเตอร์

---

### 4.2 การดึง Cookie สำหรับคลิปที่ต้องล็อกอิน (Cookies Setup)
หากต้องการดาวน์โหลดคลิปจำกัดสิทธิ์ / เฉพาะเพื่อน / 18+ บน Facebook หรือ Instagram:

#### วิธี A: ล็อกอินผ่านหน้าต่างช่วยอัตโนมัติ (แนะนำ)
1. ดับเบิ้ลคลิกไฟล์ `login_facebook.bat` หรือรัน:
   ```powershell
   python login_facebook.py
   ```
2. หน้าต่างเบราว์เซอร์จะเปิดขึ้นมา ให้ล็อกอิน Facebook ตามปกติ
3. เมื่อเข้าสู่ระบบสำเร็จ สคริปต์จะบันทึกคุกกี้ลงไฟล์ `cookies.txt` และปิดตัวเองอัตโนมัติ

#### วิธี B: ดึง Cookie จาก Google Chrome โดยตรง
```powershell
python extract_cookies_auto.py
```
*(ต้องล็อกอิน Facebook อยู่ในเบราว์เซอร์ Chrome)*

---

### 4.3 สคริปต์แปลง/แต่งวิดีโอแบบกลุ่ม (Batch Processing & Anti-Detection)
หากมีคลิปดิบดาวน์โหลดอยู่ในโฟลเดอร์ `VDO/<ชื่อครีเอเตอร์>/` แล้วต้องการนำมาแปลงใส่ลายน้ำ พลิกวิดีโอ หรือใส่ระบบกัน AI ตรวจจับ:

```powershell
# รันแต่งวิดีโอทั้งหมดของโฟลเดอร์ที่ระบุ
python batch_process_existing.py --creator "นางฟ้าชัดๆ" --watermark "@YourBrand" --anti-detection
```

**ตัวเลือกเสริมของสคริปต์:**
| Argument | คำอธิบาย | ค่าเริ่มต้น |
| :--- | :--- | :--- |
| `--creator` | ชื่อโฟลเดอร์ย่อยใน `VDO/` | `นางฟ้าชัดๆ` |
| `--no-flip` | ปิดการพลิกวิดีโอซ้าย-ขวา | เปิดพลิกอยู่แล้ว |
| `--no-brighten` | ปิดการปรับความสว่าง | เปิดปรับสว่างอยู่แล้ว |
| `--watermark` | ข้อความลายน้ำ | `@SoSoCute Girl TH` |
| `--opacity` | ความโปร่งใสของลายน้ำ (0.05 - 1.0) | `0.25` |
| `--anti-detection` | เปิดระบบป้องกันการตรวจจับ 6 เลเยอร์ | ปิดอยู่ |
| `--overwrite` | สั่งให้ประมวลผลซ้ำแม้ไฟล์เดิมมีอยู่แล้ว | ข้ามไฟล์เดิม |

* **ผลลัพธ์:** ไฟล์ที่ประมวลผลแล้วจะถูกบันทึกไว้ในโฟลเดอร์ [VDO_processed](file:///c:/Users/opal/Desktop/C++/DownlodeVDO-Link/VDO_processed)

---

### 4.4 สคริปต์โพสต์วิดีโออัตโนมัติลง Facebook (Facebook Autoposter)
นำไฟล์วิดีโอจากโฟลเดอร์ `VDO/` ไปโพสต์ลง Facebook Page อัตโนมัติ:

1. ใส่ **Page Access Token** และ **Page ID** ในไฟล์ [facebook_autoposter.py](file:///c:/Users/opal/Desktop/C++/DownlodeVDO-Link/facebook_autoposter.py) หรือใน `.env`
2. รันคำสั่ง:
   ```powershell
   python facebook_autoposter.py
   ```
3. เมื่อโพสต์เสร็จ ไฟล์จะถูกย้ายไปเก็บที่ `VDO_posted/` อัตโนมัติ

---

## 5. โครงสร้างโฟลเดอร์สำหรับเก็บไฟล์

```
DownlodeVDO-Link/
├── 📂 VDO/                 # คลิปวิดีโอดิบที่ดาวน์โหลดมา (แยกตามชื่อครีเอเตอร์/ช่อง)
├── 📂 VDO_processed/       # คลิปที่ผ่านการแต่ง/พลิก/ใส่ลายน้ำ/Anti-detection แล้ว
├── 📂 VDO_posted/          # คลิปที่ถูกนำไปโพสต์ขึ้น Facebook แล้ว
├── 📂 image/               # รูปภาพที่ดาวน์โหลดมา (เช่น Facebook Photos / Instagram Posts)
├── 📄 cookies.txt          # ไฟล์คุกกี้ Netscape สำหรับคลิปที่ต้องยืนยันตัวตน
├── 📄 reels_links.txt      # รายการลิงก์คลิปที่ได้จากการขูดข้อมูล
└── 📄 target.txt           # รายชื่อช่องหรือลิงก์เป้าหมายที่ต้องการโหลด
```

---

## 6. การแก้ไขปัญหาที่พบบ่อย (Troubleshooting)

### ❓ ปัญหา 1: พอร์ต 8000 ชน (Address already in use)
**สาเหตุ:** มีกระบวนการหรือ Uvicorn เก่าทำงานค้างอยู่  
**วิธีแก้ไข:**
```powershell
# ตรวจสอบว่า Process อะไรใช้พอร์ต 8000
netstat -ano | findstr :8000
# หรือปิด Python Process ทั้งหมด:
Stop-Process -Name python -Force
```

### ❓ ปัญหา 2: ไม่พบคำสั่ง FFmpeg (`ffmpeg is not recognized`)
**สาเหตุ:** ยังไม่ได้ติดตั้ง FFmpeg หรือไม่ได้ตั้งค่า PATH ใน Windows  
**วิธีแก้ไข:**
1. ดาวน์โหลด FFmpeg จาก [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)
2. นำโฟลเดอร์ `bin` (ที่มี `ffmpeg.exe`) ไปใส่ใน **System Environment Variables -> Path**
3. ปิดแล้วเปิด Terminal ใหม่ ทดสอบด้วย `ffmpeg -version`

### ❓ ปัญหา 3: Playwright แจ้งเตือนว่าไม่พบ Chromium (`Executable doesn't exist`)
**วิธีแก้ไข:**
```powershell
playwright install chromium
```

### ❓ ปัญหา 4: ดาวน์โหลดคลิป Facebook / Instagram ไม่ได้ หรือได้ไฟล์ขนาด 0 KB
**วิธีแก้ไข:**
- วิดีโอดังกล่าวอาจตั้งค่าเป็นส่วนบุคคลหรือจำกัดอายุ
- ให้รัน `login_facebook.bat` หรืออัปเดตไฟล์ `cookies.txt` ใหม่เพื่อให้ระบบเข้าถึงคลิปได้
