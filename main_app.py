import os
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
import sys
import mss
import mss.tools
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, 
                             QVBoxLayout, QTextEdit, QPushButton, QFrame)
from PyQt6.QtCore import Qt, QRect, QPoint, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QPen, QColor, QCursor

# Import โมดูลของคุณ
from hotkey_listener import HotkeyListener
from cloud_processor import process_and_translate

# ====================================================================
# 1. Worker Thread สำหรับเรียก Cloud API (เพื่อไม่ให้จอค้าง)
# ====================================================================
class CloudWorker(QThread):
    finished = pyqtSignal(str, str) # ส่งค่า (original, translated) กลับเมื่อเสร็จ
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

# ====================================================================
# 2. หน้าต่างสำหรับลากคลุมพื้นที่ (Selection Overlay)
# ====================================================================
class SelectionOverlay(QWidget):
    on_selected = pyqtSignal(bytes) # ส่งข้อมูลภาพกลับเมื่อเลือกเสร็จ

    # ใน class SelectionOverlay(QWidget):

    def __init__(self):
        super().__init__()
        
        # 1. ตั้งค่า Flag ที่จำเป็นเท่านั้น (Frameless, Always On Top)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint
        )
        
        # 2. ตั้งค่า Translucency และ CSS (ทำให้เกิดสีดำจางๆ)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 100);")
        
        # 3. ใช้ PrimaryScreen เพื่อกำหนดขนาดเต็มจอ (แนะนำใน PyQt6)
        screen_geometry = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        
        self.begin = QPoint()
        self.end = QPoint()
        self.is_selecting = False

    def paintEvent(self, event):
        painter = QPainter(self)
        
        # 1. วาดพื้นหลังทับจอด้วยสีดำจางๆ ตลอดเวลา
        painter.fillRect(self.rect(), QColor(0, 0, 0, 50)) 

        # 2. วาดกรอบสีแดงตอนลาก
        if self.is_selecting:
            painter.setPen(QPen(QColor(255, 0, 0), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            rect = QRect(self.begin, self.end)
            painter.drawRect(rect)

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
        self.close() # ปิดหน้าต่าง Overlay

        # คำนวณพื้นที่ที่เลือก
        x1 = min(self.begin.x(), self.end.x())
        y1 = min(self.begin.y(), self.end.y())
        x2 = max(self.begin.x(), self.end.x())
        y2 = max(self.begin.y(), self.end.y())
        
        width = x2 - x1
        height = y2 - y1

        if width > 10 and height > 10: # ต้องลากกว้างพอสมควร
            self.capture_screen(x1, y1, width, height)

    def capture_screen(self, x, y, w, h):
        # ใช้ mss จับภาพหน้าจอตามพิกัด
        with mss.mss() as sct:
            monitor = {"top": y, "left": x, "width": w, "height": h}
            sct_img = sct.grab(monitor)
            
            # แปลงเป็น bytes png
            img_bytes = mss.tools.to_png(sct_img.rgb, sct_img.size)
            self.on_selected.emit(img_bytes)

# ====================================================================
# 3. หน้าต่างแสดงผลลัพธ์ (Movable Result Window)
# ====================================================================
class ResultWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(350, 200)
        
        # Layout หลัก
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Frame พื้นหลัง (เพื่อให้มีสีและขอบมน)
        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 200);
                border-radius: 10px;
                border: 1px solid white;
            }
            QLabel {
                color: white;
                background: transparent;
                border: none;
            }
            QTextEdit {
                background: transparent;
                color: #00ffcc;
                border: none;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        frame_layout = QVBoxLayout()
        
        # Header (ปุ่มปิด)
        self.close_btn = QPushButton("X")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setStyleSheet("background-color: red; color: white; border-radius: 10px; border: none;")
        self.close_btn.clicked.connect(self.close)
        
        header_layout = QVBoxLayout()
        header_layout.addWidget(self.close_btn, alignment=Qt.AlignmentFlag.AlignRight)

        # ส่วนแสดงข้อความ
        self.original_label = QLabel("กำลังประมวลผล...")
        self.original_label.setWordWrap(True)
        self.original_label.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        
        self.translated_text = QTextEdit()
        self.translated_text.setReadOnly(True)
        
        frame_layout.addLayout(header_layout)
        frame_layout.addWidget(self.original_label)
        frame_layout.addWidget(self.translated_text)
        
        self.frame.setLayout(frame_layout)
        layout.addWidget(self.frame)
        self.setLayout(layout)

        # ตัวแปรสำหรับการลากหน้าต่าง
        self.old_pos = None

    def update_content(self, original, translated):
        self.original_label.setText(original)
        self.translated_text.setText(translated)

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

# ====================================================================
# 4. Main Controller (ตัวคุมหลัก)
# ====================================================================
class MainController(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Torslate Controller")
        self.setGeometry(100, 100, 300, 150)

        # UI สำหรับหน้าต่างหลัก (เอาไว้ดูสถานะ)
        central_widget = QWidget()
        layout = QVBoxLayout()
        label = QLabel("โปรแกรมกำลังทำงาน...\nกด Ctrl + Alt + T เพื่อแปลภาษา")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        # เริ่มต้น Hotkey Listener
        self.hotkey_thread = HotkeyListener()
        self.hotkey_thread.on_trigger.connect(self.start_selection)
        self.hotkey_thread.start()

        self.selection_window = None
        self.result_window = None
        self.worker = None

    def start_selection(self):
        print(">>> กำลังเปิดหน้าต่างลากคลุม (Opening Overlay)... <<<")
        # สร้างหน้าต่าง Overlay ใหม่ทุกครั้งที่กด Hotkey
        self.selection_window = SelectionOverlay()
        self.selection_window.on_selected.connect(self.process_image)
        self.selection_window.show()

        self.selection_window.activateWindow()
        self.selection_window.raise_()

    def process_image(self, image_data):
        # แสดงหน้าต่างผลลัพธ์ (Loading) ที่ตำแหน่งเมาส์ปัจจุบัน
        cursor_pos = QCursor.pos()
        
        if self.result_window:
            self.result_window.close()
            
        self.result_window = ResultWindow()
        self.result_window.move(cursor_pos.x() + 20, cursor_pos.y() + 20)
        self.result_window.show()

        # เริ่ม Worker Thread เพื่อเรียก API
        self.worker = CloudWorker(image_data)
        self.worker.finished.connect(self.show_result)
        self.worker.error.connect(self.show_error)
        self.worker.start()

    def show_result(self, original, translated):
        if self.result_window:
            self.result_window.update_content(original, translated)

    def show_error(self, error_msg):
        if self.result_window:
            self.result_window.update_content("Error", error_msg)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    controller = MainController()
    controller.show() # แสดงหน้าต่างคุมหลัก
    sys.exit(app.exec())