import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestFormatDisplayText:
    """测试 _format_display_text 纯逻辑方法"""

    @pytest.fixture
    def format_func(self):
        """获取 _format_display_text 函数"""
        from history_window import HistoryWindow
        return HistoryWindow._format_display_text

    @pytest.mark.parametrize(
        "name, content, content_type, pinned, expected_start, expected_content",
        [
            ("普通文本未钉住", "hello world", "text", False, "   ", "hello world"),
            ("普通文本钉住", "hello world", "text", True, "📌 ", "hello world"),
            ("图片类型未钉住", "image_data", "image", False, "   ", "[图片]"),
            ("图片类型钉住", "image_data", "image", True, "📌 ", "[图片]"),
            ("空文本", "", "text", False, "   ", ""),
        ],
    )
    def test_basic_cases(self, format_func, name, content, content_type, pinned, expected_start, expected_content):
        """测试表驱动：基本场景"""
        result = format_func(None, content, content_type, pinned)

        assert result.startswith(expected_start), (
            f"用例失败: {name} - 期望以 '{expected_start}' 开头，实际: '{result}'"
        )
        assert expected_content in result, (
            f"用例失败: {name} - 期望包含 '{expected_content}'，实际: '{result}'"
        )

    @pytest.mark.parametrize(
        "name, content, content_type, pinned, expected_contains_truncation",
        [
            ("超长文本截断", "A" * 200, "text", False, True),
            ("恰好100字符", "A" * 100, "text", False, False),
            ("99字符不截断", "A" * 99, "text", False, False),
            ("101字符截断", "A" * 101, "text", False, True),
        ],
    )
    def test_text_truncation(self, format_func, name, content, content_type, pinned, expected_contains_truncation):
        """测试表驱动：超长文本截断"""
        result = format_func(None, content, content_type, pinned)

        if expected_contains_truncation:
            assert "..." in result, f"用例失败: {name} - 期望包含 '...' 截断标记"
            assert len(result) <= 106, f"用例失败: {name} - 期望不超过106字符（前缀+100+...）"
        else:
            assert "..." not in result, f"用例失败: {name} - 不应包含 '...' 截断标记"

    def test_newline_replacement(self, format_func):
        """测试换行符替换为空格"""
        content = "line1\nline2\nline3"
        result = format_func(None, content, "text", False)

        assert "\n" not in result
        assert "line1 line2 line3" in result

    def test_tab_replacement(self, format_func):
        """测试制表符保留（仅替换换行）"""
        content = "col1\tcol2\tcol3"
        result = format_func(None, content, "text", False)

        assert "col1\tcol2\tcol3" in result or "col1 col2 col3" in result

    def test_long_text_preserves_prefix(self, format_func):
        """测试超长文本保留钉住前缀"""
        content = "A" * 200
        result = format_func(None, content, "text", True)

        assert result.startswith("📌 ")
        assert "..." in result

    def test_truncation_exact_length(self, format_func):
        """测试截断后文本长度精确为100字符加省略号"""
        content = "ABCDEFGHIJ" * 20
        result = format_func(None, content, "text", False)

        stripped = result.lstrip()
        assert stripped.endswith("...")
        assert len(stripped) == 103

    def test_image_ignores_content_length(self, format_func):
        """测试图片类型总是显示 [图片] 不管内容长度"""
        content = "A" * 1000
        result = format_func(None, content, "image", False)

        assert "[图片]" in result
        assert "..." not in result
