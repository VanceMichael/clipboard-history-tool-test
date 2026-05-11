import pytest
from unittest.mock import Mock, patch


class TestFormatDisplayText:
    @pytest.mark.parametrize(
        "test_case, content, content_type, pinned, expected_prefix",
        [
            ("钉住文本有图标前缀", "test", "text", True, "📌 "),
            ("未钉住文本有空格前缀", "test", "text", False, "   "),
            ("钉住图片有图标前缀", "", "image", True, "📌 "),
            ("未钉住图片有空格前缀", "", "image", False, "   "),
        ],
    )
    def test_pin_prefix(self, test_case, content, content_type, pinned, expected_prefix):
        with patch('history_window.QWidget'):
            from history_window import HistoryWindow
            
            result = HistoryWindow._format_display_text(Mock(), content, content_type, pinned)
            assert result.startswith(expected_prefix), f"用例失败: {test_case}"

    @pytest.mark.parametrize(
        "test_case, content, expected_display",
        [
            ("图片类型显示图片标识", "any_base64_data", "[图片]"),
            ("图片忽略内容", "abc123", "[图片]"),
        ],
    )
    def test_image_display(self, test_case, content, expected_display):
        with patch('history_window.QWidget'):
            from history_window import HistoryWindow
            
            result = HistoryWindow._format_display_text(Mock(), content, 'image', False)
            assert expected_display in result, f"用例失败: {test_case}"

    @pytest.mark.parametrize(
        "test_case, content, expected_length, has_ellipsis",
        [
            ("短文本不截断", "hello world", 11, False),
            ("刚好100字符不截断", "a" * 100, 100, False),
            ("超过100字符截断", "a" * 150, 103, True),
        ],
    )
    def test_text_truncation(self, test_case, content, expected_length, has_ellipsis):
        with patch('history_window.QWidget'):
            from history_window import HistoryWindow
            
            result = HistoryWindow._format_display_text(Mock(), content, 'text', False)
            display_text = result[3:]
            
            assert len(display_text) == expected_length, f"用例失败: {test_case} - 长度不符"
            if has_ellipsis:
                assert display_text.endswith("..."), f"用例失败: {test_case} - 应该有省略号"
            else:
                assert not display_text.endswith("..."), f"用例失败: {test_case} - 不应该有省略号"

    @pytest.mark.parametrize(
        "test_case, content, expected_chars",
        [
            ("换行符替换为空格", "hello\nworld", "hello world"),
            ("多个换行符替换", "a\nb\nc", "a b c"),
        ],
    )
    def test_newline_replacement(self, test_case, content, expected_chars):
        with patch('history_window.QWidget'):
            from history_window import HistoryWindow
            
            result = HistoryWindow._format_display_text(Mock(), content, 'text', False)
            display_text = result[3:]
            
            assert display_text == expected_chars, f"用例失败: {test_case}"

    @pytest.mark.parametrize(
        "test_case, content, content_type, pinned, expected",
        [
            ("完整文本显示", "hello", "text", False, "   hello"),
            ("完整钉住文本", "hello", "text", True, "📌 hello"),
            ("完整图片显示", "", "image", False, "   [图片]"),
            ("完整钉住图片", "", "image", True, "📌 [图片]"),
            ("中文长文本截断", "你好" * 60, "text", False, "   " + "你好" * 50 + "..."),
        ],
    )
    def test_complete_format(self, test_case, content, content_type, pinned, expected):
        with patch('history_window.QWidget'):
            from history_window import HistoryWindow
            
            result = HistoryWindow._format_display_text(Mock(), content, content_type, pinned)
            assert result == expected, f"用例失败: {test_case}"
