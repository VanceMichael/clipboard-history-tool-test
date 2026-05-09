import os
import sys
import base64
import pytest
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _FakeQByteArray:
    """模拟 QByteArray"""

    def __init__(self, data=b""):
        self._data = data

    def __bytes__(self):
        return self._data


class _FakeQBuffer:
    """模拟 QBuffer"""

    def __init__(self, byte_array):
        self._byte_array = byte_array

    def open(self, mode):
        pass

    def close(self):
        pass

    def write(self, data):
        self._byte_array._data += data


class _FakeMimeData:
    """模拟 MimeData"""

    def __init__(self, text=None, has_image=False):
        self._text = text
        self._has_image = has_image

    def hasText(self):
        return self._text is not None

    def hasImage(self):
        return self._has_image

    def text(self):
        return self._text


class _FakeClipboard:
    """模拟剪贴板"""

    def __init__(self):
        self._mime_data = _FakeMimeData()
        self._image = None

    def mimeData(self):
        return self._mime_data

    def setText(self, text):
        self._mime_data = _FakeMimeData(text=text)

    def setImage(self, image):
        self._mime_data = _FakeMimeData(has_image=True)
        self._image = image

    def image(self):
        return self._image


def _create_monitor_with_mocks(mocker):
    """创建带有 mock 的 ClipboardMonitor 实例"""
    mocker.patch("clipboard_monitor.QObject")
    mocker.patch("clipboard_monitor.QTimer")
    mock_qapp = mocker.patch("clipboard_monitor.QGuiApplication")

    fake_clipboard = _FakeClipboard()
    mock_qapp.clipboard.return_value = fake_clipboard

    mock_db = Mock()

    from clipboard_monitor import ClipboardMonitor

    monitor = ClipboardMonitor.__new__(ClipboardMonitor)
    monitor.db = mock_db
    monitor.clipboard = fake_clipboard
    monitor.last_content = None
    monitor.last_type = None
    monitor.clipboard_changed = Mock()

    return monitor, fake_clipboard, mock_db


class TestImageToBase64:
    """测试图片转 base64 功能"""

    @pytest.mark.parametrize(
        "name, image_data, is_null, expected_result",
        [
            ("简单图片数据", b"test image content", False, "dGVzdCBpbWFnZSBjb250ZW50"),
            ("空图片数据", b"", False, ""),
            ("二进制PNG头", bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]), False, "iVBORw0KGgo="),
            ("null图片", b"", True, ""),
        ],
    )
    def test_image_to_base64_various(self, mocker, name, image_data, is_null, expected_result):
        """测试表驱动：各种图片数据转 base64"""
        mock_qimage = Mock()
        mock_qimage.isNull.return_value = is_null

        def fake_save(buffer, fmt):
            buffer.write(image_data)

        mock_qimage.save = fake_save

        mocker.patch("clipboard_monitor.QByteArray", side_effect=_FakeQByteArray)
        mocker.patch("clipboard_monitor.QBuffer", side_effect=_FakeQBuffer)

        from clipboard_monitor import ClipboardMonitor

        monitor = Mock(spec=ClipboardMonitor)
        from clipboard_monitor import ClipboardMonitor as CM
        result = CM._image_to_base64(monitor, mock_qimage)

        assert result == expected_result, (
            f"用例失败: {name} - 期望 '{expected_result}'，实际 '{result}'"
        )


class TestTextStripAndDeduplication:
    """测试文本去除前后空白和去重逻辑"""

    @pytest.mark.parametrize(
        "name, raw_text, expected_stripped, expect_add_item",
        [
            ("前后有空格", "  hello world  ", "hello world", True),
            ("仅开头空格", "   leading spaces", "leading spaces", True),
            ("仅结尾空格", "trailing spaces   ", "trailing spaces", True),
            ("换行和制表", "\n\t text with newlines \n\t", "text with newlines", True),
            ("中间空格保留", "  middle   spaces  ", "middle   spaces", True),
            ("空字符串", "", "", False),
            ("仅空白", "   \n\t   ", "", False),
            ("无空白", "no_whitespace", "no_whitespace", True),
            ("中文空白", "  中文  内容  ", "中文  内容", True),
        ],
    )
    def test_text_stripping(self, mocker, name, raw_text, expected_stripped, expect_add_item):
        """测试表驱动：文本去除前后空白"""
        monitor, fake_clipboard, mock_db = _create_monitor_with_mocks(mocker)

        fake_clipboard._mime_data = _FakeMimeData(text=raw_text)

        from clipboard_monitor import ClipboardMonitor
        ClipboardMonitor.check_clipboard(monitor)

        if expect_add_item:
            assert monitor.last_content == expected_stripped, (
                f"用例失败: {name} - 期望 '{expected_stripped}'，实际 '{monitor.last_content}'"
            )
            assert monitor.last_type == "text"
            mock_db.add_item.assert_called_once_with(expected_stripped, "text")
        else:
            mock_db.add_item.assert_not_called()

    @pytest.mark.parametrize(
        "name, first_text, second_text, expect_add_count",
        [
            ("完全相同", "hello", "hello", 1),
            ("去除空白后相同", "  hello  ", "hello", 1),
            ("去除空白后不同", "hello", "world", 2),
            ("空字符串重复", "", "", 0),
        ],
    )
    def test_deduplication_after_stripping(
        self, mocker, name, first_text, second_text, expect_add_count
    ):
        """测试表驱动：去除空白后的去重逻辑"""
        monitor, fake_clipboard, mock_db = _create_monitor_with_mocks(mocker)

        fake_clipboard._mime_data = _FakeMimeData(text=first_text)
        from clipboard_monitor import ClipboardMonitor
        ClipboardMonitor.check_clipboard(monitor)

        fake_clipboard._mime_data = _FakeMimeData(text=second_text)
        ClipboardMonitor.check_clipboard(monitor)

        total_calls = mock_db.add_item.call_count

        assert total_calls == expect_add_count, (
            f"用例失败: {name} - 期望调用 {expect_add_count} 次 add_item，实际调用 {total_calls} 次"
        )


class TestClipboardTypeHandling:
    """测试不同类型的剪贴板内容处理"""

    def test_no_content_does_nothing(self, mocker):
        """测试无内容时不做任何操作"""
        monitor, fake_clipboard, mock_db = _create_monitor_with_mocks(mocker)

        fake_clipboard._mime_data = _FakeMimeData()
        from clipboard_monitor import ClipboardMonitor
        ClipboardMonitor.check_clipboard(monitor)

        mock_db.add_item.assert_not_called()
        assert monitor.last_content is None
        assert monitor.last_type is None

    def test_image_content(self, mocker):
        """测试图片内容处理"""
        monitor, fake_clipboard, mock_db = _create_monitor_with_mocks(mocker)

        mock_image = Mock()
        mock_image.isNull.return_value = False
        fake_clipboard._mime_data = _FakeMimeData(has_image=True)
        fake_clipboard._image = mock_image

        expected_base64 = "fake_base64_data"
        mocker.patch.object(
            type(monitor),
            "_image_to_base64",
            return_value=expected_base64,
        )

        from clipboard_monitor import ClipboardMonitor
        ClipboardMonitor.check_clipboard(monitor)

        assert monitor.last_content == expected_base64
        assert monitor.last_type == "image"
        mock_db.add_item.assert_called_once_with(expected_base64, "image")

    def test_type_change_triggers_new_entry(self, mocker):
        """测试类型变化时即使内容相同也触发新条目"""
        monitor, fake_clipboard, mock_db = _create_monitor_with_mocks(mocker)

        fake_clipboard._mime_data = _FakeMimeData(text="same_data")
        from clipboard_monitor import ClipboardMonitor
        ClipboardMonitor.check_clipboard(monitor)
        assert mock_db.add_item.call_count == 1

        mock_image = Mock()
        mock_image.isNull.return_value = False
        fake_clipboard._mime_data = _FakeMimeData(has_image=True)
        fake_clipboard._image = mock_image

        mocker.patch.object(
            type(monitor),
            "_image_to_base64",
            return_value="same_data",
        )

        ClipboardMonitor.check_clipboard(monitor)

        assert mock_db.add_item.call_count == 2


class TestSetClipboardContent:
    """测试设置剪贴板内容"""

    def test_set_text_content(self, mocker):
        """测试设置文本内容"""
        monitor, fake_clipboard = _create_monitor_with_mocks(mocker)[:2]

        from clipboard_monitor import ClipboardMonitor
        ClipboardMonitor.set_clipboard_content(monitor, "test text", "text")

        assert monitor.last_content == "test text"
        assert monitor.last_type == "text"

    def test_set_image_content(self, mocker):
        """测试设置图片内容"""
        monitor, fake_clipboard = _create_monitor_with_mocks(mocker)[:2]

        mock_qbytearray = mocker.patch("PyQt6.QtCore.QByteArray")
        mock_qimage = mocker.patch("PyQt6.QtGui.QImage")

        mock_image_instance = Mock()
        mock_image_instance.isNull.return_value = False
        mock_qimage.fromData.return_value = mock_image_instance

        image_base64 = base64.b64encode(b"fake_image").decode("utf-8")

        from clipboard_monitor import ClipboardMonitor
        ClipboardMonitor.set_clipboard_content(monitor, image_base64, "image")

        assert monitor.last_content == image_base64
        assert monitor.last_type == "image"

    def test_set_image_invalid_base64(self, mocker):
        """测试设置无效的图片 base64"""
        monitor, fake_clipboard = _create_monitor_with_mocks(mocker)[:2]

        from clipboard_monitor import ClipboardMonitor
        ClipboardMonitor.set_clipboard_content(monitor, "not_valid_base64!!!", "image")

        assert monitor.last_content is None
        assert monitor.last_type is None

    def test_set_image_null_image(self, mocker):
        """测试设置 null 图片"""
        monitor, fake_clipboard = _create_monitor_with_mocks(mocker)[:2]

        mock_qbytearray = mocker.patch("PyQt6.QtCore.QByteArray")
        mock_qimage = mocker.patch("PyQt6.QtGui.QImage")

        mock_image_instance = Mock()
        mock_image_instance.isNull.return_value = True
        mock_qimage.fromData.return_value = mock_image_instance

        image_base64 = base64.b64encode(b"fake_image").decode("utf-8")

        from clipboard_monitor import ClipboardMonitor
        ClipboardMonitor.set_clipboard_content(monitor, image_base64, "image")

        assert monitor.last_content is None
        assert monitor.last_type is None
