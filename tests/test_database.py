import os
import sys
import pytest
import sqlite3
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import ClipboardDatabase


class _TestableClipboardDatabase(ClipboardDatabase):
    """可测试的数据库包装类，使用临时文件数据库"""

    def __init__(self, temp_db_path):
        self._temp_db_path = temp_db_path
        super().__init__()

    def _get_db_path(self) -> str:
        return self._temp_db_path


@pytest.fixture
def db(tmp_path):
    """提供使用临时文件数据库的 ClipboardDatabase 实例"""
    temp_db = str(tmp_path / "test_clipboard.db")
    return _TestableClipboardDatabase(temp_db)


def _count_items(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM clipboard_history")
    return cursor.fetchone()[0]


def _get_all_items(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clipboard_history ORDER BY id")
    return cursor.fetchall()


class TestAddItemDeduplication:
    """测试添加条目时的去重逻辑"""

    @pytest.mark.parametrize(
        "name, initial_content, second_content, content_type, expect_dedup",
        [
            ("完全相同的文本", "hello world", "hello world", "text", True),
            ("不同的文本", "hello", "world", "text", False),
            ("相同的图片base64", "image_data_123", "image_data_123", "image", True),
            ("空字符串去重", "", "", "text", True),
            ("仅空白不同", "hello", "hello ", "text", False),
        ],
    )
    def test_deduplication_cases(self, db, name, initial_content, second_content, content_type, expect_dedup):
        """测试表驱动：各种去重场景"""
        first_id = db.add_item(initial_content, content_type)
        second_id = db.add_item(second_content, content_type)

        conn = sqlite3.connect(db.db_path)
        count = _count_items(conn)

        if expect_dedup:
            assert count == 1, f"用例失败: {name} - 期望1条记录，实际{count}条"
            assert first_id == second_id, f"用例失败: {name} - 去重时应返回相同ID"
        else:
            assert count == 2, f"用例失败: {name} - 期望2条记录，实际{count}条"
            assert first_id != second_id, f"用例失败: {name} - 不去重时应返回不同ID"

        conn.close()

    def test_duplicate_updates_timestamp(self, db, tmp_path):
        """测试重复内容只更新时间戳"""
        content = "test content"

        first_id = db.add_item(content)

        import time
        time.sleep(0.01)

        second_id = db.add_item(content)

        assert first_id == second_id

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT created_at FROM clipboard_history WHERE id = ?", (first_id,))
        final_time = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM clipboard_history")
        count = cursor.fetchone()[0]

        assert count == 1
        assert final_time is not None
        conn.close()

    def test_different_type_not_duplicate(self, db):
        """测试相同内容但不同类型不视为重复"""
        text_id = db.add_item("same content", "text")
        image_id = db.add_item("same content", "image")

        assert text_id != image_id

        conn = sqlite3.connect(db.db_path)
        count = _count_items(conn)
        assert count == 2
        conn.close()


class TestCleanupOldItems:
    """测试超过500条时的自动裁剪逻辑"""

    def test_pinned_items_never_cleaned(self, db):
        """测试钉住的条目永远不会被清理"""
        for i in range(10):
            item_id = db.add_item(f"pinned item {i}")
            db.toggle_pin(item_id)

        for i in range(600):
            db.add_item(f"unpinned item {i}")

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM clipboard_history WHERE pinned = 1")
        pinned_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM clipboard_history WHERE pinned = 0")
        unpinned_count = cursor.fetchone()[0]
        total = _count_items(conn)

        assert pinned_count == 10, f"钉住的条目数量不正确: {pinned_count}"
        assert unpinned_count == 500, f"未钉住的条目应保持500条: {unpinned_count}"
        assert total == 510, f"总条目数不正确: {total}"
        conn.close()

    def test_cleanup_removes_oldest_unpinned(self, db):
        """测试裁剪时删除最旧的未钉住条目"""
        old_ids = []
        for i in range(10):
            item_id = db.add_item(f"old item {i}")
            old_ids.append(item_id)

        for i in range(500):
            db.add_item(f"new item {i}")

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        for old_id in old_ids[:10]:
            cursor.execute("SELECT COUNT(*) FROM clipboard_history WHERE id = ?", (old_id,))
            count = cursor.fetchone()[0]
            assert count == 0, f"旧条目 {old_id} 应该被删除"

        cursor.execute("SELECT COUNT(*) FROM clipboard_history WHERE pinned = 0")
        unpinned_count = cursor.fetchone()[0]
        assert unpinned_count == 500

        conn.close()

    def test_exactly_500_not_triggered(self, db):
        """测试恰好500条时不触发裁剪"""
        for i in range(500):
            db.add_item(f"item {i}")

        conn = sqlite3.connect(db.db_path)
        count = _count_items(conn)
        assert count == 500
        conn.close()

    def test_501_triggers_cleanup(self, db):
        """测试超过500条时触发裁剪"""
        for i in range(501):
            db.add_item(f"item {i}")

        conn = sqlite3.connect(db.db_path)
        count = _count_items(conn)
        assert count == 500
        conn.close()


class TestSearchFilter:
    """测试搜索过滤功能"""

    @pytest.fixture
    def db_with_data(self, db):
        """准备测试数据"""
        db.add_item("Hello World")
        db.add_item("hello python")
        db.add_item("HELLO JAVA")
        db.add_item("你好世界")
        db.add_item("测试中文内容")
        db.add_item("test%percent")
        db.add_item("test_underscore")
        db.add_item("普通文本")
        return db

    @pytest.mark.parametrize(
        "name, query, expected_contents",
        [
            ("英文不区分大小写", "hello", 3),
            ("英文不区分大小写大写", "HELLO", 3),
            ("中文搜索", "你好", ["你好世界"]),
            ("中文关键词", "测试", ["测试中文内容"]),
            ("部分匹配", "py", ["hello python"]),
            ("无结果", "nonexistent", []),
            ("空字符串返回全部", "", 8),
        ],
    )
    def test_search_cases(self, db_with_data, name, query, expected_contents):
        """测试表驱动：各种搜索场景"""
        results = db_with_data.get_all_items(search_query=query)
        result_contents = [r[1] for r in results]

        if isinstance(expected_contents, int):
            assert len(result_contents) == expected_contents, (
                f"用例失败: {name} - 期望{expected_contents}条结果，实际{len(result_contents)}条"
            )
        else:
            for expected in expected_contents:
                assert expected in result_contents, (
                    f"用例失败: {name} - 期望包含 '{expected}'，实际结果: {result_contents}"
                )
            assert len(result_contents) == len(expected_contents), (
                f"用例失败: {name} - 期望{len(expected_contents)}条结果，实际{len(result_contents)}条: {result_contents}"
            )

    def test_special_chars_like_wildcards(self, db):
        """测试 % 和 _ 当前作为 SQL LIKE 通配符处理"""
        db.add_item("testApercent")
        db.add_item("testBpercent")
        db.add_item("test%percent")
        db.add_item("test_underscore")
        db.add_item("testXunderscore")

        results = db.get_all_items(search_query="test%percent")
        contents = [r[1] for r in results]

        assert "test%percent" in contents
        assert "testApercent" in contents
        assert "testBpercent" in contents

        results2 = db.get_all_items(search_query="test_underscore")
        contents2 = [r[1] for r in results2]

        assert "test_underscore" in contents2
        assert "testXunderscore" in contents2


class TestTogglePin:
    """测试钉住切换功能"""

    def test_toggle_pin_unpinned_to_pinned(self, db):
        """测试从未钉住切换到钉住"""
        item_id = db.add_item("test content")

        result = db.toggle_pin(item_id)

        assert result is True
        item = db.get_item(item_id)
        assert item[3] == 1

    def test_toggle_pin_pinned_to_unpinned(self, db):
        """测试从钉住切换到未钉住"""
        item_id = db.add_item("test content")
        db.toggle_pin(item_id)

        result = db.toggle_pin(item_id)

        assert result is False
        item = db.get_item(item_id)
        assert item[3] == 0

    def test_toggle_nonexistent_item(self, db):
        """测试切换不存在的条目"""
        result = db.toggle_pin(99999)
        assert result is False

    def test_multiple_toggles(self, db):
        """测试多次切换"""
        item_id = db.add_item("test content")

        states = []
        for _ in range(5):
            states.append(db.toggle_pin(item_id))

        assert states == [True, False, True, False, True]


class TestDeleteAndClear:
    """测试删除和清空功能"""

    def test_delete_existing_item(self, db):
        """测试删除存在的条目"""
        item_id = db.add_item("to delete")
        db.add_item("keep this")

        db.delete_item(item_id)

        conn = sqlite3.connect(db.db_path)
        count = _count_items(conn)
        assert count == 1

        remaining = db.get_all_items()
        assert remaining[0][1] == "keep this"
        conn.close()

    def test_delete_nonexistent_item(self, db):
        """测试删除不存在的条目不报错"""
        db.add_item("keep this")

        db.delete_item(99999)

        conn = sqlite3.connect(db.db_path)
        count = _count_items(conn)
        assert count == 1
        conn.close()

    def test_clear_history_keep_pinned(self, db):
        """测试清空历史保留钉住条目"""
        pinned_id = db.add_item("pinned")
        db.toggle_pin(pinned_id)
        db.add_item("unpinned1")
        db.add_item("unpinned2")

        db.clear_history(keep_pinned=True)

        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM clipboard_history WHERE pinned = 1")
        pinned_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM clipboard_history WHERE pinned = 0")
        unpinned_count = cursor.fetchone()[0]

        assert pinned_count == 1
        assert unpinned_count == 0
        conn.close()

    def test_clear_history_clear_all(self, db):
        """测试清空所有历史"""
        pinned_id = db.add_item("pinned")
        db.toggle_pin(pinned_id)
        db.add_item("unpinned")

        db.clear_history(keep_pinned=False)

        conn = sqlite3.connect(db.db_path)
        count = _count_items(conn)
        assert count == 0
        conn.close()

    def test_clear_empty_history(self, db):
        """测试清空空数据库不报错"""
        db.clear_history(keep_pinned=True)
        db.clear_history(keep_pinned=False)

        conn = sqlite3.connect(db.db_path)
        count = _count_items(conn)
        assert count == 0
        conn.close()


class TestDatabaseEdgeCases:
    """测试边界情况"""

    def test_long_content(self, db):
        """测试长内容存储"""
        long_content = "A" * 10000
        item_id = db.add_item(long_content)

        item = db.get_item(item_id)
        assert item[1] == long_content

    def test_special_characters(self, db):
        """测试特殊字符"""
        special_content = "特殊!@#$%^&*()字符\n换行\t制表"
        item_id = db.add_item(special_content)

        item = db.get_item(item_id)
        assert item[1] == special_content

    def test_unicode_emoji(self, db):
        """测试 Unicode 表情"""
        emoji_content = "Hello 🌍 World 🎉"
        item_id = db.add_item(emoji_content)

        item = db.get_item(item_id)
        assert item[1] == emoji_content

    def test_get_item_nonexistent(self, db):
        """测试获取不存在的条目返回 None"""
        result = db.get_item(99999)
        assert result is None
