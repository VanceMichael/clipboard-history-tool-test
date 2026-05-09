import pytest
import base64
from unittest.mock import MagicMock, patch, call
from clipboard_monitor import ClipboardMonitor


@pytest.fixture
def mock_db():
    return MagicMock()


def _make_monitor(mock_db):
    with patch('clipboard_monitor.QGuiApplication'), \
         patch('clipboard_monitor.QTimer'):
        instance = ClipboardMonitor.__new__(ClipboardMonitor)
        QObject_init = MagicMock()
        with patch.object(ClipboardMonitor.__bases__[0], '__init__', QObject_init):
            ClipboardMonitor.__init__(instance, mock_db)
        instance.clipboard = MagicMock()
        instance.db = mock_db
        instance.last_content = None
        instance.last_type = None
        instance.timer = MagicMock()
        instance.clipboard_changed = MagicMock()
        return instance


@pytest.fixture
def monitor(mock_db):
    return _make_monitor(mock_db)


class TestCheckClipboardTextDedup:
    @pytest.mark.parametrize(
        "label,raw_text,stripped_text,last_content,last_type,expect_add_call",
        [
            ("new_text", "  hello  ", "hello", None, None, True),
            ("same_after_strip", "  hello  ", "hello", "hello", "text", False),
            ("different_after_strip", "  hello  ", "hello", "world", "text", True),
            ("only_whitespace", "   ", "", None, None, False),
            ("empty_string", "", "", None, None, False),
            ("same_content_diff_type", "hello", "hello", "hello", "image", True),
        ],
    )
    def test_text_strip_and_dedup(
        self, monitor, mock_db, label, raw_text, stripped_text, last_content, last_type, expect_add_call
    ):
        mock_db.reset_mock()
        mime_data = MagicMock()
        mime_data.hasImage.return_value = False
        mime_data.hasText.return_value = True
        mime_data.text.return_value = raw_text
        monitor.clipboard.mimeData.return_value = mime_data
        monitor.last_content = last_content
        monitor.last_type = last_type

        monitor.check_clipboard()

        if expect_add_call:
            mock_db.add_item.assert_called_once_with(stripped_text, 'text'), (
                f"[{label}] add_item 应以 strip 后内容调用，期望 ({stripped_text!r}, 'text')，"
                f"实际 {mock_db.add_item.call_args}"
            )
            assert monitor.last_content == stripped_text, f"[{label}] last_content 应更新"
            assert monitor.last_type == 'text', f"[{label}] last_type 应为 'text'"
        else:
            mock_db.add_item.assert_not_called(), (
                f"[{label}] 内容未变化或为空，不应调用 add_item"
            )


class TestCheckClipboardImage:
    def test_image_calls_add_item(self, monitor, mock_db):
        mock_db.reset_mock()
        mime_data = MagicMock()
        mime_data.hasImage.return_value = True
        monitor.clipboard.mimeData.return_value = mime_data
        monitor.clipboard.image.return_value = MagicMock()

        with patch.object(monitor, '_image_to_base64', return_value='base64data'):
            monitor.check_clipboard()

        mock_db.add_item.assert_called_once_with('base64data', 'image')

    def test_image_dedup_same_content_same_type(self, monitor, mock_db):
        mock_db.reset_mock()
        mime_data = MagicMock()
        mime_data.hasImage.return_value = True
        monitor.clipboard.mimeData.return_value = mime_data
        monitor.clipboard.image.return_value = MagicMock()
        monitor.last_content = 'base64data'
        monitor.last_type = 'image'

        with patch.object(monitor, '_image_to_base64', return_value='base64data'):
            monitor.check_clipboard()

        mock_db.add_item.assert_not_called(), "相同图片不应重复添加"

    def test_neither_image_nor_text_returns_early(self, monitor, mock_db):
        mock_db.reset_mock()
        mime_data = MagicMock()
        mime_data.hasImage.return_value = False
        mime_data.hasText.return_value = False
        monitor.clipboard.mimeData.return_value = mime_data

        monitor.check_clipboard()

        mock_db.add_item.assert_not_called()


class TestImageToBase64:
    def test_valid_image_encode(self, monitor):
        real_png_bytes = b'\x89PNG\r\n\x1a\n'
        expected_b64 = base64.b64encode(real_png_bytes).decode('utf-8')

        byte_arr_instance = MagicMock()
        buf_instance = MagicMock()

        with patch('clipboard_monitor.QByteArray', return_value=byte_arr_instance), \
             patch('clipboard_monitor.QBuffer', return_value=buf_instance), \
             patch('clipboard_monitor.bytes', return_value=real_png_bytes):
            qimage = MagicMock()
            qimage.isNull.return_value = False

            result = monitor._image_to_base64(qimage)

            assert result == expected_b64, f"base64 编码结果不匹配: got {result!r}, want {expected_b64!r}"
            qimage.save.assert_called_once_with(buf_instance, "PNG")

    def test_null_image_returns_empty(self, monitor):
        qimage = MagicMock()
        qimage.isNull.return_value = True

        result = monitor._image_to_base64(qimage)

        assert result == '', "null 图片应返回空字符串"

    def test_valid_image_calls_save_and_close_buffer(self, monitor):
        byte_arr_instance = MagicMock()
        buf_instance = MagicMock()

        with patch('clipboard_monitor.QByteArray', return_value=byte_arr_instance), \
             patch('clipboard_monitor.QBuffer', return_value=buf_instance), \
             patch('clipboard_monitor.bytes', return_value=b'raw'), \
             patch('clipboard_monitor.base64.b64encode', return_value=b'ZW52'):
            qimage = MagicMock()
            qimage.isNull.return_value = False

            monitor._image_to_base64(qimage)

            buf_instance.open.assert_called_once()
            buf_instance.close.assert_called_once()


class TestSetClipboardContent:
    def test_set_text_content(self, monitor):
        monitor.clipboard.reset_mock()
        monitor.set_clipboard_content("hello", "text")

        monitor.clipboard.setText.assert_called_once_with("hello")
        assert monitor.last_content == "hello"
        assert monitor.last_type == "text"

    def test_set_image_valid(self, monitor):
        monitor.clipboard.reset_mock()

        test_b64 = base64.b64encode(b'\x89PNG_fake').decode('utf-8')

        mock_byte_arr = MagicMock()
        mock_image = MagicMock()
        mock_image.isNull.return_value = False

        with patch('PyQt6.QtCore.QByteArray', return_value=mock_byte_arr), \
             patch('PyQt6.QtGui.QImage') as MockQImage:
            MockQImage.fromData.return_value = mock_image

            monitor.set_clipboard_content(test_b64, "image")

        monitor.clipboard.setImage.assert_called_once_with(mock_image), (
            "有效图片应调用 setImage"
        )
        assert monitor.last_content == test_b64
        assert monitor.last_type == 'image'

    def test_set_image_null_image(self, monitor):
        monitor.clipboard.reset_mock()

        test_b64 = base64.b64encode(b'\x89PNG_fake').decode('utf-8')

        mock_byte_arr = MagicMock()
        mock_image = MagicMock()
        mock_image.isNull.return_value = True

        with patch('PyQt6.QtCore.QByteArray', return_value=mock_byte_arr), \
             patch('PyQt6.QtGui.QImage') as MockQImage:
            MockQImage.fromData.return_value = mock_image

            monitor.set_clipboard_content(test_b64, "image")

        monitor.clipboard.setImage.assert_not_called(), "null 图片不应调用 setImage"

    def test_set_image_invalid_base64_exception(self, monitor):
        monitor.clipboard.reset_mock()
        monitor.set_clipboard_content("!!!not-base64!!!", "image")
        monitor.clipboard.setImage.assert_not_called(), "异常 base64 不应调用 setImage"
