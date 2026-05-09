import pytest


def _format_display_text(content: str, content_type: str, pinned: bool) -> str:
    prefix = "\U0001f4cc " if pinned else "   "

    if content_type == 'image':
        return f"{prefix}[图片]"

    max_length = 100
    if len(content) > max_length:
        content = content[:max_length] + "..."

    content = content.replace('\n', ' ')
    return f"{prefix}{content}"


class TestFormatDisplayText:
    @pytest.mark.parametrize(
        "label,content,content_type,pinned,expected",
        [
            (
                "short_text_unpinned",
                "hello",
                "text",
                False,
                "   hello",
            ),
            (
                "short_text_pinned",
                "hello",
                "text",
                True,
                "\U0001f4cc hello",
            ),
            (
                "image_type_unpinned",
                "base64data",
                "image",
                False,
                "   [图片]",
            ),
            (
                "image_type_pinned",
                "base64data",
                "image",
                True,
                "\U0001f4cc [图片]",
            ),
            (
                "newline_replaced",
                "line1\nline2",
                "text",
                False,
                "   line1 line2",
            ),
            (
                "exact_100_chars",
                "a" * 100,
                "text",
                False,
                "   " + "a" * 100,
            ),
            (
                "101_chars_truncated",
                "a" * 101,
                "text",
                False,
                "   " + "a" * 100 + "...",
            ),
            (
                "200_chars_truncated",
                "b" * 200,
                "text",
                False,
                "   " + "b" * 100 + "...",
            ),
            (
                "mixed_newlines_and_long",
                "x\ny\n" + "z" * 150,
                "text",
                False,
                "   x y " + "z" * 96 + "...",
            ),
            (
                "empty_text",
                "",
                "text",
                False,
                "   ",
            ),
            (
                "chinese_text",
                "你好世界",
                "text",
                False,
                "   你好世界",
            ),
        ],
    )
    def test_format_display_text_table_driven(self, label, content, content_type, pinned, expected):
        result = _format_display_text(content, content_type, pinned)
        assert result == expected, (
            f"[{label}] 期望 {expected!r}，实际 {result!r}"
        )

    def test_truncation_preserves_prefix(self):
        content = "x" * 200
        result = _format_display_text(content, "text", True)
        assert result.startswith("\U0001f4cc "), "截断后应保留钉住前缀"

    def test_image_ignores_content_length(self):
        long_b64 = "x" * 500
        result = _format_display_text(long_b64, "image", False)
        assert result == "   [图片]", "image 类型不应截断 content，直接显示 [图片]"

    def test_multiple_newlines_collapsed(self):
        result = _format_display_text("a\n\n\nb", "text", False)
        assert result == "   a   b", "多个换行符应各自替换为空格"

    def test_truncation_happens_before_newline_replace(self):
        content = "x\ny\n" + "z" * 150
        result = _format_display_text(content, "text", False)
        assert "..." in result, "超长文本应有截断标记"
        assert "\n" not in result, "截断后换行应全部被替换为空格"
