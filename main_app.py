import os
import sys
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
import mss
import mss.tools
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, 
                             QVBoxLayout, QTextEdit, QPushButton, QFrame, QHBoxLayout)
from PyQt6.QtCore import Qt, QRect, QPoint, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QCursor, QFont

# Import โมดูลของคุณ (ตรวจสอบว่าไฟล์เหล่านี้อยู่ครบ)
from hotkey_listener import HotkeyListener
from cloud_processor import process_and_translate, translate_content

# ====================================================================
# 1. Worker Thread (Logic เดิม ไม่มีการแก้ไข)
# ====================================================================
class CloudWorker(QThread):
    finished = pyqtSignal(str, str)
    error = pyqtSignal(str)

    def __init__(self, image_data):
        super().__init__()
        self.image_data = image_data

    def run(self):
        try:
            original, translated = process_and_translate(self.image_data)
            if original:
                self.finished.emit(original, translated)
            else:
                self.error.emit("ไม่พบข้อความ หรือ เกิดข้อผิดพลาด")
        except Exception as e:
            self.error.emit(str(e))

class ManualTranslateWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, text):
        super().__init__()
        self.text = text

    def run(self):
        try:
            translated = translate_content(self.text)
            if translated:
                self.finished.emit(translated)
            else:
                self.error.emit("ไม่สามารถแปลข้อความได้")
        except Exception as e:
            self.error.emit(str(e))

# ====================================================================
# 2. หน้าต่างสำหรับลากคลุมพื้นที่ (Logic เดิม ไม่มีการแก้ไข)
# ====================================================================
class SelectionOverlay(QWidget):
    on_selected = pyqtSignal(bytes)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 100);")
        
        screen_geometry = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        
        self.begin = QPoint()
        self.end = QPoint()
        self.is_selecting = False

    def paintEvent(self, event):
        painter = QPainter(self)
        
        # 1. ถมสีดำจางๆ ทั่วทั้งหน้าจอ (Dim Background)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100)) # ปรับความเข้มที่เลข 100 (0-255)

        if self.is_selecting:
            # คำนวณพื้นที่สี่เหลี่ยม (normalized ช่วยให้ลากย้อนกลับได้ไม่บั๊ก)
            selection_rect = QRect(self.begin, self.end).normalized()

            # 2. เจาะรู (Clear Mask)
            # เปลี่ยนโหมดเป็น DestinationOut: การวาดทับ = การลบออก
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            
            # วาดสี่เหลี่ยมทึบลงไป (สีอะไรก็ได้ ขอแค่ทึบ) ผลลัพธ์คือพื้นที่นี้จะกลายเป็นใสแจ๋ว
            painter.fillRect(selection_rect, QColor(255, 255, 255))
            
            # 3. คืนค่าโหมดปกติ เพื่อวาดเส้นขอบ
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # 4. วาดเส้นขอบสีแดง
            painter.setPen(QPen(QColor(255, 0, 0), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush) # ไม่ถมสี
            painter.drawRect(selection_rect)

    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.end = event.pos()
        self.is_selecting = True
        self.update()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        self.is_selecting = False
        self.close()

        x1 = min(self.begin.x(), self.end.x())
        y1 = min(self.begin.y(), self.end.y())
        x2 = max(self.begin.x(), self.end.x())
        y2 = max(self.begin.y(), self.end.y())
        
        width = x2 - x1
        height = y2 - y1

        if width > 10 and height > 10:
            self.capture_screen(x1, y1, width, height)

    def capture_screen(self, x, y, w, h):
        screen = QApplication.primaryScreen()
        scale_factor = screen.devicePixelRatio()
        x = int(x * scale_factor)
        y = int(y * scale_factor)
        w = int(w * scale_factor)
        h = int(h * scale_factor)
        with mss.mss() as sct:
            monitor = {"top": y, "left": x, "width": w, "height": h}
            sct_img = sct.grab(monitor)
            img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
            self.on_selected.emit(img_bytes)

# ====================================================================
# 3. หน้าต่าง Manual Translate (ปรับปรุง UI)
# ====================================================================
class TranslateWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Torslate - Manual Translate")
        self.resize(900, 600)
        
        # ปรับ Theme เป็น Dark Mode สะอาดตา
        self.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                color: #ffffff;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #00e5ff; /* สีฟ้า */
            }
            QTextEdit {
                background-color: #383838;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
                font-size: 14px;
                color: #e0e0e0;
            }
            QTextEdit:focus {
                border: 1px solid #00e5ff;
            }
            QPushButton {
                background-color: #444;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #555;
            }
            QPushButton:pressed {
                background-color: #666;
            }
            #EnterBtn {
                background-color: #007bff;
                font-weight: bold;
            }
            #EnterBtn:hover {
                background-color: #0056b3;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # ---------- ส่วน English ----------
        en_label = QLabel("English Source")
        self.en_edit = QTextEdit()
        self.en_edit.setPlaceholderText("Paste text here or wait for OCR...")

        en_bottom_layout = QHBoxLayout()
        en_bottom_layout.addStretch()
        
        self.en_copy_btn = QPushButton("Copy Eng")
        self.en_copy_btn.setFixedWidth(80)
        self.en_copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.en_copy_btn.clicked.connect(self.copy_en)
        
        self.enter_btn = QPushButton("Translate")
        self.enter_btn.setObjectName("EnterBtn") # ใช้ ID เพื่อลงสีแยก
        self.enter_btn.setFixedWidth(100)
        self.enter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.enter_btn.clicked.connect(self.manual_translate)
        
        en_bottom_layout.addWidget(self.en_copy_btn)
        en_bottom_layout.addWidget(self.enter_btn)

        # ---------- เส้นคั่น ----------
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #555; height: 1px; border: none;")

        # ---------- ส่วน Thai ----------
        th_label = QLabel("Thai Translation")
        self.th_edit = QTextEdit()
        self.th_edit.setReadOnly(False)
        
        self.th_copy_btn = QPushButton("Copy Thai")
        self.th_copy_btn.setFixedWidth(80)
        self.th_copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.th_copy_btn.clicked.connect(self.copy_th)

        th_bottom_layout = QHBoxLayout()
        th_bottom_layout.addStretch()
        th_bottom_layout.addWidget(self.th_copy_btn)

        # ---------- ประกอบ Layout ----------
        main_layout.addWidget(en_label)
        main_layout.addWidget(self.en_edit)
        main_layout.addLayout(en_bottom_layout)
        main_layout.addSpacing(10)
        main_layout.addWidget(line)
        main_layout.addSpacing(10)
        main_layout.addWidget(th_label)
        main_layout.addWidget(self.th_edit)
        main_layout.addLayout(th_bottom_layout)

        self.manual_worker = None

    def set_ocr_result(self, original: str, translated: str):
        self.en_edit.setPlainText(original)
        self.th_edit.setPlainText(translated)

    def manual_translate(self):
        text = self.en_edit.toPlainText().strip()
        if not text:
            return
        self.enter_btn.setEnabled(False)
        self.enter_btn.setText("Working...")
        self.th_edit.clear()

        self.manual_worker = ManualTranslateWorker(text)
        self.manual_worker.finished.connect(self.on_manual_finished)
        self.manual_worker.error.connect(self.on_manual_error)
        self.manual_worker.start()

    def on_manual_finished(self, translated: str):
        self.th_edit.setPlainText(translated)
        self.enter_btn.setEnabled(True)
        self.enter_btn.setText("Translate")

    def on_manual_error(self, msg: str):
        self.th_edit.setPlainText(msg)
        self.enter_btn.setEnabled(True)
        self.enter_btn.setText("Translate")

    def copy_en(self):
        QApplication.clipboard().setText(self.en_edit.toPlainText())

    def copy_th(self):
        QApplication.clipboard().setText(self.th_edit.toPlainText())


# ====================================================================
# 5. หน้าต่าง Overlay Result (Subtitle Style: Center & No Shift)
# ====================================================================
class OverlayResultWindow(QWidget):
    def __init__(self):
        super().__init__()
        
        # 1. ตั้งค่า Frameless (ไม่มีขอบ)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # ขนาดเริ่มต้น
        self.resize(600, 150)

        # --- Frame หลัก (พื้นหลัง) ---
        # เราใช้ Layout หลักสำหรับ Frame เพื่อให้มันเต็มพื้นที่
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 160); 
                border-radius: 15px;
            }
            QLabel {
                color: #ffffff;
                background-color: transparent;
                border: none;
                font-family: 'Segoe UI', sans-serif;
                font-size: 20px;
                font-weight: 600;
            }
        """)
        main_layout.addWidget(self.frame)

        # --- Text Content (Layer ล่างสุด) ---
        # ใช้ Layout ใน Frame เพื่อจัดข้อความกึ่งกลาง
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(10, 10, 10, 10)
        
        self.text_display = QLabel()
        self.text_display.setAlignment(Qt.AlignmentFlag.AlignCenter) # จัดกึ่งกลางทั้งแนวตั้งและนอน
        self.text_display.setWordWrap(True) # ตัดบรรทัดอัตโนมัติ
        self.text_display.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse) # ให้ลาก Copy ได้
        
        frame_layout.addWidget(self.text_display)

        # --- Header Container (Floating Layer บนสุด) ---
        # หมายเหตุ: เราสร้าง Header ให้เป็นลูกของ self แต่ *ไม่ได้* addWidget เข้า layout
        # เพื่อให้มันลอยอยู่เหนือ content โดยไม่ดันข้อความลงมา
        self.header_widget = QWidget(self)
        self.header_widget.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.2);
                color: #ddd;
                border: none;
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.4);
                color: white;
            }
        """)
        
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(10, 5, 10, 0) # ระยะห่างขอบ (ซ้าย, บน, ขวา, ล่าง)
        
        # ปุ่มสลับภาษา
        self.btn_swap = QPushButton("Show Original (Eng)")
        self.btn_swap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_swap.clicked.connect(self.toggle_view)
        
        # ปุ่มปิด
        self.btn_close = QPushButton("X")
        self.btn_close.setObjectName("closeBtn")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)

        header_layout.addWidget(self.btn_swap)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_close)
        
        # ซ่อนปุ่มไว้ก่อน
        self.header_widget.hide() 
        
        # ตัวแปรเก็บข้อมูล
        self.original_text = ""
        self.translated_text = ""
        self.is_showing_translated = True
        self.old_pos = None

    # --- Resize Event (สำคัญมากสำหรับ Floating Widget) ---
    def resizeEvent(self, event):
        # เมื่อหน้าต่างเปลี่ยนขนาด ต้องสั่งให้ Header กว้างเท่าหน้าต่างเสมอ
        # และอยู่ติดขอบบน (0, 0)
        self.header_widget.setGeometry(0, 0, self.width(), 40) 
        super().resizeEvent(event)

    # --- Mouse Hover Events ---
    def enterEvent(self, event):
        self.header_widget.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.header_widget.hide()
        super().leaveEvent(event)

    # --- Dragging Logic ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.pos() + delta)
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    # --- Content Logic ---
    def set_content(self, original, translated):
        self.original_text = original
        self.translated_text = translated
        
        self.is_showing_translated = True
        self.text_display.setText(translated)
        self.btn_swap.setText("Show Original (Eng)")

    def toggle_view(self):
        if self.is_showing_translated:
            self.text_display.setText(self.original_text)
            self.btn_swap.setText("Show Translated (Thai)")
            self.is_showing_translated = False
        else:
            self.text_display.setText(self.translated_text)
            self.btn_swap.setText("Show Original (Eng)")
            self.is_showing_translated = True

# ====================================================================
#  Main Application Entry Point
# ====================================================================
class MainController(QMainWindow):
    def __init__(self):
        super().__init__()
        # ... (ส่วน UI Setup เดิม ละไว้ในฐานที่เข้าใจ) ...
        self.setWindowTitle("Torslate")
        self.resize(500, 350)
        # (Copy Stylesheet เดิมมาใส่ตรงนี้ได้เลยครับ)
        self.setStyleSheet("QMainWindow { background-color: #1e1e1e; } QLabel { color: #e0e0e0; }") 

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        title = QLabel("Torslate")
        title.setStyleSheet("font-size: 30px; color: #00e5ff; font-weight: bold;")
        layout.addWidget(title)
        
        info = QLabel("Ctrl+Alt+T: Normal Mode\nCtrl+Alt+R: Set Region\nCtrl+Alt+E: Translate Region")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)
        
        self.setCentralWidget(central_widget)

        # ---------- Logic ----------
        self.hotkey_thread = HotkeyListener()
        self.hotkey_thread.on_trigger.connect(self.start_selection)           # T (เดิม)
        self.hotkey_thread.on_trigger_region_set.connect(self.start_region_set)       # R (ใหม่)
        self.hotkey_thread.on_trigger_story_translate.connect(self.start_story_translate) # E (ใหม่)
        self.hotkey_thread.start()

        self.selection_window = None
        self.region_selector = None      # ตัวลากเส้นใหม่
        self.story_indicator = None      # กรอบขาวค้างหน้าจอ
        self.saved_story_rect = None     # เก็บพิกัด QRect
        
        self.worker = None
        self.translate_window = None     
        self.overlay_result_window = None
        
        self.last_result_pos = None      # จำตำแหน่งหน้าต่างผลลัพธ์

    # ==========================================
    # Logic เดิม (Ctrl + Alt + T)
    # ==========================================
    def start_selection(self):
        print(">>> Mode: Standard Capture")
        self.selection_window = SelectionOverlay()
        self.selection_window.on_selected.connect(self.process_image)
        self.selection_window.show()
        self.selection_window.activateWindow()
        self.selection_window.raise_()

    def process_image(self, image_data):
        self.worker = CloudWorker(image_data)
        self.worker.finished.connect(self.show_ocr_result)
        self.worker.error.connect(self.show_ocr_error)
        self.worker.start()

    # ==========================================
    # Logic ใหม่ (Story Mode)
    # ==========================================
    def start_region_set(self):
        """Ctrl+Alt+R: เปิดตัวลากเพื่อจำพิกัด"""
        print(">>> Mode: Set Story Region")
        # ปิดตัวเก่าถ้ามี
        if self.story_indicator:
            self.story_indicator.close()
            self.story_indicator = None
            
        self.region_selector = RegionSelector()
        self.region_selector.on_region_selected.connect(self.set_story_region)
        self.region_selector.show()
        self.region_selector.activateWindow()
        self.region_selector.raise_()

    def set_story_region(self, rect):
        """บันทึกพิกัด และสร้างกรอบขาว"""
        self.saved_story_rect = rect
        print(f"Region Saved: {rect}")
        
        # สร้างกรอบขาวค้างไว้ (คลิกทะลุได้)
        self.story_indicator = StoryRegionIndicator(rect)
        self.story_indicator.show()

    def start_story_translate(self):
        """Ctrl+Alt+E: แปลจากพิกัดเดิมทันที"""
        if not self.saved_story_rect:
            print("Error: No region set! Press Ctrl+Alt+R first.")
            # แจ้งเตือนถ้ายังไม่ตั้งค่า
            self.show_ocr_error("กรุณากด Ctrl+Alt+R เพื่อกำหนดขอบเขตก่อน")
            return

        print(">>> Mode: Story Translate (Fixed Region)")
        
        # คำนวณ Physical Pixels สำหรับ mss
        screen = QApplication.primaryScreen()
        scale = screen.devicePixelRatio()
        
        rect = self.saved_story_rect
        x = int(rect.x() * scale)
        y = int(rect.y() * scale)
        w = int(rect.width() * scale)
        h = int(rect.height() * scale)

        # จับภาพทันที (ไม่ต้องลาก)
        try:
            with mss.mss() as sct:
                monitor = {"top": y, "left": x, "width": w, "height": h}
                sct_img = sct.grab(monitor)
                img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
                
                # ส่งไปแปล (ใช้ Logic เดียวกับ process_image)
                self.process_image(img_bytes)
        except Exception as e:
            print(f"Capture Error: {e}")

    # ==========================================
    # Shared Logic (การแสดงผล)
    # ==========================================
    def show_ocr_result(self, original, translated):
        if self.overlay_result_window is None:
            self.overlay_result_window = OverlayResultWindow()
            # ดักจับ Event การเคลื่อนย้ายเพื่อจำตำแหน่ง
            self.overlay_result_window.moveEvent = self.save_window_pos
        
        self.overlay_result_window.set_content(original, translated)
        
        # ถ้ามีตำแหน่งจำไว้ ให้ใช้ตำแหน่งเดิม
        if self.last_result_pos:
            self.overlay_result_window.move(self.last_result_pos)
        else:
            # ถ้าไม่มี (ครั้งแรก) ให้ไปโผล่ใกล้ๆ เมาส์
            cursor_pos = QCursor.pos()
            self.overlay_result_window.move(cursor_pos.x() + 20, cursor_pos.y() + 20)
        
        self.overlay_result_window.show()
        self.overlay_result_window.raise_()
        self.overlay_result_window.activateWindow()

    def save_window_pos(self, event):
        # ฟังก์ชันนี้จะถูกเรียกเมื่อหน้าต่าง Overlay ถูกลาก
        if self.overlay_result_window:
            self.last_result_pos = self.overlay_result_window.pos()
        # เรียก implementation เดิมด้วยเพื่อไม่ให้การลากพัง
        super(OverlayResultWindow, self.overlay_result_window).moveEvent(event)

    def show_ocr_error(self, error_msg):
        if self.overlay_result_window is None:
            self.overlay_result_window = OverlayResultWindow()
        self.overlay_result_window.set_content("Error", error_msg)
        self.overlay_result_window.show()
        
    def open_translate_window(self):
        if self.translate_window is None:
            self.translate_window = TranslateWindow()
        self.translate_window.show()


# ====================================================================
# 6. (NEW) หน้าต่างสำหรับลากกำหนดพื้นที่ (Region Selector)
# ====================================================================
class RegionSelector(QWidget):
    on_region_selected = pyqtSignal(QRect) # ส่งพิกัดกลับไป (ไม่ใช่รูปภาพ)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 100);")
        
        screen_geometry = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        
        self.begin = QPoint()
        self.end = QPoint()
        self.is_selecting = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 50)) 

        if self.is_selecting:
            selection_rect = QRect(self.begin, self.end).normalized()
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
            painter.fillRect(selection_rect, QColor(255, 255, 255))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            
            # วาดกรอบสีเขียว เพื่อให้รู้ว่าเป็นโหมด Set Region
            painter.setPen(QPen(QColor(0, 255, 0), 2)) 
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(selection_rect)

    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.end = event.pos()
        self.is_selecting = True
        self.update()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        self.is_selecting = False
        self.close()

        rect = QRect(self.begin, self.end).normalized()
        if rect.width() > 10 and rect.height() > 10:
            self.on_region_selected.emit(rect) # ส่งพิกัดกลับไป

# ====================================================================
# 7. (NEW) กรอบขาวแสดงพื้นที่ Story Mode (Indicator)
# ====================================================================
class StoryRegionIndicator(QWidget):
    def __init__(self, rect):
        super().__init__()
        # ตั้งค่าให้เป็น Overlay ที่คลิกทะลุได้ (TransparentForMouseEvents)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput # <--- สำคัญ! คลิกทะลุได้
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        # ตั้งตำแหน่งตาม Rect ที่ส่งมา
        self.setGeometry(rect)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        # วาดกรอบขาวบางๆ
        painter.setPen(QPen(QColor(255, 255, 255, 128), 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, self.width()-1, self.height()-1)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    controller = MainController()
    controller.show()
    sys.exit(app.exec())