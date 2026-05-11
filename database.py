import sqlite3
import os
import sys
from datetime import datetime
from typing import List, Optional, Tuple, Any


class ClipboardDatabase:
    MAX_HISTORY = 500

    def __init__(self, db_path: str = None):
        self.db_path = db_path if db_path else self._get_db_path()
        self._init_db()

    def _get_db_path(self) -> str:
        if sys.platform == 'win32':
            base_dir = os.path.join(os.environ.get('APPDATA', ''), 'ClipboardHistory')
        else:
            base_dir = os.path.join(os.path.expanduser('~'), '.clipboard_history')
        
        os.makedirs(base_dir, exist_ok=True)
        return os.path.join(base_dir, 'clipboard.db')

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clipboard_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'text',
                pinned INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pinned ON clipboard_history(pinned)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON clipboard_history(created_at)')
        
        conn.commit()
        conn.close()

    def add_item(self, content: str, content_type: str = 'text') -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT id FROM clipboard_history WHERE content = ? AND content_type = ? ORDER BY created_at DESC LIMIT 1',
            (content, content_type)
        )
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute(
                'UPDATE clipboard_history SET created_at = ? WHERE id = ?',
                (datetime.now().isoformat(), existing[0])
            )
            conn.commit()
            conn.close()
            return existing[0]
        
        cursor.execute(
            'INSERT INTO clipboard_history (content, content_type, created_at) VALUES (?, ?, ?)',
            (content, content_type, datetime.now().isoformat())
        )
        
        item_id = cursor.lastrowid
        conn.commit()
        
        self._cleanup_old_items()
        
        conn.close()
        return item_id

    def _cleanup_old_items(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM clipboard_history WHERE pinned = 0')
        unpinned_count = cursor.fetchone()[0]
        
        if unpinned_count > self.MAX_HISTORY:
            to_delete = unpinned_count - self.MAX_HISTORY
            cursor.execute('''
                DELETE FROM clipboard_history 
                WHERE id IN (
                    SELECT id FROM clipboard_history 
                    WHERE pinned = 0 
                    ORDER BY created_at ASC 
                    LIMIT ?
                )
            ''', (to_delete,))
            conn.commit()
        
        conn.close()

    def get_all_items(self, search_query: str = '') -> List[Tuple[Any, ...]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if search_query:
            cursor.execute('''
                SELECT id, content, content_type, pinned, created_at 
                FROM clipboard_history 
                WHERE content LIKE ?
                ORDER BY pinned DESC, created_at DESC
            ''', (f'%{search_query}%',))
        else:
            cursor.execute('''
                SELECT id, content, content_type, pinned, created_at 
                FROM clipboard_history 
                ORDER BY pinned DESC, created_at DESC
            ''')
        
        items = cursor.fetchall()
        conn.close()
        return items

    def toggle_pin(self, item_id: int) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT pinned FROM clipboard_history WHERE id = ?', (item_id,))
        result = cursor.fetchone()
        
        if result:
            new_pin_state = 0 if result[0] else 1
            cursor.execute(
                'UPDATE clipboard_history SET pinned = ? WHERE id = ?',
                (new_pin_state, item_id)
            )
            conn.commit()
            conn.close()
            return bool(new_pin_state)
        
        conn.close()
        return False

    def delete_item(self, item_id: int):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM clipboard_history WHERE id = ?', (item_id,))
        conn.commit()
        conn.close()

    def clear_history(self, keep_pinned: bool = True):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if keep_pinned:
            cursor.execute('DELETE FROM clipboard_history WHERE pinned = 0')
        else:
            cursor.execute('DELETE FROM clipboard_history')
        
        conn.commit()
        conn.close()

    def get_item(self, item_id: int) -> Optional[Tuple[Any, ...]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT id, content, content_type, pinned, created_at FROM clipboard_history WHERE id = ?',
            (item_id,)
        )
        
        item = cursor.fetchone()
        conn.close()
        return item
