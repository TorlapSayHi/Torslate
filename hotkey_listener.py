from PyQt6.QtCore import QThread, pyqtSignal
from pynput import keyboard

class HotkeyListener(QThread):
    # Signal เดิม (Ctrl+Alt+T)
    on_trigger = pyqtSignal()
    
    # Signal ใหม่สำหรับ Story Mode
    on_trigger_region_set = pyqtSignal()   # Ctrl+Alt+R (ตั้งค่าขอบ)
    on_trigger_story_translate = pyqtSignal() # Ctrl+Alt+E (เริ่มแปล)

    def run(self):
        print("--- Hotkey Listener Started ---")
        print("1. Ctrl+Alt+T : Auto Capture & Translate")
        print("2. Ctrl+Alt+R : Set Story Region")
        print("3. Ctrl+Alt+E : Translate Story Region")
        
        with keyboard.GlobalHotKeys({
            '<ctrl>+<alt>+t': self.emit_signal,
            '<ctrl>+<alt>+r': self.emit_region_set,
            '<ctrl>+<alt>+e': self.emit_story_translate
        }) as h:
            h.join()

    def emit_signal(self):
        print(">>> Hotkey: Standard Translate (T) <<<")
        self.on_trigger.emit()

    def emit_region_set(self):
        print(">>> Hotkey: Set Region (R) <<<")
        self.on_trigger_region_set.emit()

    def emit_story_translate(self):
        print(">>> Hotkey: Story Translate (E) <<<")
        self.on_trigger_story_translate.emit()