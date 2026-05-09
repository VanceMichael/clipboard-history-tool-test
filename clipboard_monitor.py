from PyQt6.QtCore import QObject, QTimer, pyqtSignal, QByteArray, QBuffer
from PyQt6.QtGui import QClipboard, QGuiApplication, QImage, QPixmap
import base64


class ClipboardMonitor(QObject):
    clipboard_changed = pyqtSignal(str, str)

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.clipboard = QGuiApplication.clipboard()
        self.last_content = None
        self.last_type = None
        
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.check_clipboard)
        self.timer.start()

    def check_clipboard(self):
        mime_data = self.clipboard.mimeData()
        
        if mime_data.hasImage():
            image = self.clipboard.image()
            content = self._image_to_base64(image)
            content_type = 'image'
        elif mime_data.hasText():
            content = mime_data.text().strip()
            content_type = 'text'
        else:
            return
        
        if content and (content != self.last_content or content_type != self.last_type):
            self.last_content = content
            self.last_type = content_type
            
            self.db.add_item(content, content_type)
            self.clipboard_changed.emit(content, content_type)

    def _image_to_base64(self, qimage: QImage) -> str:
        if qimage.isNull():
            return ''
        
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        qimage.save(buffer, "PNG")
        buffer.close()
        
        return base64.b64encode(bytes(byte_array)).decode('utf-8')

    def set_clipboard_content(self, content: str, content_type: str):
        if content_type == 'image':
            try:
                image_data = base64.b64decode(content)
                from PyQt6.QtCore import QByteArray
                from PyQt6.QtGui import QImage
                
                byte_array = QByteArray(image_data)
                image = QImage.fromData(byte_array, "PNG")
                if not image.isNull():
                    self.clipboard.setImage(image)
                    self.last_content = content
                    self.last_type = 'image'
            except Exception:
                pass
        else:
            self.clipboard.setText(content)
            self.last_content = content
            self.last_type = 'text'
