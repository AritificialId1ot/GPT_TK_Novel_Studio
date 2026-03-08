# Novel Studio GUI v7

Novel Studio GUI 是一个用于长篇小说创作的 AI 写作工作台。  
该软件基于 **Python + Tkinter** 开发，将对话式 AI、结构化草稿流程、写作素材管理和本地语料分析整合到一个统一的写作环境中。

与普通聊天工具不同，本系统将写作组织为 **会话（Session）、素材资产（Assets）、草稿工作区（Draft Workspace）和语料库（Corpus）**，从而支持长期写作项目保持风格一致性和世界观稳定性。

---

# 功能特点

## 对话式写作

系统提供持续的对话式写作界面，可用于互动式创作。

主要功能：

- 基于会话的写作项目管理
- 持久化对话历史
- AI 自动生成回复
- 结构化 Prompt 组装
- 历史记录导入导出

每一条对话都会存储在数据库中，并与对应写作项目关联。

---

# 草稿工作台

草稿工作台提供一个完整的结构化写作流程。

工作流程分为三个阶段：

1. 草稿生成
2. 草稿评审
3. 草稿改稿

工作区包含以下字段：

| 字段 | 说明 |
|-----|------|
| Draft Task | 写作任务或剧情描述 |
| Current Draft | 当前草稿内容 |
| Review Result | AI 评审意见 |
| Extra Requirements | 额外修改要求 |
| Review Prompt Template | 评审模板 |

典型工作流程：

```
写草稿任务
→ 生成草稿
→ 评审草稿
→ 添加修改要求
→ 改稿
→ 接受草稿到历史记录
```

工作区内容会自动保存。

---

# 写作素材系统

写作上下文由结构化素材控制。

支持的素材类型：

| 素材 | 用途 |
|------|------|
| Combo | 标签组合和主题组合 |
| Style DNA | 文风规则 |
| Lexicon | 词汇偏好 |
| Bible | 世界观设定 |
| Recap | 前文剧情总结 |

启用后，这些素材会被加入 **系统提示词（System Prompt）** 中。

这样模型生成内容时就会遵循设定好的世界观和风格规则。

---

# 语料库分析

系统支持扫描本地语料库目录。

支持的文件格式：

```
.txt
.md
.markdown
.text
```

每个文件会记录以下信息：

- 文件路径
- 修改时间
- 文件大小
- SHA1 校验
- 推断标签
- 分析结果

这些信息会存储在 SQLite 数据库中。

---

# 标签推断系统

语料扫描器内置标签体系。

主要分类包括：

- 背景
- 题材
- 内容
- 人物
- 身体部位

系统通过匹配文件名和文本内容中的关键词进行标签推断。

示例同义词组：

```
tickling
挠痒
胳肢
呵痒
くすぐり
```

推断出的标签可用于语料分析和素材生成。

---

# Pixiv 标签发现

系统支持从 Pixiv 获取相关标签。

流程如下：

1. 将内部标签映射为 Pixiv 搜索词
2. 获取 Pixiv 标签页面
3. 提取相关标签
4. 识别未知标签
5. 分类新标签

该功能可用于扩展语料库的主题和词汇范围。

---

# 模型任务分配

不同任务使用不同模型。

默认配置：

| 任务 | 模型 |
|----|------|
| 对话 | gpt-5-mini |
| 草稿生成 | gpt-5.4 |
| 草稿评审 | gpt-5-mini |
| 草稿改稿 | gpt-5.4 |
| 语料分析 | gpt-5-nano |

这种任务级模型分配可以平衡速度、成本和生成质量。

---

# 系统架构

程序采用三层结构：

```
run_app.py
      ↓
GUI界面层 (gui_app.py)
      ↓
后端服务层 (core_adapter.py)
```

---

# 项目结构

```
project-root
│
├── run_app.py
├── gui_app.py
├── core_adapter.py
│
├── README.md
└── requirements.txt
```

文件说明：

| 文件 | 说明 |
|-----|------|
| run_app.py | 程序入口 |
| gui_app.py | 图形界面 |
| core_adapter.py | 后端逻辑 |

---

# 模块说明

## run_app.py

程序入口。

功能：

- 启动应用
- 打开 GUI 界面

不包含业务逻辑。

---

## gui_app.py

Tkinter 图形界面实现。

主要功能：

- 主窗口布局
- 会话管理
- 对话界面
- 草稿工作区
- 语料管理
- 后台任务执行
- 进度显示

核心类：

```
App
```

---

## core_adapter.py

后端核心服务。

主要职责：

- 数据库初始化
- 数据表升级
- 会话管理
- 草稿状态存储
- 模型调用
- Prompt 构建
- 语料扫描
- 标签推断
- Pixiv 标签获取

核心类：

```
BackendService
```

---

# 数据库设计

系统使用 SQLite 存储数据。

主要数据表：

| 表 | 说明 |
|---|------|
| sessions | 写作项目和素材 |
| turns | 对话历史 |
| draft_states | 草稿状态 |
| corpus_files | 语料文件 |
| file_analyses | 语料分析 |

结构示例：

```
sessions
 ├ combo
 ├ style_dna
 ├ lexicon
 ├ bible
 └ recap

turns
 ├ role
 ├ content
 ├ timestamp
 └ meta

draft_states
 ├ task_text
 ├ draft_text
 ├ review_text
 └ extra_text
```

---

# Prompt 构建

系统提示词由启用的素材组合生成。

可能包含：

```
Combo
Style DNA
Lexicon
Bible
Recap
运行时语料参考
```

这些内容会拼接形成最终 Prompt。

---

# Token 控制策略

为避免超过模型输入限制，系统会截断长文本。

策略：

```
文本开头
...
文本结尾
```

对于消息列表：

```
保留 system prompt
优先保留最近消息
截断旧消息
```

---

# 后台任务系统

耗时操作在后台线程执行。

例如：

- 模型生成
- 语料扫描
- 标签分析

执行流程：

```
后台线程
↓
结果队列
↓
GUI 轮询
```

这样可以避免界面卡死。

---

# 安装

要求：

```
Python 3.9+
```

依赖库：

```
openai
requests
beautifulsoup4
```

安装：

```
pip install openai requests beautifulsoup4
```

Tkinter 和 SQLite 通常随 Python 自带。

---

# 运行程序

运行：

```
python run_app.py
```

程序会自动打开 GUI 界面。

---

# 配置目录

用户配置保存在：

```
~/.novel_studio_gui/
```

结构示例：

```
.novel_studio_gui
 ├ ui_settings.json
 └ train_corpus/
```

数据库路径查找顺序：

1. 环境变量 `NOVEL_STUDIO_DB`
2. 程序目录
3. 当前工作目录
4. 用户主目录
5. 默认数据库文件

---

# 典型使用流程

示例写作流程：

1. 创建新会话
2. 添加世界观素材（Bible / Style DNA / Lexicon）
3. 启用需要的素材
4. 编写草稿任务
5. 生成草稿
6. 评审草稿
7. 添加修改要求
8. 改稿
9. 接受草稿进入历史记录

---

# 故障排查

## 程序无法启动

检查 Python 版本：

```
python --version
```

需要：

```
Python 3.9+
```

---

## AI 无响应

可能原因：

- 未配置 API Key
- 网络问题
- 输入过长

设置 API Key：

```
export OPENAI_API_KEY=your_key
```

---

## 语料扫描无结果

确认文件格式：

```
.txt
.md
.markdown
.text
```

---

# 当前限制

目前存在的限制：

- 进度条为活动指示而非精确百分比
- Pixiv 抓取依赖网页结构
- Tkinter 界面较为简单
- 超长上下文会被截断

---

# 未来计划

未来可能增加：

- 模型流式输出
- 语料 embedding 检索
- 章节管理系统
- 更现代的 GUI 框架
- 项目打包导出

---

# License

本项目用于研究和创作用途。

用户需要遵守所使用 AI 模型服务提供商的相关使用条款。
