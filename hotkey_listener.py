from PyQt6.QtCore import QThread, pyqtSignal
from pynput import keyboard

class HotkeyListener(QThread):
    # Signal ที่จะส่งไปบอก Main App ว่ามีการกดปุ่มแล้ว
    on_trigger = pyqtSignal()

    def run(self):
        print("--- Hotkey Listener Started: Waiting for Ctrl+Alt+T ---")
        # กำหนด Hotkey ที่นี่ (เช่น <ctrl>+<alt>+t)
        # หมายเหตุ: การใช้ GlobalHotKeys ช่วยให้จัดการได้ง่ายกว่า Listener ธรรมดา
        with keyboard.GlobalHotKeys({
            '<ctrl>+<alt>+t': self.emit_signal
        }) as h:
            h.join()

    def emit_signal(self):
        print(">>> Hotkey Detected! <<<")
        # ส่งสัญญาณไปที่ GUI Thread
        self.on_trigger.emit()