from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, 
    QLineEdit, QMenu, QMessageBox, QLabel, QHBoxLayout
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QEvent
from PyQt6.QtGui import QAction, QCursor, QGuiApplication, QKeyEvent


class HistoryListWidget(QListWidget):
    item_activated = pyqtSignal(QListWidgetItem)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            current_item = self.currentItem()
            if current_item:
                self.item_activated.emit(current_item)
            return
        
        super().keyPressEvent(event)


class SearchLineEdit(QLineEdit):
    move_focus_to_list = pyqtSignal(bool)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Down:
            self.move_focus_to_list.emit(True)
            return
        elif event.key() == Qt.Key.Key_Up:
            self.move_focus_to_list.emit(False)
            return
        elif event.key() == Qt.Key.Key_Escape:
            self.window().hide()
            return
        
        super().keyPressEvent(event)


class HistoryWindow(QWidget):
    item_selected = pyqtSignal(str, str)
    pin_toggled = pyqtSignal(int)
    item_deleted = pyqtSignal(int)

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.setWindowFlags(
            Qt.WindowType.Tool | 
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFixedSize(400, 500)
        
        self._init_ui()
        self.load_history()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        header_layout = QHBoxLayout()
        title_label = QLabel("剪贴板历史")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        hotkey_label = QLabel("Ctrl/Cmd+Shift+V")
        hotkey_label.setStyleSheet("color: #888; font-size: 10px;")
        header_layout.addWidget(hotkey_label)
        
        layout.addLayout(header_layout)
        
        self.search_input = SearchLineEdit()
        self.search_input.setPlaceholderText("搜索...")
        self.search_input.textChanged.connect(self.filter_history)
        self.search_input.move_focus_to_list.connect(self._on_move_focus_to_list)
        layout.addWidget(self.search_input)
        
        self.list_widget = HistoryListWidget()
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.list_widget.item_activated.connect(self._on_list_item_activated)
        layout.addWidget(self.list_widget)
        
        self.setTabOrder(self.search_input, self.list_widget)

    def _on_move_focus_to_list(self, down: bool):
        if self.list_widget.count() > 0:
            self.list_widget.setFocus()
            if down:
                self.list_widget.setCurrentRow(0)
            else:
                self.list_widget.setCurrentRow(self.list_widget.count() - 1)

    def _on_list_item_activated(self, item: QListWidgetItem):
        self._select_item(item)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)

    def load_history(self, search_query: str = ''):
        self.list_widget.clear()
        items = self.db.get_all_items(search_query)
        
        for item in items:
            item_id, content, content_type, pinned, created_at = item
            display_text = self._format_display_text(content, content_type, pinned)
            
            list_item = QListWidgetItem(display_text)
            list_item.setData(Qt.ItemDataRole.UserRole, (item_id, content, content_type))
            
            if pinned:
                list_item.setBackground(Qt.GlobalColor.lightGray)
            
            self.list_widget.addItem(list_item)

    def _format_display_text(self, content: str, content_type: str, pinned: bool) -> str:
        prefix = "📌 " if pinned else "   "
        
        if content_type == 'image':
            return f"{prefix}[图片]"
        
        max_length = 100
        if len(content) > max_length:
            content = content[:max_length] + "..."
        
        content = content.replace('\n', ' ')
        return f"{prefix}{content}"

    def filter_history(self, query: str):
        self.load_history(query)

    def show_context_menu(self, pos: QPoint):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        
        item_id, content, content_type = item.data(Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        
        copy_action = QAction("复制", self)
        copy_action.triggered.connect(lambda: self._copy_item(item))
        menu.addAction(copy_action)
        
        pin_action = QAction("取消钉住" if "📌" in item.text() else "钉住", self)
        pin_action.triggered.connect(lambda: self._toggle_pin(item_id))
        menu.addAction(pin_action)
        
        delete_action = QAction("删除", self)
        delete_action.triggered.connect(lambda: self._delete_item(item_id))
        menu.addAction(delete_action)
        
        menu.exec(self.list_widget.mapToGlobal(pos))

    def on_item_double_clicked(self, item: QListWidgetItem):
        self._select_item(item)

    def _select_item(self, item: QListWidgetItem):
        item_id, content, content_type = item.data(Qt.ItemDataRole.UserRole)
        self.item_selected.emit(content, content_type)

    def _copy_item(self, item: QListWidgetItem):
        item_id, content, content_type = item.data(Qt.ItemDataRole.UserRole)
        self.item_selected.emit(content, content_type)

    def _toggle_pin(self, item_id: int):
        self.db.toggle_pin(item_id)
        self.pin_toggled.emit(item_id)
        self.load_history(self.search_input.text())

    def _delete_item(self, item_id: int):
        reply = QMessageBox.question(
            self, 
            '确认删除', 
            '确定要删除这条记录吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_item(item_id)
            self.item_deleted.emit(item_id)
            self.load_history(self.search_input.text())

    def show_at_cursor(self):
        cursor_pos = QCursor.pos()
        screen_geometry = QGuiApplication.primaryScreen().availableGeometry()
        
        x = cursor_pos.x() - self.width() // 2
        y = cursor_pos.y() - self.height() // 2
        
        x = max(screen_geometry.left(), min(x, screen_geometry.right() - self.width()))
        y = max(screen_geometry.top(), min(y, screen_geometry.bottom() - self.height()))
        
        self.move(x, y)
        self.search_input.clear()
        self.load_history()
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_input.setFocus()
