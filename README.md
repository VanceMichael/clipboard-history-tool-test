# 剪贴板历史工具

一个跨平台（Windows/macOS）的系统托盘常驻剪贴板历史工具。

## 功能特性

- 自动记录复制的文本和图片
- 最多保留最近 500 条历史记录（未钉住的）
- 钉住功能：钉住的条目永远不会被自动清除，始终排在最前面
- 全局快捷键：Ctrl/Cmd+Shift+V 弹出历史列表
- 实时搜索过滤
- 右键菜单：复制、钉住/取消钉住、删除
- 关闭窗口只收起到托盘，托盘菜单中才有"退出"选项
- SQLite 持久化存储，下次启动可续上历史

## 安装

```bash
pip install -r requirements.txt
```

## 使用

```bash
python main.py
```

应用启动后会在系统托盘显示图标。

- **显示历史**：按 Ctrl/Cmd+Shift+V 或点击托盘图标
- **选择条目**：使用上下箭头键，按 Enter 选中
- **搜索**：在搜索框中输入文字实时过滤
- **钉住条目**：右键条目选择"钉住"
- **退出**：托盘图标右键选择"退出"

## 项目结构

```
.
├── main.py              # 应用入口文件，启动主应用
├── main_app.py          # 主应用类，整合所有模块（系统托盘、全局快捷键）
├── database.py          # SQLite 数据库管理模块，负责历史记录的存储和查询
├── clipboard_monitor.py # 剪贴板监控模块，监听剪贴板变化并保存记录
├── history_window.py    # 历史记录窗口，提供搜索、钉住、右键菜单等交互功能
├── requirements.txt     # Python 依赖包列表
└── README.md            # 项目说明文档
```

## 文件说明

- **main.py**：简洁的入口点，创建并运行主应用实例
- **main_app.py**：核心应用类，管理系统托盘、全局快捷键、各模块间通信
- **database.py**：使用标准库 sqlite3 实现的数据库模块，支持增删查改、钉住、搜索等功能
- **clipboard_monitor.py**：使用 PyQt6 的剪贴板 API 监控变化，支持文本和图片
- **history_window.py**：用户界面，展示历史列表、搜索框、右键菜单
- **requirements.txt**：列出项目所需的 PyQt6 和 pynput 依赖
# clipboard-history-tool-test
