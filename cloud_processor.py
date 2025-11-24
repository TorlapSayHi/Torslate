import os
import io
from google.cloud import vision
from google.cloud import translate_v2 as translate # ใช้ v2 สำหรับการเรียกแบบง่าย
from google.api_core.exceptions import GoogleAPICallError
from typing import Optional, Tuple

# ====================================================================
# I. Fuction สำหรับ OCR (Google Cloud Vision API)
# ====================================================================

def process_image_to_text(image_data: bytes) -> Optional[str]:
    """
    ดึงข้อความทั้งหมดจากข้อมูลรูปภาพไบนารีโดยใช้ Google Cloud Vision API.

    Args:
        image_data: ข้อมูลรูปภาพในรูปแบบไบนารี (bytes) ที่ได้จากการจับภาพหน้าจอ

    Returns:
        ข้อความที่สแกนได้ทั้งหมดในรูปแบบ string หรือ None หากเกิดข้อผิดพลาด.
    """
    try:
        # สร้าง Client สำหรับ Vision API
        # Client จะใช้ GOOGLE_APPLICATION_CREDENTIALS ในการยืนยันตัวตน
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_data)

        # เรียกใช้ Text Detection
        response = client.text_detection(image=image)
        texts = response.text_annotations

        if texts:
            # texts[0].description คือข้อความทั้งหมดที่สแกนเจอในรูปภาพ
            original_text = texts[0].description.strip()
            return original_text
        
        print("INFO: ไม่พบข้อความใด ๆ ในรูปภาพที่สแกน.")
        return None

    except GoogleAPICallError as e:
        print(f"ERROR: การเรียกใช้ Google Vision API ล้มเหลว: {e}")
        return None
    except Exception as e:
        print(f"ERROR: เกิดข้อผิดพลาดที่ไม่คาดคิดในการทำ OCR: {e}")
        return None

# ====================================================================
# II. Fuction สำหรับ Translation (Google Cloud Translation API)
# ====================================================================

def translate_content(text_content: str, target_language: str = 'th', source_language: str = 'en') -> Optional[str]:
    """
    แปลข้อความที่กำหนดโดยใช้ Google Cloud Translation API (v2).

    Args:
        text_content: ข้อความต้นฉบับที่จะแปล
        target_language: รหัสภาษาปลายทาง (เช่น 'th' สำหรับไทย)
        source_language: รหัสภาษาต้นทาง (เช่น 'en' สำหรับอังกฤษ)

    Returns:
        ข้อความที่แปลแล้วในรูปแบบ string หรือ None หากเกิดข้อผิดพลาด.
    """
    if not text_content:
        return None
    
    try:
        # สร้าง Client สำหรับ Translation API (ใช้ v2 เพื่อความง่ายในการเรียก)
        client = translate.Client()

        # ทำการแปล
        result = client.translate(
            text_content,
            target_language=target_language,
            source_language=source_language
        )
        
        translated_text = result['translatedText'].strip()
        return translated_text

    except GoogleAPICallError as e:
        print(f"ERROR: การเรียกใช้ Google Translation API ล้มเหลว: {e}")
        return None
    except Exception as e:
        print(f"ERROR: เกิดข้อผิดพลาดที่ไม่คาดคิดในการแปล: {e}")
        return None

# ====================================================================
# III. ฟังก์ชันรวม (Main Processing)
# ====================================================================

def process_and_translate(image_data: bytes) -> Tuple[Optional[str], Optional[str]]:
    """
    ฟังก์ชันหลักที่รวมการทำ OCR และการแปลภาษาเข้าด้วยกัน
    
    Returns:
        tuple (ข้อความต้นฉบับ, ข้อความที่แปลแล้ว)
    """
    # 1. ทำ OCR เพื่อดึงข้อความ
    original_text = process_image_to_text(image_data)
    
    if not original_text:
        return None, "ไม่สามารถดึงข้อความจากรูปภาพได้"

    # 2. ทำ Translation
    translated_text = translate_content(original_text)
    
    if not translated_text:
        return original_text, "ไม่สามารถแปลข้อความได้"

    return original_text, translated_text


# ====================================================================
# IV. ตัวอย่างการใช้งานและทดสอบ
# ====================================================================

if __name__ == '__main__':
    # ทดสอบโดยใช้ไฟล์รูปภาพจริงในโปรเจกต์ของคุณ
    TEST_IMAGE_PATH = 'torslate.png'
    
    if not os.path.exists(TEST_IMAGE_PATH):
        print(f"ERROR: ไม่พบไฟล์ทดสอบ '{TEST_IMAGE_PATH}' โปรดสร้างไฟล์ภาพที่มีข้อความภาษาอังกฤษเพื่อทดสอบ")
    else:
        # อ่านไฟล์ภาพเป็นข้อมูลไบนารี
        with open(TEST_IMAGE_PATH, 'rb') as f:
            test_image_data = f.read()

        print("--- เริ่มการประมวลผล Cloud API ---")
        
        # เรียกใช้ฟังก์ชันหลัก
        original, translated = process_and_translate(test_image_data)
        
        print("\n--- ผลลัพธ์ ---")
        if original and translated:
            # ถ้าต้องการจำกัดข้อความต้นฉบับที่แสดง ให้ใช้บรรทัดด้านล่างแทน
            # print(f"Original Text (สแกนได้):\n{original[:100]}...")
            print(f"Original Text (สแกนได้):\n{original}")
            print("\n------------------------------")
            print(f"Translated Text (แปลแล้ว):\n{translated}")
        elif original:
            print(f"Original Text (สแกนได้):\n{original}")
            print("\n⚠️ การแปลล้มเหลว (ตรวจสอบ API Key และ Quota)")
        else:
            print("❌ การประมวลผลล้มเหลวโดยสมบูรณ์")
        print("------------------------------")