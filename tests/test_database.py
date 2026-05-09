import pytest
import sqlite3
import os
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from database import ClipboardDatabase


@pytest.fixture
def db(tmp_path):
    with patch.object(ClipboardDatabase, '_get_db_path', return_value=str(tmp_path / 'test.db')):
        database = ClipboardDatabase()
        database.db_path = str(tmp_path / 'test.db')
        database._init_db()
        yield database
    db_file = tmp_path / 'test.db'
    if db_file.exists():
        os.unlink(db_file)


def _count_rows(db, where=''):
    conn = sqlite3.connect(db.db_path)
    sql = 'SELECT COUNT(*) FROM clipboard_history'
    if where:
        sql += f' WHERE {where}'
    count = conn.execute(sql).fetchone()[0]
    conn.close()
    return count


def _insert_item(db, content, content_type='text', pinned=0, created_at=None):
    conn = sqlite3.connect(db.db_path)
    if created_at is None:
        created_at = datetime.now().isoformat()
    conn.execute(
        'INSERT INTO clipboard_history (content, content_type, pinned, created_at) VALUES (?, ?, ?, ?)',
        (content, content_type, pinned, created_at),
    )
    conn.commit()
    last_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()
    return last_id


def _make_timestamps(n, base=datetime(2024, 1, 1)):
    return [(base + timedelta(seconds=i)).isoformat() for i in range(n)]


class TestAddItemDedup:
    @pytest.mark.parametrize(
        "label,content1,type1,content2,type2,expect_same_row",
        [
            ("same_text_same_type", "hello", "text", "hello", "text", True),
            ("same_text_diff_type", "hello", "text", "hello", "image", False),
            ("empty_string", "", "text", "", "text", True),
        ],
        ids=lambda x: x if isinstance(x, str) else None,
    )
    def test_dedup_table_driven(self, db, label, content1, type1, content2, type2, expect_same_row):
        id1 = db.add_item(content1, type1)
        id2 = db.add_item(content2, type2)
        if expect_same_row:
            assert id1 == id2, f"[{label}] 相同内容+类型应返回相同 id，got id1={id1} id2={id2}"
            assert _count_rows(db) == 1, f"[{label}] 相同内容+类型只应保留 1 行，got {_count_rows(db)}"
        else:
            assert id1 != id2, f"[{label}] 同内容不同 content_type 不应去重"
            assert _count_rows(db) == 2, f"[{label}] 同内容不同 content_type 应有 2 行"

    def test_dedup_updates_timestamp(self, db):
        id1 = db.add_item("hello")
        conn = sqlite3.connect(db.db_path)
        old_ts = conn.execute('SELECT created_at FROM clipboard_history WHERE id=?', (id1,)).fetchone()[0]
        conn.close()

        time.sleep(0.05)
        id2 = db.add_item("hello")

        assert id1 == id2
        conn = sqlite3.connect(db.db_path)
        new_ts = conn.execute('SELECT created_at FROM clipboard_history WHERE id=?', (id1,)).fetchone()[0]
        conn.close()
        assert new_ts >= old_ts, "去重更新时 created_at 应该更新"

    def test_different_content_not_deduped(self, db):
        db.add_item("aaa")
        db.add_item("bbb")
        assert _count_rows(db) == 2

    def test_dedup_checks_both_content_and_type(self, db):
        id1 = db.add_item("hello", "text")
        id2 = db.add_item("hello", "image")
        assert id1 != id2, "相同 content 但不同 content_type 不应去重"
        assert _count_rows(db) == 2


class TestCleanupOldItems:
    def test_trim_to_max_history(self, db):
        timestamps = _make_timestamps(510)
        for i in range(510):
            _insert_item(db, f"item_{i:04d}", pinned=0, created_at=timestamps[i])
        db._cleanup_old_items()
        unpinned = _count_rows(db, 'pinned=0')
        assert unpinned <= ClipboardDatabase.MAX_HISTORY, (
            f"未钉住记录应 <= {ClipboardDatabase.MAX_HISTORY}，实际 {unpinned}"
        )

    def test_pinned_items_never_cleaned(self, db):
        pinned_ids = set()
        pinned_ts = _make_timestamps(10)
        for i in range(10):
            pid = _insert_item(db, f"pinned_{i}", pinned=1, created_at=pinned_ts[i])
            pinned_ids.add(pid)
        unpinned_ts = _make_timestamps(510)
        for i in range(510):
            _insert_item(db, f"unpinned_{i}", pinned=0, created_at=unpinned_ts[i])
        db._cleanup_old_items()
        conn = sqlite3.connect(db.db_path)
        surviving_pinned = {r[0] for r in conn.execute('SELECT id FROM clipboard_history WHERE pinned=1').fetchall()}
        conn.close()
        assert pinned_ids == surviving_pinned, f"钉住条目应全部保留，丢失: {pinned_ids - surviving_pinned}"

    def test_oldest_unpinned_deleted_first(self, db):
        old_id = _insert_item(db, "old", pinned=0, created_at=datetime(2020, 1, 1).isoformat())
        timestamps = _make_timestamps(500)
        for i in range(500):
            _insert_item(db, f"new_{i}", pinned=0, created_at=timestamps[i])
        db._cleanup_old_items()
        assert db.get_item(old_id) is None, "最旧的未钉住条目应被清理"

    def test_no_cleanup_when_under_limit(self, db):
        timestamps = _make_timestamps(10)
        for i in range(10):
            _insert_item(db, f"item_{i}", pinned=0, created_at=timestamps[i])
        db._cleanup_old_items()
        assert _count_rows(db) == 10, "未超限不应清理"


class TestSearchFilter:
    @pytest.mark.parametrize(
        "label,query,expected_count",
        [
            ("case_mixed", "HeLLo", 2),
            ("chinese_keyword", "你好", 1),
            ("percent_sign", "100%", 1),
            ("underscore", "test_value", 1),
            ("no_match", "zzz_not_exist", 0),
        ],
    )
    def test_search_table_driven(self, db, label, query, expected_count):
        seed_data = [
            ("hello world", "text"),
            ("HELLO WORLD", "text"),
            ("你好世界", "text"),
            ("100% 完成", "text"),
            ("test_value check", "text"),
            ("unrelated content", "text"),
        ]
        for content, ctype in seed_data:
            db.add_item(content, ctype)
        results = db.get_all_items(search_query=query)
        assert len(results) == expected_count, (
            f"[{label}] query={query!r} 期望 {expected_count} 条，实际 {len(results)} 条"
        )

    def test_empty_query_returns_all(self, db):
        db.add_item("a")
        db.add_item("b")
        assert len(db.get_all_items()) == 2

    def test_like_wildcard_percent_as_wildcard(self, db):
        db.add_item("discount 50% off")
        db.add_item("discount 50 percent off")
        results = db.get_all_items(search_query="50%")
        matched = [r[1] for r in results]
        assert "discount 50% off" in matched, (
            "搜索 '50%' 应包含 'discount 50% off'"
        )
        assert "discount 50 percent off" in matched, (
            "SQL LIKE 中 % 是通配符，'50%' 实际匹配 '50' 后接任意字符，所以 '50 percent off' 也会被匹配"
        )

    def test_like_wildcard_underscore_as_wildcard(self, db):
        db.add_item("a_b")
        db.add_item("axb")
        results = db.get_all_items(search_query="a_b")
        matched = [r[1] for r in results]
        assert "a_b" in matched, "搜索 'a_b' 应包含 a_b"
        assert "axb" in matched, (
            "SQL LIKE 中 _ 是单字符通配符，'a_b' 同时匹配 'axb'，这是已知行为"
        )

    def test_search_ordering_pinned_first(self, db):
        db.add_item("alpha")
        pid = db.add_item("alpha pinned")
        db.toggle_pin(pid)
        results = db.get_all_items(search_query="alpha")
        assert results[0][3] == 1, "搜索结果中钉住的条目应排在前面"


class TestTogglePin:
    @pytest.mark.parametrize(
        "label,initial_pinned,expect_after_toggle",
        [
            ("unpin_pinned", True, False),
            ("pin_unpinned", False, True),
        ],
    )
    def test_toggle_pin_table_driven(self, db, label, initial_pinned, expect_after_toggle):
        pid = _insert_item(db, "item", pinned=1 if initial_pinned else 0)
        result = db.toggle_pin(pid)
        assert result == expect_after_toggle, (
            f"[{label}] toggle_pin 返回值期望 {expect_after_toggle}，实际 {result}"
        )
        item = db.get_item(pid)
        assert item[3] == (1 if expect_after_toggle else 0), (
            f"[{label}] 数据库中 pinned 状态不一致"
        )

    def test_toggle_pin_twice_returns_original(self, db):
        pid = _insert_item(db, "item", pinned=0)
        db.toggle_pin(pid)
        final = db.toggle_pin(pid)
        assert final is False, "来回切换两次应回到原始状态"

    def test_toggle_pin_nonexistent(self, db):
        result = db.toggle_pin(999999)
        assert result is False, "不存在的 id 应返回 False"


class TestDeleteItem:
    def test_delete_existing(self, db):
        pid = db.add_item("to_delete")
        assert db.get_item(pid) is not None
        db.delete_item(pid)
        assert db.get_item(pid) is None

    def test_delete_nonexistent_no_error(self, db):
        db.delete_item(999999)

    def test_delete_pinned_item(self, db):
        pid = _insert_item(db, "pinned_item", pinned=1)
        db.delete_item(pid)
        assert db.get_item(pid) is None, "钉住的条目也应能被删除"


class TestClearHistory:
    @pytest.mark.parametrize(
        "label,keep_pinned,pinned_survive,unpinned_survive",
        [
            ("keep_pinned_True", True, True, False),
            ("keep_pinned_False", False, False, False),
        ],
    )
    def test_clear_history_table_driven(self, db, label, keep_pinned, pinned_survive, unpinned_survive):
        _insert_item(db, "unpinned", pinned=0)
        _insert_item(db, "pinned", pinned=1)
        db.clear_history(keep_pinned=keep_pinned)
        pinned_count = _count_rows(db, 'pinned=1')
        unpinned_count = _count_rows(db, 'pinned=0')
        if pinned_survive:
            assert pinned_count == 1, f"[{label}] 钉住条目应保留"
        else:
            assert pinned_count == 0, f"[{label}] 钉住条目应被清除"
        if unpinned_survive:
            assert unpinned_count == 1, f"[{label}] 未钉住条目应保留"
        else:
            assert unpinned_count == 0, f"[{label}] 未钉住条目应被清除"

    def test_clear_empty_db_no_error(self, db):
        db.clear_history(keep_pinned=True)
        db.clear_history(keep_pinned=False)


class TestGetItem:
    def test_get_existing(self, db):
        pid = db.add_item("fetch_me")
        item = db.get_item(pid)
        assert item is not None
        assert item[1] == "fetch_me"

    def test_get_nonexistent(self, db):
        assert db.get_item(999999) is None


class TestGetAllItemsOrdering:
    def test_pinned_before_unpinned(self, db):
        uid = db.add_item("unpinned")
        pid = db.add_item("pinned")
        db.toggle_pin(pid)
        items = db.get_all_items()
        ids = [r[0] for r in items]
        assert ids.index(pid) < ids.index(uid), "钉住的条目应排在未钉住之前"
