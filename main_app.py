import sys
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox, QStyle
)
from PyQt6.QtCore import QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QAction

from database import ClipboardDatabase
from clipboard_monitor import ClipboardMonitor
from history_window import HistoryWindow


class GlobalHotkeyManager(QObject):
    hotkey_pressed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._initialized = False
        self._listener = None
        self._try_init()

    def _try_init(self):
        try:
            from pynput import keyboard
            self._listener = keyboard.GlobalHotKeys({
                '<ctrl>+<shift>+v': self._on_hotkey,
                '<cmd>+<shift>+v': self._on_hotkey,
            })
            self._listener.start()
            self._initialized = True
            print("全局快捷键已初始化 (Ctrl/Cmd+Shift+V)")
        except ImportError:
            print("警告: 未安装 pynput 库，全局快捷键功能不可用")
            print("请运行: pip install pynput")
        except Exception as e:
            print(f"初始化全局快捷键失败: {e}")

    def _on_hotkey(self):
        self.hotkey_pressed.emit()

    def stop(self):
        if self._listener:
            self._listener.stop()


class ClipboardHistoryApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        self.db = ClipboardDatabase()
        self.clipboard_monitor = ClipboardMonitor(self.db)
        self.history_window = HistoryWindow(self.db)
        self.hotkey_manager = GlobalHotkeyManager()
        
        self._setup_tray()
        self._setup_connections()

    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon()
        
        icon = self.app.style().standardIcon(
            QStyle.StandardPixmap.SP_FileDialogContentsView
        )
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("剪贴板历史工具")
        
        menu = QMenu()
        
        show_action = QAction("显示历史 (Ctrl/Cmd+Shift+V)", self.app)
        show_action.triggered.connect(self.show_history)
        menu.addAction(show_action)
        
        menu.addSeparator()
        
        clear_action = QAction("清空历史(保留钉住)", self.app)
        clear_action.triggered.connect(self.clear_history_keep_pinned)
        menu.addAction(clear_action)
        
        clear_all_action = QAction("清空所有历史", self.app)
        clear_all_action.triggered.connect(self.clear_all_history)
        menu.addAction(clear_all_action)
        
        menu.addSeparator()
        
        quit_action = QAction("退出", self.app)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _setup_connections(self):
        self.clipboard_monitor.clipboard_changed.connect(self._on_clipboard_changed)
        self.history_window.item_selected.connect(self._on_item_selected)
        
        if self.hotkey_manager._initialized:
            self.hotkey_manager.hotkey_pressed.connect(self.show_history)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_history()

    def _on_clipboard_changed(self, content, content_type):
        if self.history_window.isVisible():
            self.history_window.load_history(self.history_window.search_input.text())

    def _on_item_selected(self, content, content_type):
        self.history_window.hide()
        
        QTimer.singleShot(50, lambda: self._set_and_paste(content, content_type))

    def _set_and_paste(self, content, content_type):
        self.clipboard_monitor.set_clipboard_content(content, content_type)
        
        QTimer.singleShot(100, self._simulate_paste)

    def _simulate_paste(self):
        try:
            from pynput.keyboard import Controller, Key
            import time
            
            keyboard = Controller()
            time.sleep(0.1)
            
            if sys.platform == 'darwin':
                with keyboard.pressed(Key.cmd):
                    keyboard.press('v')
                    keyboard.release('v')
            else:
                with keyboard.pressed(Key.ctrl):
                    keyboard.press('v')
                    keyboard.release('v')
        except Exception as e:
            print(f"模拟粘贴失败: {e}")

    def show_history(self):
        if self.history_window.isVisible():
            self.history_window.hide()
        else:
            self.history_window.show_at_cursor()

    def clear_history_keep_pinned(self):
        reply = QMessageBox.question(
            None, 
            '确认清空', 
            '确定要清空所有未钉住的历史记录吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.db.clear_history(keep_pinned=True)
            if self.history_window.isVisible():
                self.history_window.load_history()

    def clear_all_history(self):
        reply = QMessageBox.question(
            None, 
            '确认清空', 
            '确定要清空所有历史记录（包括钉住的）吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.db.clear_history(keep_pinned=False)
            if self.history_window.isVisible():
                self.history_window.load_history()

    def quit_app(self):
        self.hotkey_manager.stop()
        self.tray_icon.hide()
        self.app.quit()

    def run(self):
        self.tray_icon.showMessage(
            "剪贴板历史工具",
            "已启动，按 Ctrl/Cmd+Shift+V 显示历史记录",
            QSystemTrayIcon.MessageIcon.Information,
            3000
        )
        
        sys.exit(self.app.exec())
