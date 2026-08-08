import os
import time
import requests
import shutil
import glob
from pathlib import Path

# ==========================================
# ⚙️ การตั้งค่า (Configuration)
# ==========================================
# นำ Page Access Token และ Page ID มาใส่ตรงนี้ 
# หรือดึงจากไฟล์ .env โดยใช้ os.environ.get("FB_PAGE_ACCESS_TOKEN")
PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN", "YOUR_PAGE_ACCESS_TOKEN_HERE")
PAGE_ID = os.environ.get("FB_PAGE_ID", "YOUR_PAGE_ID_HERE")

# กำหนดโฟลเดอร์สำหรับอ่านวิดีโอ และโฟลเดอร์สำหรับเก็บวิดีโอที่โพสต์แล้ว
BASE_DIR = Path(__file__).parent.resolve()
VDO_DIR = BASE_DIR / "VDO"
POSTED_DIR = BASE_DIR / "VDO_posted"

def setup_directories():
    """สร้างโฟลเดอร์ถ้ายังไม่มี"""
    VDO_DIR.mkdir(parents=True, exist_ok=True)
    POSTED_DIR.mkdir(parents=True, exist_ok=True)

def get_oldest_video():
    """ค้นหาวิดีโอที่เก่าที่สุดในโฟลเดอร์ VDO"""
    # ค้นหาไฟล์ .mp4 (สามารถเพิ่มนามสกุลอื่นได้ถ้าต้องการ)
    video_files = list(VDO_DIR.glob("*.mp4"))
    
    if not video_files:
        return None
    
    # เรียงตามเวลาที่สร้างไฟล์ หรือ แก้ไขไฟล์ (เก่าที่สุดไปใหม่ที่สุด)
    video_files.sort(key=lambda x: x.stat().st_mtime)
    return video_files[0]

def post_video_to_facebook(video_path: Path):
    """ฟังก์ชันอัปโหลดวิดีโอไปยัง Facebook Page"""
    print(f"กำลังอัปโหลดวิดีโอ: {video_path.name} ...")
    
    url = f"https://graph.facebook.com/v19.0/{PAGE_ID}/videos"
    
    # กำหนดแคปชั่น (สามารถดึงจากชื่อไฟล์ หรือตั้งค่าแบบอื่นได้)
    description = f"Auto Post: {video_path.stem}\n#AutoPost #Video"
    
    payload = {
        'access_token': PAGE_ACCESS_TOKEN,
        'description': description
    }
    
    try:
        with open(video_path, 'rb') as f:
            files = {
                'file': (video_path.name, f, 'video/mp4')
            }
            # Facebook Graph API สำหรับ Video อัปโหลดอาจจะใช้เวลาสักพักขึ้นอยู่กับขนาดไฟล์
            response = requests.post(url, data=payload, files=files)
            
        result = response.json()
        
        if response.status_code == 200 and 'id' in result:
            print(f"✅ โพสต์สำเร็จ! Video ID: {result['id']}")
            return True
        else:
            print(f"❌ เกิดข้อผิดพลาดในการโพสต์: {result}")
            return False
            
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดในระบบ: {e}")
        return False

def main():
    print("เริ่มทำงาน Facebook Auto Poster...")
    setup_directories()
    
    # ตรวจสอบการตั้งค่า
    if PAGE_ACCESS_TOKEN == "YOUR_PAGE_ACCESS_TOKEN_HERE" or PAGE_ID == "YOUR_PAGE_ID_HERE":
        print("⚠️ กรุณาตั้งค่า PAGE_ACCESS_TOKEN และ PAGE_ID ในโค้ดก่อนใช้งาน")
        return
        
    video_to_post = get_oldest_video()
    
    if not video_to_post:
        print("ไม่พบวิดีโอใหม่ในโฟลเดอร์ VDO รอการทำงานรอบต่อไป...")
        return
        
    print(f"พบวิดีโอที่พร้อมโพสต์: {video_to_post.name}")
    
    # โพสต์วิดีโอ
    success = post_video_to_facebook(video_to_post)
    
    # ถ้าย้ายสำเร็จ หรือถ้าจะบังคับย้ายไปโฟลเดอร์อื่น 
    if success:
        destination = POSTED_DIR / video_to_post.name
        # ถ้าย้ายไฟล์แล้วมีชื่อซ้ำ ให้เติม timestamp
        if destination.exists():
            new_name = f"{video_to_post.stem}_{int(time.time())}{video_to_post.suffix}"
            destination = POSTED_DIR / new_name
            
        shutil.move(str(video_to_post), str(destination))
        print(f"📁 ย้ายไฟล์ไปที่: {destination.relative_to(BASE_DIR)}")
    else:
        print("ข้ามการย้ายไฟล์เนื่องจากโพสต์ไม่สำเร็จ")

if __name__ == "__main__":
    main()
