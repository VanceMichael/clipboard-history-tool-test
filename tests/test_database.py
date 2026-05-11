import pytest
import time
from database import ClipboardDatabase


@pytest.fixture
def db(temp_db_path):
    return ClipboardDatabase(temp_db_path)


class TestAddItemDeduplication:
    @pytest.mark.parametrize(
        "test_case, content1, content2, type1, type2, expect_same_id",
        [
            ("相同文本相同类型", "hello", "hello", "text", "text", True),
            ("不同文本相同类型", "hello", "world", "text", "text", False),
            ("相同内容不同类型", "data", "data", "text", "image", False),
            ("空文本重复", "", "", "text", "text", True),
            ("中文内容重复", "你好世界", "你好世界", "text", "text", True),
            ("带特殊字符重复", "a%b_c", "a%b_c", "text", "text", True),
        ],
    )
    def test_duplicate_handling(self, db, test_case, content1, content2, type1, type2, expect_same_id):
        id1 = db.add_item(content1, type1)
        time.sleep(0.001)
        id2 = db.add_item(content2, type2)
        
        if expect_same_id:
            assert id1 == id2, f"用例失败: {test_case} - 期望相同ID但得到不同ID"
        else:
            assert id1 != id2, f"用例失败: {test_case} - 期望不同ID但得到相同ID"

    def test_duplicate_updates_timestamp(self, db):
        id1 = db.add_item("test content")
        item1 = db.get_item(id1)
        time.sleep(0.01)
        
        id2 = db.add_item("test content")
        item2 = db.get_item(id2)
        
        assert id1 == id2
        assert item1[4] != item2[4], "重复内容应该更新时间戳"


class TestCleanupOldItems:
    def test_pinned_items_never_cleaned(self, db):
        for i in range(10):
            item_id = db.add_item(f"content_{i}")
            if i < 3:
                db.toggle_pin(item_id)
        
        for i in range(10, ClipboardDatabase.MAX_HISTORY + 50):
            db.add_item(f"content_{i}")
        
        items = db.get_all_items()
        pinned_items = [item for item in items if item[3] == 1]
        
        assert len(pinned_items) == 3, "钉住的条目不应该被清理"

    def test_unpinned_items_trimmed_to_max(self, db):
        for i in range(ClipboardDatabase.MAX_HISTORY + 100):
            db.add_item(f"content_{i}")
        
        items = db.get_all_items()
        unpinned = [item for item in items if item[3] == 0]
        
        assert len(unpinned) <= ClipboardDatabase.MAX_HISTORY, f"未钉住条目应该不超过{ClipboardDatabase.MAX_HISTORY}条"

    def test_oldest_unpinned_cleaned_first(self, db):
        for i in range(10):
            db.add_item(f"old_content_{i}")
        
        db.MAX_HISTORY = 5
        for i in range(10):
            db.add_item(f"new_content_{i}")
        db.MAX_HISTORY = 500
        
        items = db.get_all_items()
        contents = [item[1] for item in items]
        
        old_count = sum(1 for c in contents if c.startswith("old_"))
        assert old_count <= 5, "旧的条目应该优先被清理"


class TestSearchFilter:
    @pytest.mark.parametrize(
        "test_case, content, search_query, should_find",
        [
            ("精确匹配英文", "hello world", "hello", True),
            ("大小写混写匹配", "Hello World", "Hello", True),
            ("大小写不同匹配", "HELLO", "hello", True),
            ("中文搜索", "你好世界", "世界", True),
            ("中文不匹配", "你好世界", "测试", False),
            ("部分匹配", "abc123def", "123", True),
            ("空搜索返回全部", "test content", "", True),
        ],
    )
    def test_basic_search(self, db, test_case, content, search_query, should_find):
        db.add_item(content)
        results = db.get_all_items(search_query)
        found = any(item[1] == content for item in results)
        
        if should_find:
            assert found, f"用例失败: {test_case} - 应该找到内容"
        else:
            assert not found, f"用例失败: {test_case} - 不应该找到内容"

    @pytest.mark.parametrize(
        "test_case, content, search_query",
        [
            ("百分号转义", "test%value", "test%value"),
            ("下划线转义", "test_value", "test_value"),
            ("混合特殊字符", "a%b_c%d", "a%b_c"),
        ],
    )
    def test_special_characters_in_search(self, db, test_case, content, search_query):
        db.add_item(content)
        db.add_item("other content")
        
        results = db.get_all_items(search_query)
        found = any(item[1] == content for item in results)
        
        assert found, f"用例失败: {test_case} - 特殊字符应该被正确搜索"


class TestTogglePin:
    def test_pin_unpin_cycle(self, db):
        item_id = db.add_item("test content")
        
        result1 = db.toggle_pin(item_id)
        assert result1 is True, "第一次切换应该钉住"
        item1 = db.get_item(item_id)
        assert item1[3] == 1, "钉住状态应该为1"
        
        result2 = db.toggle_pin(item_id)
        assert result2 is False, "第二次切换应该取消钉住"
        item2 = db.get_item(item_id)
        assert item2[3] == 0, "未钉住状态应该为0"
        
        result3 = db.toggle_pin(item_id)
        assert result3 is True, "第三次切换应该重新钉住"

    def test_toggle_nonexistent_item(self, db):
        result = db.toggle_pin(999999)
        assert result is False, "不存在的条目应该返回False"


class TestDeleteAndClear:
    def test_delete_item(self, db):
        item_id = db.add_item("to delete")
        assert db.get_item(item_id) is not None
        
        db.delete_item(item_id)
        assert db.get_item(item_id) is None, "删除后条目应该不存在"

    def test_delete_nonexistent_item_no_error(self, db):
        db.delete_item(999999)

    def test_clear_history_keep_pinned(self, db):
        for i in range(5):
            item_id = db.add_item(f"item_{i}")
            if i < 2:
                db.toggle_pin(item_id)
        
        db.clear_history(keep_pinned=True)
        items = db.get_all_items()
        
        assert len(items) == 2, "应该保留钉住的2条记录"
        assert all(item[3] == 1 for item in items), "保留的都应该是钉住的"

    def test_clear_history_all(self, db):
        for i in range(5):
            item_id = db.add_item(f"item_{i}")
            if i < 2:
                db.toggle_pin(item_id)
        
        db.clear_history(keep_pinned=False)
        items = db.get_all_items()
        
        assert len(items) == 0, "应该清空所有记录"

    def test_clear_empty_history(self, db):
        db.clear_history()
        db.clear_history(keep_pinned=False)
