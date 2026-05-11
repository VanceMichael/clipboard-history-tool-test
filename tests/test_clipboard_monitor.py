import pytest
import base64
from unittest.mock import Mock, MagicMock, patch, PropertyMock


class TestImageToBase64:
    def test_null_image_returns_empty_string(self):
        mock_qimage = Mock()
        mock_qimage.isNull.return_value = True
        
        from clipboard_monitor import ClipboardMonitor
        
        result = ClipboardMonitor._image_to_base64(Mock(), mock_qimage)
        assert result == ""

    def test_image_encoding_flow(self):
        with patch('clipboard_monitor.QByteArray') as MockQByteArray, \
             patch('clipboard_monitor.QBuffer') as MockBuffer:
            
            mock_qimage = Mock()
            mock_qimage.isNull.return_value = False
            
            test_png_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'
            
            mock_byte_array = MagicMock()
            MockQByteArray.return_value = mock_byte_array
            
            mock_buffer = MagicMock()
            MockBuffer.return_value = mock_buffer
            
            with patch('clipboard_monitor.bytes', return_value=test_png_bytes):
                from clipboard_monitor import ClipboardMonitor
                
                result = ClipboardMonitor._image_to_base64(Mock(), mock_qimage)
                
                mock_qimage.save.assert_called_once()
                assert mock_qimage.save.call_args[0][1] == "PNG"
                
                expected = base64.b64encode(test_png_bytes).decode('utf-8')
                assert result == expected


class TestTextDeduplication:
    @pytest.mark.parametrize(
        "test_case, last_content, new_content, expect_add",
        [
            ("相同内容不重复添加", "hello", "hello", False),
            ("不同内容添加", "hello", "world", True),
            ("新内容strip后与last相同", "hello", "  hello  ", False),
            ("新内容strip后不同", "hello", "  world  ", True),
            ("换行strip后相同", "hello", "hello\n", False),
            ("制表符strip后相同", "hello", "\thello\t", False),
            ("初始None添加", None, "hello", True),
            ("空字符串变内容", "", "hello", True),
        ],
    )
    def test_text_strip_comparison(self, test_case, last_content, new_content, expect_add):
        mock_db = Mock()
        
        with patch('clipboard_monitor.QGuiApplication') as MockGuiApp, \
             patch('clipboard_monitor.QTimer'):
            
            mock_clipboard = Mock()
            MockGuiApp.clipboard.return_value = mock_clipboard
            
            from clipboard_monitor import ClipboardMonitor
            monitor = ClipboardMonitor(mock_db)
            
            monitor.last_content = last_content
            monitor.last_type = 'text'
            mock_db.reset_mock()
            
            mock_mime = Mock()
            mock_mime.hasImage.return_value = False
            mock_mime.hasText.return_value = True
            mock_mime.text.return_value = new_content
            mock_clipboard.mimeData.return_value = mock_mime
            
            monitor.check_clipboard()
            
            if expect_add:
                mock_db.add_item.assert_called_once(), f"用例失败: {test_case}"
            else:
                mock_db.add_item.assert_not_called(), f"用例失败: {test_case}"

    @pytest.mark.parametrize(
        "test_case, raw_content, expected_stripped",
        [
            ("去除前后空格", "  test content  ", "test content"),
            ("去除前后换行", "\nhello\nworld\n", "hello\nworld"),
            ("去除前后制表符", "\tfoo\tbar\t", "foo\tbar"),
            ("混合空白", "  \n\t  test  \t\n  ", "test"),
        ],
    )
    def test_content_is_stripped_before_save(self, test_case, raw_content, expected_stripped):
        mock_db = Mock()
        
        with patch('clipboard_monitor.QGuiApplication') as MockGuiApp, \
             patch('clipboard_monitor.QTimer'):
            
            mock_clipboard = Mock()
            MockGuiApp.clipboard.return_value = mock_clipboard
            
            from clipboard_monitor import ClipboardMonitor
            monitor = ClipboardMonitor(mock_db)
            
            monitor.last_content = "different"
            
            mock_mime = Mock()
            mock_mime.hasImage.return_value = False
            mock_mime.hasText.return_value = True
            mock_mime.text.return_value = raw_content
            mock_clipboard.mimeData.return_value = mock_mime
            
            monitor.check_clipboard()
            
            mock_db.add_item.assert_called_once()
            actual_content = mock_db.add_item.call_args[0][0]
            assert actual_content == expected_stripped, f"用例失败: {test_case}"


class TestContentTypeHandling:
    def test_image_type_different_from_text(self):
        mock_db = Mock()
        
        with patch('clipboard_monitor.QGuiApplication') as MockGuiApp, \
             patch('clipboard_monitor.QTimer'):
            
            mock_clipboard = Mock()
            MockGuiApp.clipboard.return_value = mock_clipboard
            
            from clipboard_monitor import ClipboardMonitor
            monitor = ClipboardMonitor(mock_db)
            
            monitor.last_content = "same_data"
            monitor.last_type = 'text'
            
            mock_mime = Mock()
            mock_mime.hasImage.return_value = True
            mock_mime.hasText.return_value = False
            mock_clipboard.mimeData.return_value = mock_mime
            
            mock_image = Mock()
            mock_image.isNull.return_value = False
            mock_clipboard.image.return_value = mock_image
            
            with patch.object(monitor, '_image_to_base64', return_value="same_data"):
                monitor.check_clipboard()
                
                mock_db.add_item.assert_called_once()
                assert monitor.last_type == 'image'

    def test_unknown_content_ignored(self):
        mock_db = Mock()
        
        with patch('clipboard_monitor.QGuiApplication') as MockGuiApp, \
             patch('clipboard_monitor.QTimer'):
            
            mock_clipboard = Mock()
            MockGuiApp.clipboard.return_value = mock_clipboard
            
            mock_mime = Mock()
            mock_mime.hasImage.return_value = False
            mock_mime.hasText.return_value = False
            mock_clipboard.mimeData.return_value = mock_mime
            
            from clipboard_monitor import ClipboardMonitor
            monitor = ClipboardMonitor(mock_db)
            
            monitor.check_clipboard()
            
            mock_db.add_item.assert_not_called()

    def test_empty_whitespace_text_ignored(self):
        mock_db = Mock()
        
        with patch('clipboard_monitor.QGuiApplication') as MockGuiApp, \
             patch('clipboard_monitor.QTimer'):
            
            mock_clipboard = Mock()
            MockGuiApp.clipboard.return_value = mock_clipboard
            
            mock_mime = Mock()
            mock_mime.hasImage.return_value = False
            mock_mime.hasText.return_value = True
            mock_mime.text.return_value = "   \n\t   "
            mock_clipboard.mimeData.return_value = mock_mime
            
            from clipboard_monitor import ClipboardMonitor
            monitor = ClipboardMonitor(mock_db)
            
            monitor.check_clipboard()
            
            mock_db.add_item.assert_not_called()


class TestSignalEmission:
    def test_clipboard_changed_signal(self):
        mock_db = Mock()
        
        with patch('clipboard_monitor.QGuiApplication') as MockGuiApp, \
             patch('clipboard_monitor.QTimer'):
            
            mock_clipboard = Mock()
            MockGuiApp.clipboard.return_value = mock_clipboard
            
            from clipboard_monitor import ClipboardMonitor
            monitor = ClipboardMonitor(mock_db)
            
            signal_emitted = []
            def handler(content, content_type):
                signal_emitted.append((content, content_type))
            
            monitor.clipboard_changed.connect(handler)
            
            mock_mime = Mock()
            mock_mime.hasImage.return_value = False
            mock_mime.hasText.return_value = True
            mock_mime.text.return_value = "test signal"
            mock_clipboard.mimeData.return_value = mock_mime
            
            monitor.check_clipboard()
            
            assert len(signal_emitted) == 1
            assert signal_emitted[0] == ("test signal", "text")


class TestSetClipboardContent:
    def test_set_text_content(self):
        mock_db = Mock()
        
        with patch('clipboard_monitor.QGuiApplication') as MockGuiApp, \
             patch('clipboard_monitor.QTimer'):
            
            mock_clipboard = Mock()
            MockGuiApp.clipboard.return_value = mock_clipboard
            
            from clipboard_monitor import ClipboardMonitor
            monitor = ClipboardMonitor(mock_db)
            
            monitor.set_clipboard_content("test text", "text")
            
            mock_clipboard.setText.assert_called_once_with("test text")
            assert monitor.last_content == "test text"
            assert monitor.last_type == "text"

    def test_set_image_content(self):
        mock_db = Mock()
        
        with patch('clipboard_monitor.QGuiApplication') as MockGuiApp, \
             patch('clipboard_monitor.QTimer'):
            
            mock_clipboard = Mock()
            MockGuiApp.clipboard.return_value = mock_clipboard
            
            from clipboard_monitor import ClipboardMonitor
            monitor = ClipboardMonitor(mock_db)
            
            mock_image = Mock()
            mock_image.isNull.return_value = False
            
            with patch('clipboard_monitor.QImage.fromData', return_value=mock_image):
                with patch('clipboard_monitor.QByteArray'):
                    test_base64 = base64.b64encode(b'test_image_data').decode('utf-8')
                    monitor.set_clipboard_content(test_base64, "image")
            
            mock_clipboard.setImage.assert_called_once_with(mock_image)
            assert monitor.last_content == test_base64
            assert monitor.last_type == "image"

    def test_set_invalid_image_ignored(self):
        mock_db = Mock()
        
        with patch('clipboard_monitor.QGuiApplication') as MockGuiApp, \
             patch('clipboard_monitor.QTimer'), \
             patch('clipboard_monitor.QImage') as MockQImage:
            
            mock_clipboard = Mock()
            MockGuiApp.clipboard.return_value = mock_clipboard
            
            mock_image = Mock()
            mock_image.isNull.return_value = True
            MockQImage.fromData.return_value = mock_image
            
            from clipboard_monitor import ClipboardMonitor
            monitor = ClipboardMonitor(mock_db)
            
            original_last_content = monitor.last_content
            original_last_type = monitor.last_type
            
            test_base64 = base64.b64encode(b'invalid_data').decode('utf-8')
            monitor.set_clipboard_content(test_base64, "image")
            
            mock_clipboard.setImage.assert_not_called()
            assert monitor.last_content == original_last_content
            assert monitor.last_type == original_last_type
