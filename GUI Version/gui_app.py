from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable, Dict, List, Optional

from core_adapter import (DEFAULT_REVIEW_TEMPLATE, BackendService,
                          ProgressProxy, backend, load_ui_settings,
                          normalize_tags, save_ui_settings, tag_category,
                          tags_to_tree_text)

ROLE_COLORS = {
    'user_header': '#1f6feb',
    'assistant_header': '#8b5cf6',
    'system_header': '#b45309',
    'user_body': '#0f172a',
    'assistant_body': '#111827',
    'system_body': '#334155',
    'match_bg': '#fff3a3',
}

TASK_LABELS = {
    'chat': '聊天',
    'draft': '生成草稿',
    'review': '草稿评审',
    'revise': '改稿',
    'analysis': '语料分析',
}

ASSET_TITLES = ['Combo', 'Style DNA', 'Lexicon', 'Bible', 'Recap']


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.service = BackendService()
        self.ui = load_ui_settings()
        self.title(f"小说工作台 v7 - {Path(self.service.db_path).name}")
        self.geometry(f"{self.ui.get('window_width', 1800)}x{self.ui.get('window_height', 1120)}")
        self.minsize(1450, 900)

        self.current_session = None
        self._session_ids: List[int] = []
        self.turn_offsets: List[str] = []
        self.result_queue: 'queue.Queue[Callable[[], None]]' = queue.Queue()

        self.search_var = tk.StringVar(value='')
        self.progress_var = tk.StringVar(value='就绪')
        self.font_size_var = tk.IntVar(value=int(self.ui.get('font_size', 14)))
        self.border_var = tk.IntVar(value=int(self.ui.get('text_border_width', 1)))
        self.max_files_var = tk.StringVar(value=str(self.ui.get('max_files', 200)))
        self.corpus_dir_var = tk.StringVar(value=self.ui.get('corpus_dir_default', backend.DEFAULT_TRAIN_DIR))
        self.asset_paths: Dict[str, tk.StringVar] = {
            'Combo': tk.StringVar(value=self.ui.get('default_combo_path', '')),
            'Bible': tk.StringVar(value=self.ui.get('default_bible_path', '')),
            'Recap': tk.StringVar(value=self.ui.get('default_recap_path', '')),
        }
        self.pixiv_suggestions: List[Dict[str, Any]] = []
        self.pixiv_suggestion_vars: Dict[str, tk.BooleanVar] = {}
        self.selected_tags: List[str] = []
        self.tag_filter_var = tk.StringVar(value='')

        self.task_model_vars: Dict[str, tk.StringVar] = {}
        task_models = dict(backend.TASK_MODEL_DEFAULTS)
        task_models.update(self.ui.get('task_models', {}) or {})
        for task in TASK_LABELS:
            self.task_model_vars[task] = tk.StringVar(value=task_models.get(task, backend.TASK_MODEL_DEFAULTS[task]))

        self._apply_dpi_settings()
        self._build_ui()
        self.apply_text_style()
        self.after(100, self._drain_queue)
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.refresh_sessions(select_first=True)

    def _apply_dpi_settings(self):
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        try:
            self.tk.call('tk', 'scaling', max(1.35, self.winfo_fpixels('1i') / 72.0))
        except Exception:
            pass

    def _font(self, delta: int = 0, weight: str = 'normal'):
        return (self.ui.get('font_family', 'Microsoft YaHei UI'), self.font_size_var.get() + delta, weight)

    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=(8, 8, 8, 6))
        top.grid(row=0, column=0, columnspan=2, sticky='ew')
        for i in range(18):
            top.columnconfigure(i, weight=0)
        top.columnconfigure(15, weight=1)

        ttk.Button(top, text='新建会话', command=self.create_session).grid(row=0, column=0, padx=4)
        ttk.Button(top, text='重命名', command=self.rename_session).grid(row=0, column=1, padx=4)
        ttk.Button(top, text='删除会话', command=self.delete_session).grid(row=0, column=2, padx=4)
        ttk.Button(top, text='重置对话链', command=self.reset_chain).grid(row=0, column=3, padx=4)

        ttk.Label(top, text='字号').grid(row=0, column=4, padx=(14, 2))
        ttk.Spinbox(top, from_=10, to=28, textvariable=self.font_size_var, width=5, command=self.apply_text_style).grid(row=0, column=5, padx=2)
        ttk.Label(top, text='边框').grid(row=0, column=6, padx=(10, 2))
        ttk.Spinbox(top, from_=0, to=6, textvariable=self.border_var, width=5, command=self.apply_text_style).grid(row=0, column=7, padx=2)
        ttk.Button(top, text='应用外观', command=self.apply_text_style).grid(row=0, column=8, padx=4)

        ttk.Label(top, text='搜索历史').grid(row=0, column=9, padx=(14, 2))
        ttk.Entry(top, textvariable=self.search_var, width=24).grid(row=0, column=10, padx=2)
        ttk.Button(top, text='上一个', command=lambda: self.search_history(False)).grid(row=0, column=11, padx=2)
        ttk.Button(top, text='下一个', command=lambda: self.search_history(True)).grid(row=0, column=12, padx=2)
        ttk.Button(top, text='顶部', command=lambda: self.history_text.yview_moveto(0.0)).grid(row=0, column=13, padx=2)
        ttk.Button(top, text='底部', command=lambda: self.history_text.yview_moveto(1.0)).grid(row=0, column=14, padx=2)

        self.pbar = ttk.Progressbar(top, mode='indeterminate', length=160)
        self.pbar.grid(row=0, column=16, padx=(6, 6))
        ttk.Label(top, textvariable=self.progress_var, font=self._font()).grid(row=0, column=17, sticky='e')

        left = ttk.Frame(self, padding=(8, 0, 4, 8))
        left.grid(row=1, column=0, sticky='nsew')
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text='会话列表', font=self._font(1, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 6))
        self.session_list = tk.Listbox(left, exportselection=False, width=28, font=self._font())
        self.session_list.grid(row=1, column=0, sticky='nsew')
        self.session_list.bind('<<ListboxSelect>>', self.on_session_select)
        y = ttk.Scrollbar(left, orient='vertical', command=self.session_list.yview)
        y.grid(row=1, column=1, sticky='ns')
        self.session_list.configure(yscrollcommand=y.set)

        main = ttk.Panedwindow(self, orient='horizontal')
        main.grid(row=1, column=1, sticky='nsew', padx=(4, 8), pady=(0, 8))

        history_wrap = ttk.Frame(main, padding=4)
        history_wrap.columnconfigure(0, weight=1)
        history_wrap.rowconfigure(1, weight=1)
        ttk.Label(history_wrap, text='历史记录（输入与回复合并）', font=self._font(1, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 6))
        hist_inner = ttk.Frame(history_wrap)
        hist_inner.grid(row=1, column=0, sticky='nsew')
        hist_inner.columnconfigure(0, weight=1)
        hist_inner.rowconfigure(0, weight=1)

        self.history_text = tk.Text(hist_inner, wrap='word', font=self._font(), padx=12, pady=12, relief='solid', borderwidth=self.border_var.get())
        self.history_text.grid(row=0, column=0, sticky='nsew')
        self.history_text.configure(state='disabled')
        sy = ttk.Scrollbar(hist_inner, orient='vertical', command=self.history_text.yview)
        sy.grid(row=0, column=1, sticky='ns')
        self.history_text.configure(yscrollcommand=sy.set)

        nav = ttk.Frame(hist_inner)
        nav.grid(row=0, column=2, sticky='ns', padx=(6, 0))
        ttk.Label(nav, text='定位', font=self._font()).pack(anchor='w')
        self.history_nav = tk.Listbox(nav, exportselection=False, width=18, font=self._font(-1))
        self.history_nav.pack(fill='y', expand=True)
        self.history_nav.bind('<<ListboxSelect>>', self.on_nav_select)
        nsy = ttk.Scrollbar(nav, orient='vertical', command=self.history_nav.yview)
        nsy.pack(fill='y', side='right')
        self.history_nav.configure(yscrollcommand=nsy.set)

        tabs = ttk.Notebook(main)
        main.add(history_wrap, weight=3)
        main.add(tabs, weight=2)

        self.chat_tab = ttk.Frame(tabs, padding=8)
        self.draft_tab = ttk.Frame(tabs, padding=8)
        self.assets_tab = ttk.Frame(tabs, padding=8)
        self.corpus_tab = ttk.Frame(tabs, padding=8)
        self.model_tab = ttk.Frame(tabs, padding=8)
        tabs.add(self.chat_tab, text='聊天')
        tabs.add(self.draft_tab, text='草稿工作台')
        tabs.add(self.assets_tab, text='素材与开关')
        tabs.add(self.corpus_tab, text='DNA / 语料库')
        tabs.add(self.model_tab, text='模型设置')

        self._build_chat_tab()
        self._build_draft_tab()
        self._build_assets_tab()
        self._build_corpus_tab()
        self._build_model_tab()

    def _build_chat_tab(self):
        parent = self.chat_tab
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        ttk.Label(parent, text='输入', font=self._font(1, 'bold')).grid(row=0, column=0, sticky='w')
        self.input_text = ScrolledText(parent, wrap='word', height=18, font=self._font(), relief='solid', borderwidth=self.border_var.get(), padx=10, pady=10)
        self.input_text.grid(row=1, column=0, sticky='nsew', pady=(6, 8))
        btns = ttk.Frame(parent)
        btns.grid(row=2, column=0, sticky='ew')
        ttk.Button(btns, text='发送', command=self.send_chat).pack(side='left', padx=(0, 6))
        ttk.Button(btns, text='清空输入', command=lambda: self.input_text.delete('1.0', 'end')).pack(side='left', padx=6)
        ttk.Button(btns, text='从文件导入', command=lambda: self.load_text_into(self.input_text)).pack(side='left', padx=6)
        ttk.Button(btns, text='导出历史', command=self.export_history).pack(side='left', padx=6)

    def _build_draft_tab(self):
        parent = self.draft_tab
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        for r in (1, 4, 6):
            parent.rowconfigure(r, weight=1)

        ttk.Label(parent, text='草稿任务', font=self._font(1, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Label(parent, text='评审提示词模板', font=self._font(1, 'bold')).grid(row=0, column=1, sticky='w')
        self.draft_task = ScrolledText(parent, wrap='word', height=8, font=self._font(), relief='solid', borderwidth=self.border_var.get(), padx=10, pady=10)
        self.review_template = ScrolledText(parent, wrap='word', height=8, font=self._font(), relief='solid', borderwidth=self.border_var.get(), padx=10, pady=10)
        self.draft_task.grid(row=1, column=0, sticky='nsew', padx=(0, 6), pady=(6, 8))
        self.review_template.grid(row=1, column=1, sticky='nsew', padx=(6, 0), pady=(6, 8))

        bar = ttk.Frame(parent)
        bar.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(0, 8))
        ttk.Button(bar, text='生成草稿', command=self.generate_draft).pack(side='left', padx=(0, 6))
        ttk.Button(bar, text='评审当前稿', command=self.review_draft).pack(side='left', padx=6)
        ttk.Button(bar, text='保存草稿状态', command=self.save_draft_state).pack(side='left', padx=6)
        ttk.Button(bar, text='从文件载入任务', command=lambda: self.load_text_into(self.draft_task)).pack(side='left', padx=6)
        ttk.Button(bar, text='重置评审模板', command=self.reset_review_template).pack(side='left', padx=6)

        ttk.Label(parent, text='当前草稿', font=self._font(1, 'bold')).grid(row=3, column=0, sticky='w')
        ttk.Label(parent, text='评审结果（可手改）', font=self._font(1, 'bold')).grid(row=3, column=1, sticky='w')
        self.draft_current = ScrolledText(parent, wrap='word', height=14, font=self._font(), relief='solid', borderwidth=self.border_var.get(), padx=10, pady=10)
        self.draft_review = ScrolledText(parent, wrap='word', height=14, font=self._font(), relief='solid', borderwidth=self.border_var.get(), padx=10, pady=10)
        self.draft_current.grid(row=4, column=0, sticky='nsew', padx=(0, 6), pady=(6, 8))
        self.draft_review.grid(row=4, column=1, sticky='nsew', padx=(6, 0), pady=(6, 8))

        ttk.Label(parent, text='额外修改要求', font=self._font(1, 'bold')).grid(row=5, column=0, sticky='w')
        extra_wrap = ttk.Frame(parent)
        extra_wrap.grid(row=6, column=0, columnspan=2, sticky='nsew')
        extra_wrap.columnconfigure(0, weight=1)
        extra_wrap.rowconfigure(0, weight=1)
        self.draft_extra = ScrolledText(extra_wrap, wrap='word', height=8, font=self._font(), relief='solid', borderwidth=self.border_var.get(), padx=10, pady=10)
        self.draft_extra.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
        side = ttk.Frame(extra_wrap)
        side.grid(row=0, column=1, sticky='ns')
        ttk.Button(side, text='改稿', command=self.revise_draft).pack(fill='x', pady=(0, 6))
        ttk.Button(side, text='接受到历史', command=self.accept_draft).pack(fill='x', pady=6)
        ttk.Button(side, text='导出当前稿', command=lambda: self.save_text_from(self.draft_current)).pack(fill='x', pady=6)
        ttk.Button(side, text='导出评审', command=lambda: self.save_text_from(self.draft_review)).pack(fill='x', pady=6)

    def _build_assets_tab(self):
        parent = self.assets_tab
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        flags = ttk.LabelFrame(parent, text='启用项', padding=10)
        flags.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        self.use_combo = tk.BooleanVar(value=False)
        self.use_style = tk.BooleanVar(value=False)
        self.use_lexicon = tk.BooleanVar(value=False)
        self.use_bible = tk.BooleanVar(value=False)
        self.use_recap = tk.BooleanVar(value=False)
        self.use_corpus = tk.BooleanVar(value=False)
        self.asset_switches = {}
        for i, (label, var, cmd) in enumerate([
            ('组合包', self.use_combo, self.on_toggle_combo),
            ('Style DNA', self.use_style, self.on_toggle_style_like),
            ('Lexicon', self.use_lexicon, self.on_toggle_style_like),
            ('Bible', self.use_bible, self.save_asset_flags),
            ('Recap', self.use_recap, self.save_asset_flags),
            ('运行时语料库', self.use_corpus, self.on_toggle_style_like),
        ]):
            cb = ttk.Checkbutton(flags, text=label, variable=var, command=cmd)
            cb.grid(row=0, column=i, padx=8, sticky='w')
            self.asset_switches[label] = cb

        self.asset_notebook = ttk.Notebook(parent)
        self.asset_notebook.grid(row=1, column=0, sticky='nsew')
        self.combo_box = self._add_asset_tab('Combo')
        self.style_box = self._add_asset_tab('Style DNA')
        self.lexicon_box = self._add_asset_tab('Lexicon')
        self.bible_box = self._add_asset_tab('Bible')
        self.recap_box = self._add_asset_tab('Recap')

        bottom = ttk.Frame(parent)
        bottom.grid(row=2, column=0, sticky='ew', pady=(10, 0))
        ttk.Button(bottom, text='保存当前素材', command=self.save_assets).pack(side='left', padx=(0, 6))
        ttk.Button(bottom, text='导入到当前页', command=self.load_into_selected_asset).pack(side='left', padx=6)
        ttk.Button(bottom, text='导入组合包', command=self.import_combo_package).pack(side='left', padx=6)

    def _add_asset_tab(self, title: str):
        frame = ttk.Frame(self.asset_notebook, padding=8)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(1, weight=1)
        head = ttk.Frame(frame)
        head.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 6))
        head.columnconfigure(1, weight=1)
        ttk.Label(head, text='文件路径').grid(row=0, column=0, sticky='w')
        path_var = self.asset_paths.get(title, tk.StringVar(value=''))
        self.asset_paths[title] = path_var
        ttk.Entry(head, textvariable=path_var).grid(row=0, column=1, sticky='ew', padx=6)
        ttk.Button(head, text='选择文件', command=lambda t=title: self.load_asset_from_file(t)).grid(row=0, column=2, padx=4)
        ttk.Button(head, text='设为默认', command=lambda t=title: self.save_default_path(t)).grid(row=0, column=3, padx=4)
        ttk.Button(head, text='清空路径', command=lambda t=title: self.clear_asset_path(t)).grid(row=0, column=4, padx=4)
        text = ScrolledText(frame, wrap='word', font=self._font(), relief='solid', borderwidth=self.border_var.get(), padx=10, pady=10)
        text.grid(row=1, column=0, columnspan=2, sticky='nsew')
        self.asset_notebook.add(frame, text=title)
        return text

    def _build_corpus_tab(self):
        parent = self.corpus_tab
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(3, weight=1)
        parent.rowconfigure(5, weight=1)

        row1 = ttk.Frame(parent)
        row1.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 8))
        row1.columnconfigure(1, weight=1)
        ttk.Label(row1, text='语料目录').grid(row=0, column=0, sticky='w')
        ttk.Entry(row1, textvariable=self.corpus_dir_var).grid(row=0, column=1, sticky='ew', padx=6)
        ttk.Button(row1, text='选择目录', command=self.pick_corpus_dir).grid(row=0, column=2, padx=4)
        ttk.Button(row1, text='设为默认', command=self.save_default_corpus_dir).grid(row=0, column=3, padx=4)
        ttk.Button(row1, text='扫描语料', command=self.corpus_scan).grid(row=0, column=4, padx=4)
        ttk.Button(row1, text='推断标签', command=self.corpus_infer).grid(row=0, column=5, padx=4)
        ttk.Button(row1, text='分析语料', command=self.corpus_analyze).grid(row=0, column=6, padx=4)

        row2 = ttk.Frame(parent)
        row2.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 8))
        ttk.Label(row2, text='最大文件数').pack(side='left')
        ttk.Entry(row2, textvariable=self.max_files_var, width=8).pack(side='left', padx=6)
        ttk.Button(row2, text='查看标签统计', command=self.show_tag_counts).pack(side='left', padx=6)
        ttk.Button(row2, text='查看标签词典', command=self.show_tag_dictionary).pack(side='left', padx=6)
        ttk.Button(row2, text='Pixiv 自动分析', command=self.pixiv_analyze).pack(side='left', padx=6)
        ttk.Button(row2, text='加入勾选候选标签', command=self.add_checked_pixiv_tags).pack(side='left', padx=6)
        ttk.Button(row2, text='生成 Style DNA', command=self.build_style_dna).pack(side='left', padx=6)
        ttk.Button(row2, text='生成 Lexicon', command=self.build_lexicon).pack(side='left', padx=6)
        ttk.Button(row2, text='生成组合包', command=self.build_combo).pack(side='left', padx=6)

        candidate_frame = ttk.LabelFrame(parent, text='Pixiv 候选新增标签', padding=6)
        candidate_frame.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(0, 8))
        candidate_frame.columnconfigure(0, weight=1)
        self.pixiv_candidate_text = ScrolledText(candidate_frame, wrap='word', height=7, font=self._font(), relief='solid', borderwidth=self.border_var.get(), padx=8, pady=8)
        self.pixiv_candidate_text.grid(row=0, column=0, sticky='ew')

        tree_frame = ttk.LabelFrame(parent, text='标签树（双击加入已选标签）', padding=6)
        tree_frame.grid(row=3, column=0, sticky='nsew', padx=(0, 6), pady=(0, 8))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(1, weight=1)
        filter_bar = ttk.Frame(tree_frame)
        filter_bar.grid(row=0, column=0, sticky='ew', pady=(0, 6))
        ttk.Label(filter_bar, text='筛选').pack(side='left')
        ttk.Entry(filter_bar, textvariable=self.tag_filter_var, width=20).pack(side='left', padx=6)
        ttk.Button(filter_bar, text='应用', command=self.populate_tag_tree).pack(side='left', padx=4)
        ttk.Button(filter_bar, text='重置', command=self.reset_tag_filter).pack(side='left', padx=4)
        self.tag_tree = ttk.Treeview(tree_frame, show='tree')
        self.tag_tree.grid(row=1, column=0, sticky='nsew')
        tty = ttk.Scrollbar(tree_frame, orient='vertical', command=self.tag_tree.yview)
        tty.grid(row=1, column=1, sticky='ns')
        self.tag_tree.configure(yscrollcommand=tty.set)
        self.tag_tree.bind('<Double-1>', self.on_tag_tree_double_click)

        pick_frame = ttk.LabelFrame(parent, text='已选标签', padding=6)
        pick_frame.grid(row=3, column=1, sticky='nsew', pady=(0, 8))
        pick_frame.columnconfigure(0, weight=1)
        pick_frame.rowconfigure(1, weight=1)
        ttk.Label(pick_frame, text='当前组合').grid(row=0, column=0, sticky='w')
        self.selected_list = tk.Listbox(pick_frame, exportselection=False, font=self._font())
        self.selected_list.grid(row=1, column=0, sticky='nsew')
        psy = ttk.Scrollbar(pick_frame, orient='vertical', command=self.selected_list.yview)
        psy.grid(row=1, column=1, sticky='ns')
        self.selected_list.configure(yscrollcommand=psy.set)
        pick_btn = ttk.Frame(pick_frame)
        pick_btn.grid(row=2, column=0, sticky='ew', pady=(6, 0))
        ttk.Button(pick_btn, text='移除选中', command=self.remove_selected_tag).pack(side='left', padx=(0, 6))
        ttk.Button(pick_btn, text='清空', command=self.clear_selected_tags).pack(side='left', padx=6)
        ttk.Button(pick_btn, text='从当前会话组合载入', command=self.load_combo_from_session).pack(side='left', padx=6)

        ttk.Label(parent, text='输出', font=self._font(1, 'bold')).grid(row=4, column=0, columnspan=2, sticky='w')
        self.corpus_output = ScrolledText(parent, wrap='word', font=self._font(), relief='solid', borderwidth=self.border_var.get(), padx=10, pady=10)
        self.corpus_output.grid(row=5, column=0, columnspan=2, sticky='nsew')
        parent.rowconfigure(5, weight=1)
        self.populate_tag_tree()

    def _build_model_tab(self):
        parent = self.model_tab
        parent.columnconfigure(0, weight=1)
        info = ttk.LabelFrame(parent, text='任务模型选择', padding=10)
        info.grid(row=0, column=0, sticky='ew')
        models = list(backend.MODEL_CATALOG.keys())
        for i, task in enumerate(TASK_LABELS):
            ttk.Label(info, text=TASK_LABELS[task]).grid(row=i, column=0, sticky='w', pady=4)
            cb = ttk.Combobox(info, values=models, textvariable=self.task_model_vars[task], state='readonly', width=24)
            cb.grid(row=i, column=1, sticky='w', padx=6)
            ttk.Button(info, text='查看上限', command=lambda t=task: self.show_model_info(t)).grid(row=i, column=2, padx=6)
        ttk.Button(info, text='保存模型选择', command=self.save_model_choices).grid(row=len(TASK_LABELS), column=1, sticky='w', pady=(10, 0))

        self.model_info_text = ScrolledText(parent, wrap='word', height=20, font=self._font(), relief='solid', borderwidth=self.border_var.get(), padx=10, pady=10)
        self.model_info_text.grid(row=1, column=0, sticky='nsew', pady=(10, 0))
        parent.rowconfigure(1, weight=1)
        self.refresh_model_info_panel()

    def apply_text_style(self):
        widgets = [
            getattr(self, name) for name in [
                'history_text', 'input_text', 'draft_task', 'review_template', 'draft_current', 'draft_review', 'draft_extra',
                'style_box', 'lexicon_box', 'bible_box', 'recap_box', 'corpus_output', 'model_info_text'
            ] if hasattr(self, name)
        ]
        for w in widgets:
            w.configure(font=self._font(), borderwidth=self.border_var.get())
        if hasattr(self, 'session_list'):
            self.session_list.configure(font=self._font())
            self.history_nav.configure(font=self._font(-1))
            self.selected_list.configure(font=self._font())
        self._configure_history_tags()
        save_ui_settings({'font_size': self.font_size_var.get(), 'text_border_width': self.border_var.get()})

    def _configure_history_tags(self):
        t = self.history_text
        t.tag_configure('user_header', foreground=ROLE_COLORS['user_header'], font=self._font(0, 'bold'))
        t.tag_configure('assistant_header', foreground=ROLE_COLORS['assistant_header'], font=self._font(0, 'bold'))
        t.tag_configure('system_header', foreground=ROLE_COLORS['system_header'], font=self._font(0, 'bold'))
        t.tag_configure('user_body', foreground=ROLE_COLORS['user_body'], spacing3=10)
        t.tag_configure('assistant_body', foreground=ROLE_COLORS['assistant_body'], spacing3=14)
        t.tag_configure('system_body', foreground=ROLE_COLORS['system_body'], spacing3=10)
        t.tag_configure('match', background=ROLE_COLORS['match_bg'])
        t.tag_configure('meta', foreground='#64748b', font=self._font(-1))

    def set_progress(self, text: str, active: bool):
        self.progress_var.set(text)
        try:
            if active:
                self.pbar.start(12)
            else:
                self.pbar.stop()
        except Exception:
            pass

    def _progress_from_worker(self, text: str, active: bool):
        self.result_queue.put(lambda text=text, active=active: self.set_progress(text, active))

    def run_bg(self, title: str, fn: Callable[[], Any], done: Callable[[Any], None]):
        self.set_progress(title, True)

        def _safe_done(result: Any):
            try:
                done(result)
            except Exception as e:
                messagebox.showerror('错误', f'后台任务完成后更新界面失败：\n{e}')

        def worker():
            try:
                result = fn()
                self.result_queue.put(lambda result=result: _safe_done(result))
            except Exception as e:
                self.result_queue.put(lambda e=e: messagebox.showerror('错误', str(e)))
            finally:
                self.result_queue.put(lambda: self.set_progress('就绪', False))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_queue(self):
        try:
            while True:
                cb = self.result_queue.get_nowait()
                try:
                    cb()
                except Exception as e:
                    messagebox.showerror('错误', f'界面队列处理失败：\n{e}')
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def refresh_sessions(self, select_first: bool = False, select_id: Optional[int] = None):
        rows = self.service.list_sessions()
        self.session_list.delete(0, 'end')
        self._session_ids = []
        for row in rows:
            self.session_list.insert('end', f'{row.id:>4}  {row.title}')
            self._session_ids.append(row.id)
        if not rows:
            s = self.service.create_session('新会话')
            self.refresh_sessions(select_id=s.session_id)
            return
        if select_id and select_id in self._session_ids:
            idx = self._session_ids.index(select_id)
            self.session_list.selection_clear(0, 'end')
            self.session_list.selection_set(idx)
            self.session_list.see(idx)
            self.load_session(select_id)
        elif select_first:
            self.session_list.selection_set(0)
            self.load_session(self._session_ids[0])

    def load_session(self, session_id: int):
        self.current_session = self.service.load_session(session_id)
        self.populate_assets()
        self.populate_draft_state()
        self.load_combo_from_session(silent=True)
        self.render_history()

    def on_session_select(self, event=None):
        sel = self.session_list.curselection()
        if sel:
            self.load_session(self._session_ids[sel[0]])

    def create_session(self):
        title = simpledialog.askstring('新建会话', '输入会话标题：', initialvalue='新会话')
        if title is None:
            return
        s = self.service.create_session(title)
        self.refresh_sessions(select_id=s.session_id)

    def rename_session(self):
        if not self.current_session:
            return
        title = simpledialog.askstring('重命名', '输入新标题：', initialvalue=self.current_session.title)
        if title is None:
            return
        self.service.rename_session(self.current_session.session_id, title)
        self.refresh_sessions(select_id=self.current_session.session_id)

    def delete_session(self):
        if not self.current_session:
            return
        sid = self.current_session.session_id
        title = self.current_session.title
        remaining = [x for x in self._session_ids if x != sid]
        next_id = remaining[0] if remaining else None
        if not messagebox.askyesno('删除会话', f'确定删除会话 {sid} - {title} 吗？'):
            return
        self.service.delete_session(sid)
        self.current_session = None
        self.refresh_sessions(select_first=next_id is None, select_id=next_id)

    def reset_chain(self):
        if self.current_session:
            self.current_session = self.service.reset_chain(self.current_session)
            self.set_progress('对话链已重置', False)

    def render_history(self):
        if not self.current_session:
            return
        turns = self.service.get_turns(self.current_session.session_id)
        self.history_nav.delete(0, 'end')
        self.turn_offsets = []
        t = self.history_text
        t.configure(state='normal')
        t.delete('1.0', 'end')
        self._configure_history_tags()
        for idx, turn in enumerate(turns, 1):
            role = turn['role']
            header_tag = f'{role}_header' if f'{role}_header' in {'user_header', 'assistant_header', 'system_header'} else 'system_header'
            body_tag = f'{role}_body' if f'{role}_body' in {'user_body', 'assistant_body', 'system_body'} else 'system_body'
            start = t.index('end-1c')
            t.insert('end', f"[{turn['created_at']}] {role.upper()}\n", header_tag)
            if turn.get('meta'):
                meta = ', '.join(f'{k}={v}' for k, v in list(turn['meta'].items())[:4])
                if meta:
                    t.insert('end', meta + '\n', 'meta')
            t.insert('end', (turn['content'] or '').rstrip() + '\n\n', body_tag)
            self.history_nav.insert('end', f"{idx:03d} {role[:1].upper()} {turn['created_at'][11:19]}")
            self.turn_offsets.append(start)
        t.configure(state='disabled')
        self.history_text.yview_moveto(1.0)

    def on_nav_select(self, event=None):
        sel = self.history_nav.curselection()
        if sel and self.turn_offsets:
            idx = sel[0]
            self.history_text.see(self.turn_offsets[idx])

    def search_history(self, next_match: bool = True):
        needle = self.search_var.get().strip()
        if not needle:
            return
        t = self.history_text
        t.tag_remove('match', '1.0', 'end')
        matches = []
        pos = '1.0'
        while True:
            found = t.search(needle, pos, stopindex='end', nocase=True)
            if not found:
                break
            end = f'{found}+{len(needle)}c'
            t.tag_add('match', found, end)
            matches.append(found)
            pos = end
        if not matches:
            return
        current = t.index('insert')
        target = None
        if next_match:
            for m in matches:
                if t.compare(m, '>', current):
                    target = m
                    break
            target = target or matches[0]
        else:
            for m in reversed(matches):
                if t.compare(m, '<', current):
                    target = m
                    break
            target = target or matches[-1]
        t.mark_set('insert', target)
        t.see(target)

    def populate_assets(self):
        if not self.current_session:
            return
        s = self.current_session
        self.use_combo.set(bool(getattr(s, 'use_combo', False)))
        self.use_style.set(bool(s.use_style))
        self.use_lexicon.set(bool(s.use_lexicon))
        self.use_bible.set(bool(s.use_bible))
        self.use_recap.set(bool(s.use_recap))
        self.use_corpus.set(bool(s.use_runtime_corpus))
        self._set_text(self.combo_box, getattr(s, 'combo_text', ''))
        self.asset_paths['Combo'].set(getattr(s, 'combo_path', '') or self.asset_paths['Combo'].get())
        self._set_text(self.style_box, s.style_dna)
        self._set_text(self.lexicon_box, s.lexicon_text)
        self._set_text(self.bible_box, s.bible)
        self._set_text(self.recap_box, s.recap)
        self.sync_asset_switch_states()
        self.asset_paths['Bible'].set(getattr(s, 'bible_path', '') or self.ui.get('default_bible_path', ''))
        self.asset_paths['Recap'].set(getattr(s, 'recap_path', '') or self.ui.get('default_recap_path', ''))

    def populate_draft_state(self):
        if not self.current_session:
            return
        state = self.service.get_gui_state(self.current_session.session_id)
        self._set_text(self.draft_task, state.get('draft_task', ''))
        self._set_text(self.review_template, state.get('review_prompt_template', DEFAULT_REVIEW_TEMPLATE))
        self._set_text(self.draft_current, state.get('draft_current', ''))
        self._set_text(self.draft_review, state.get('draft_review', ''))
        self._set_text(self.draft_extra, state.get('draft_extra', ''))

    def sync_asset_switch_states(self):
        if getattr(self, 'use_combo', None) is None:
            return
        if self.use_combo.get() and (self.use_style.get() or self.use_lexicon.get() or self.use_corpus.get()):
            self.use_style.set(False)
            self.use_lexicon.set(False)
            self.use_corpus.set(False)
        combo_disabled = self.use_style.get() or self.use_lexicon.get() or self.use_corpus.get()
        style_disabled = self.use_combo.get()
        if hasattr(self, 'asset_switches'):
            self.asset_switches.get('组合包') and self.asset_switches['组合包'].state(['disabled' if combo_disabled else '!disabled'])
            for key in ('Style DNA', 'Lexicon', '运行时语料库'):
                if key in self.asset_switches:
                    self.asset_switches[key].state(['disabled' if style_disabled else '!disabled'])

    def on_toggle_combo(self):
        if self.use_combo.get():
            self.use_style.set(False)
            self.use_lexicon.set(False)
            self.use_corpus.set(False)
        self.sync_asset_switch_states()
        self.save_asset_flags()

    def on_toggle_style_like(self):
        if self.use_style.get() or self.use_lexicon.get() or self.use_corpus.get():
            self.use_combo.set(False)
        self.sync_asset_switch_states()
        self.save_asset_flags()

    def save_asset_flags(self):
        if not self.current_session:
            return
        self.sync_asset_switch_states()
        self.current_session = self.service.update_session(
            self.current_session,
            use_combo=self.use_combo.get(),
            use_style=self.use_style.get(),
            use_lexicon=self.use_lexicon.get(),
            use_bible=self.use_bible.get(),
            use_recap=self.use_recap.get(),
            use_runtime_corpus=self.use_corpus.get(),
        )

    def save_assets(self, refresh: bool = True):
        if not self.current_session:
            return
        self.current_session = self.service.update_session(
            self.current_session,
            combo_text=self._get_text(self.combo_box),
            combo_path=self.asset_paths['Combo'].get(),
            style_dna=self._get_text(self.style_box),
            lexicon_text=self._get_text(self.lexicon_box),
            bible=self._get_text(self.bible_box),
            recap=self._get_text(self.recap_box),
            bible_path=self.asset_paths['Bible'].get(),
            recap_path=self.asset_paths['Recap'].get(),
            use_style=self.use_style.get(),
            use_lexicon=self.use_lexicon.get(),
            use_bible=self.use_bible.get(),
            use_recap=self.use_recap.get(),
            use_runtime_corpus=self.use_corpus.get(),
        )
        if refresh:
            self.refresh_sessions(select_id=self.current_session.session_id)

    def load_asset_from_file(self, title: str):
        initial = self.asset_paths.get(title, tk.StringVar()).get() or os.path.expanduser('~')
        path = filedialog.askopenfilename(initialdir=str(Path(initial).parent) if initial else os.path.expanduser('~'), filetypes=[('文本', '*.txt *.md *.text'), ('所有文件', '*.*')])
        if not path:
            return
        text = self.service.load_text(path)
        widget_map = {'Combo': self.combo_box, 'Style DNA': self.style_box, 'Lexicon': self.lexicon_box, 'Bible': self.bible_box, 'Recap': self.recap_box}
        self._set_text(widget_map[title], text)
        self.asset_paths[title].set(path)
        if title == 'Combo' and self.current_session:
            self.current_session = self.service.update_session(self.current_session, combo_text=text, combo_path=path)
        if title in ('Bible', 'Recap') and self.current_session:
            kwargs = {'bible_path': self.asset_paths['Bible'].get(), 'recap_path': self.asset_paths['Recap'].get()}
            if title == 'Bible':
                kwargs['bible'] = text
            if title == 'Recap':
                kwargs['recap'] = text
            self.current_session = self.service.update_session(self.current_session, **kwargs)

    def clear_asset_path(self, title: str):
        self.asset_paths[title].set('')
        if self.current_session and title in ('Bible', 'Recap'):
            self.current_session = self.service.update_session(
                self.current_session,
                bible_path=self.asset_paths['Bible'].get(),
                recap_path=self.asset_paths['Recap'].get(),
            )

    def save_default_path(self, title: str):
        key = 'default_bible_path' if title == 'Bible' else 'default_recap_path'
        save_ui_settings({key: self.asset_paths[title].get()})
        self.ui = load_ui_settings()
        self.set_progress(f'{title} 默认路径已保存', False)

    def refresh_recap_before_draft(self):
        if not self.current_session:
            return
        updated = self.service.refresh_recap_from_path(self.current_session)
        self.current_session = updated
        self._set_text(self.recap_box, updated.recap)
        self.asset_paths['Recap'].set(getattr(updated, 'recap_path', '') or '')

    def save_draft_state(self, silent: bool = False):
        if not self.current_session:
            return
        self.service.save_gui_state(
            self.current_session.session_id,
            draft_task=self._get_text(self.draft_task),
            draft_current=self._get_text(self.draft_current),
            draft_review=self._get_text(self.draft_review),
            draft_extra=self._get_text(self.draft_extra),
            review_prompt_template=self._get_text(self.review_template),
        )
        if not silent:
            self.refresh_sessions(select_id=self.current_session.session_id)
            self.set_progress('草稿状态已保存', False)

    def send_chat(self):
        if not self.current_session:
            return
        text = self._get_text(self.input_text).strip()
        if not text:
            return
        self.save_assets(refresh=False)
        self.save_model_choices(silent=True)

        def task():
            return self.service.chat_once(self.current_session, text, progress=ProgressProxy())

        def done(result):
            self.current_session, _ = result
            self.input_text.delete('1.0', 'end')
            self.refresh_sessions(select_id=self.current_session.session_id)
            self.render_history()

        self.run_bg('正在生成回复…', task, done)

    def generate_draft(self):
        if not self.current_session:
            return
        self.save_draft_state(silent=True)
        self.save_assets(refresh=False)
        self.save_model_choices(silent=True)
        self.refresh_recap_before_draft()

        task_text = self._get_text(self.draft_task).strip()
        if not task_text:
            messagebox.showwarning('提示', '草稿任务不能为空。')
            return

        review_template = self._get_text(self.review_template).strip() or DEFAULT_REVIEW_TEMPLATE

        # 先把界面里的内容完整保存，防止刷新时任务框被清空
        self.service.save_gui_state(
            self.current_session.session_id,
            draft_task=self._get_text(self.draft_task),
            draft_current=self._get_text(self.draft_current),
            draft_review=self._get_text(self.draft_review),
            draft_extra=self._get_text(self.draft_extra),
            review_prompt_template=review_template,
        )

        def task():
            return self.service.draft_generate(
                self.current_session,
                task_text,
                progress=ProgressProxy(self._progress_from_worker),
            )

        def done(out):
            self._set_text(self.draft_current, out or '')
            self.save_draft_state(silent=True)
            if not (out or '').strip():
                messagebox.showwarning('提示', '草稿生成结果为空，请检查模型返回或 API 配置。')

        self.run_bg('正在生成草稿…', task, done)

    def review_draft(self):
        if not self.current_session:
            return
        self.save_draft_state(silent=True)
        self.save_assets(refresh=False)
        self.save_model_choices(silent=True)
        self.refresh_recap_before_draft()

        draft = self._get_text(self.draft_current).strip()
        if not draft:
            messagebox.showwarning('提示', '当前草稿为空。')
            return

        review_template = self._get_text(self.review_template).strip() or DEFAULT_REVIEW_TEMPLATE

        # 先保存界面状态，防止中途刷新把文本冲掉
        self.service.save_gui_state(
            self.current_session.session_id,
            draft_task=self._get_text(self.draft_task),
            draft_current=self._get_text(self.draft_current),
            draft_review=self._get_text(self.draft_review),
            draft_extra=self._get_text(self.draft_extra),
            review_prompt_template=review_template,
        )

        def task():
            return self.service.draft_review(
                self.current_session,
                draft,
                review_template,
                progress=ProgressProxy(self._progress_from_worker),
            )

        def done(out):
            review_text = (out or '').strip()
            if not review_text and self.current_session:
                state = self.service.get_gui_state(self.current_session.session_id)
                review_text = (state.get('draft_review') or '').strip()
            self._set_text(self.draft_review, review_text)
            try:
                self.draft_review.edit_reset()
                self.draft_review.see('1.0')
                self.draft_review.update_idletasks()
            except Exception:
                pass
            self.service.save_gui_state(
                self.current_session.session_id,
                draft_task=self._get_text(self.draft_task),
                draft_current=self._get_text(self.draft_current),
                draft_review=review_text,
                draft_extra=self._get_text(self.draft_extra),
                review_prompt_template=self._get_text(self.review_template),
            )
            self.refresh_sessions(select_id=self.current_session.session_id)
            if not review_text:
                messagebox.showwarning('提示', '评审结果为空，请检查模型返回或 API 配置。')

        self.run_bg('正在评审草稿…', task, done)

    def revise_draft(self):
        if not self.current_session:
            return
        self.save_draft_state(silent=True)
        self.save_assets(refresh=False)
        self.save_model_choices(silent=True)
        self.refresh_recap_before_draft()

        draft = self._get_text(self.draft_current).strip()
        if not draft:
            messagebox.showwarning('提示', '当前草稿为空。')
            return

        task_text = self._get_text(self.draft_task)
        review_text = self._get_text(self.draft_review)
        extra_text = self._get_text(self.draft_extra)

        # 先保存界面状态，防止中途刷新把文本冲掉
        self.service.save_gui_state(
            self.current_session.session_id,
            draft_task=task_text,
            draft_current=draft,
            draft_review=review_text,
            draft_extra=extra_text,
            review_prompt_template=self._get_text(self.review_template),
        )

        def task():
            return self.service.draft_revise(
                self.current_session,
                task_text,
                draft,
                review_text,
                extra_text,
                progress=ProgressProxy(self._progress_from_worker),
            )

        def done(out):
            self._set_text(self.draft_current, out or '')
            self.save_draft_state(silent=True)
            if not (out or '').strip():
                messagebox.showwarning('提示', '改稿结果为空，请检查模型返回或 API 配置。')

        self.run_bg('正在改稿…', task, done)

    def accept_draft(self):
        if not self.current_session:
            return
        final_text = self._get_text(self.draft_current).strip()
        if not final_text:
            return
        self.service.accept_draft_to_history(self.current_session, final_text)
        self.render_history()
        self.refresh_sessions(select_id=self.current_session.session_id)
        self.set_progress('草稿已写入历史', False)

    def reset_review_template(self):
        self._set_text(self.review_template, DEFAULT_REVIEW_TEMPLATE)

    def pick_corpus_dir(self):
        folder = filedialog.askdirectory(initialdir=self.corpus_dir_var.get() or os.path.expanduser('~'))
        if folder:
            self.corpus_dir_var.set(folder)

    def save_default_corpus_dir(self):
        save_ui_settings({'corpus_dir_default': self.corpus_dir_var.get(), 'max_files': self._get_max_files()})
        self.ui = load_ui_settings()
        self.set_progress('语料目录默认值已保存', False)

    def corpus_scan(self):
        folder = self.corpus_dir_var.get().strip() or backend.DEFAULT_TRAIN_DIR
        self.save_default_corpus_dir()
        self.run_bg('正在扫描语料…', lambda: self.service.corpus_scan(folder), lambda r: self._append_output(f'扫描完成：总数={r[0]}，更新={r[1]}\n'))

    def corpus_infer(self):
        self.run_bg('正在推断标签…', lambda: self.service.corpus_infer(self._get_max_files()), lambda _: self._append_output('标签推断完成。\n'))

    def corpus_analyze(self):
        self.run_bg('正在分析语料…', lambda: self.service.corpus_analyze(self._get_max_files()), lambda _: self._append_output('语料分析完成。\n'))

    def show_tag_counts(self):
        counts = self.service.corpus_tag_counts()
        self._set_text(self.corpus_output, '\n'.join(f'{tag}：{cnt}' for tag, cnt in counts))

    def show_tag_dictionary(self):
        self._set_text(self.corpus_output, self.service.available_tag_dictionary_text())

    def pixiv_analyze(self):
        tags = self._get_selected_tags()
        if not tags:
            messagebox.showwarning('提示', '请先从标签树中选择至少一个标签。')
            return
        self.run_bg('正在检索 Pixiv 标签…', lambda: self.service.pixiv_auto_analyze_tags(tags), self._on_pixiv_result)

    def _on_pixiv_result(self, result):
        matched = (result or {}).get('matched', [])
        self.pixiv_suggestions = (result or {}).get('suggestions', [])
        self.pixiv_suggestion_vars = {item['tag']: tk.BooleanVar(value=False) for item in self.pixiv_suggestions}
        lines = []
        if matched:
            lines.append('Pixiv 中已命中的现有标签：')
            lines.extend(f'- {tag}：{score}' for tag, score in matched)
        if self.pixiv_suggestions:
            lines.append('')
            lines.append('候选新增标签（勾选后可加入标签树）：')
            lines.extend(f'[ ] {item["tag"]} ｜建议分类：{item["category"]}｜命中：{item["score"]}' for item in self.pixiv_suggestions)
        if not lines:
            lines = ['Pixiv 自动分析没有拿到可用结果。']
        txt='\n'.join(lines)
        self._set_text(self.pixiv_candidate_text, txt)
        self._set_text(self.corpus_output, txt)
        if self.pixiv_suggestions:
            self._open_pixiv_picker()

    def _open_pixiv_picker(self):
        win = tk.Toplevel(self)
        win.title('选择要加入标签树的 Pixiv 候选标签')
        win.geometry('760x520')
        outer = ttk.Frame(win, padding=10)
        outer.pack(fill='both', expand=True)
        holder = ScrolledText(outer, wrap='word', font=self._font())
        holder.pack(fill='both', expand=True)
        holder.insert('end', '以下候选来自 Pixiv 页面标签提取。请勾选后点击下方按钮加入标签树。\n\n')
        checks=[]
        for item in self.pixiv_suggestions:
            var=self.pixiv_suggestion_vars[item['tag']]
            cb=ttk.Checkbutton(outer, text=f"{item['tag']} ｜{item['category']}｜命中 {item['score']}", variable=var)
            checks.append(cb)
            holder.window_create('end', window=cb)
            holder.insert('end', '\n')
        holder.configure(state='disabled')
        btn=ttk.Frame(outer)
        btn.pack(fill='x', pady=(8,0))
        ttk.Button(btn, text='全选', command=lambda:[v.set(True) for v in self.pixiv_suggestion_vars.values()]).pack(side='left', padx=4)
        ttk.Button(btn, text='加入标签树', command=lambda:(self.add_checked_pixiv_tags(), win.destroy())).pack(side='left', padx=4)
        ttk.Button(btn, text='关闭', command=win.destroy).pack(side='left', padx=4)

    def add_checked_pixiv_tags(self):
        picked=[]
        for item in self.pixiv_suggestions:
            if self.pixiv_suggestion_vars.get(item['tag']) and self.pixiv_suggestion_vars[item['tag']].get():
                picked.append({'tag': item['tag'], 'category': item['category']})
        if not picked:
            messagebox.showinfo('提示', '还没有勾选候选标签。')
            return
        added=self.service.add_custom_tags(picked)
        self.populate_tag_tree()
        self.show_tag_dictionary()
        self.set_progress(f'已新增 {added} 个标签到词典', False)

    def build_style_dna(self):
        tags = self._get_selected_tags()
        if not tags:
            messagebox.showwarning('提示', '请先选择标签。')
            return
        self.run_bg('正在生成 Style DNA…', lambda: self.service.style_build_from_tags(tags, self._get_max_files()), self._on_style_built)

    def _on_style_built(self, text: str):
        self._set_text(self.style_box, text)
        self._set_text(self.corpus_output, text)
        if self.current_session:
            self.current_session = self.service.update_session(self.current_session, style_dna=text)

    def build_lexicon(self):
        tags = self._get_selected_tags()
        if not tags:
            messagebox.showwarning('提示', '请先选择标签。')
            return
        self.run_bg('正在生成 Lexicon…', lambda: self.service.lexicon_build_from_tags(tags, self._get_max_files()), self._on_lexicon_built)

    def _on_lexicon_built(self, text: str):
        self._set_text(self.lexicon_box, text)
        self._set_text(self.corpus_output, text)
        if self.current_session:
            self.current_session = self.service.update_session(self.current_session, lexicon_text=text)

    def build_combo(self):
        tags = self._get_selected_tags()
        if not tags:
            messagebox.showwarning('提示', '请先选择标签。')
            return
        self.run_bg('正在生成组合包…', lambda: self.service.combo_build_from_tags(tags, self._get_max_files()), self._on_combo_built)

    def _on_combo_built(self, result):
        style_text, lexicon_text, combo_tags, combo_name, save_path = result
        combo_text = f'组合包名称：{combo_name}\n标签：\n{tags_to_tree_text(combo_tags)}\n保存路径：{save_path}\n\n{style_text}\n\n{lexicon_text}'
        self._set_text(self.combo_box, combo_text)
        self.asset_paths['Combo'].set(save_path)
        self._set_text(self.style_box, style_text)
        self._set_text(self.lexicon_box, lexicon_text)
        self._set_text(self.corpus_output, combo_text)
        self.use_combo.set(True)
        self.on_toggle_combo()
        if self.current_session:
            self.current_session = self.service.update_session(
                self.current_session,
                combo_text=combo_text,
                combo_path=save_path,
                style_dna=style_text,
                lexicon_text=lexicon_text,
                combo_tags_json=json.dumps(combo_tags, ensure_ascii=False),
                combo_name=combo_name,
                use_combo=True,
            )

    def import_combo_package(self):
        path = filedialog.askopenfilename(title='选择组合包', initialdir=self.asset_paths['Combo'].get() or os.path.expanduser('~'), filetypes=[('JSON 组合包', '*.json'), ('所有文件', '*.*')])
        if not path:
            return
        try:
            data = self.service.load_combo_package(path)
        except Exception as e:
            messagebox.showerror('导入失败', str(e))
            return
        self.asset_paths['Combo'].set(path)
        self._set_text(self.combo_box, data['combo_text'])
        self._set_text(self.style_box, data['style_dna'])
        self._set_text(self.lexicon_box, data['lexicon'])
        self.selected_tags = normalize_tags(data['combo_tags'])
        self.refresh_selected_tags()
        self.use_combo.set(True)
        self.on_toggle_combo()
        if self.current_session:
            self.current_session = self.service.update_session(self.current_session, combo_text=data['combo_text'], combo_path=path, style_dna=data['style_dna'], lexicon_text=data['lexicon'], combo_tags_json=json.dumps(data['combo_tags'], ensure_ascii=False), combo_name=data['combo_name'], use_combo=True)
        self._set_text(self.corpus_output, data['combo_text'])

    def populate_tag_tree(self):
        self.tag_tree.delete(*self.tag_tree.get_children())
        flt = self.tag_filter_var.get().strip().lower()
        for category, children in self.service.tag_tree().items():
            parent = self.tag_tree.insert('', 'end', text=category, open=True, values=('category',))
            for tag in children:
                if flt and flt not in tag.lower() and flt not in category.lower():
                    continue
                self.tag_tree.insert(parent, 'end', text=tag, values=('tag',))

    def reset_tag_filter(self):
        self.tag_filter_var.set('')
        self.populate_tag_tree()

    def on_tag_tree_double_click(self, event=None):
        item = self.tag_tree.focus()
        if not item:
            return
        parent = self.tag_tree.parent(item)
        if not parent:
            return
        tag = self.tag_tree.item(item, 'text')
        self.add_selected_tag(tag)

    def add_selected_tag(self, tag: str):
        tags = normalize_tags(self.selected_tags + [tag])
        self.selected_tags = tags
        self.refresh_selected_tags()

    def remove_selected_tag(self):
        sel = self.selected_list.curselection()
        if not sel:
            return
        idx = sel[0]
        self.selected_tags.pop(idx)
        self.refresh_selected_tags()

    def clear_selected_tags(self):
        self.selected_tags = []
        self.refresh_selected_tags()

    def load_combo_from_session(self, silent: bool = False):
        if not self.current_session:
            return
        try:
            combo_tags = json.loads(self.current_session.combo_tags_json or '[]')
        except Exception:
            combo_tags = []
        self.selected_tags = normalize_tags(combo_tags)
        self.refresh_selected_tags()
        if self.selected_tags and not silent:
            self.set_progress('已载入会话中的标签组合', False)

    def refresh_selected_tags(self):
        self.selected_list.delete(0, 'end')
        for tag in self.selected_tags:
            self.selected_list.insert('end', f'[{tag_category(tag)}] {tag}')

    def _get_selected_tags(self) -> List[str]:
        return normalize_tags(self.selected_tags)

    def export_history(self):
        if not self.current_session:
            return
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json'), ('所有文件', '*.*')])
        if path:
            backend.export_session_json(self.service.conn, self.current_session, path)
            self.set_progress('历史已导出', False)

    def load_text_into(self, widget):
        path = filedialog.askopenfilename(filetypes=[('文本', '*.txt *.md *.text'), ('所有文件', '*.*')])
        if path:
            self._set_text(widget, self.service.load_text(path))

    def save_text_from(self, widget):
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('文本', '*.txt'), ('所有文件', '*.*')])
        if path:
            self.service.save_text(path, self._get_text(widget))

    def load_into_selected_asset(self):
        idx = self.asset_notebook.index(self.asset_notebook.select())
        self.load_asset_from_file(ASSET_TITLES[idx])

    def save_model_choices(self, silent: bool = False):
        payload = {task: var.get() for task, var in self.task_model_vars.items()}
        self.service.set_task_models(payload)
        self.ui = load_ui_settings()
        self.refresh_model_info_panel()
        if not silent:
            self.set_progress('模型选择已保存', False)

    def show_model_info(self, task: str):
        model = self.task_model_vars[task].get()
        text = self.service.model_info_text(model)
        old = self._get_text(self.model_info_text)
        self._set_text(self.model_info_text, f'{old}\n\n【{TASK_LABELS[task]}】\n{text}'.strip())

    def refresh_model_info_panel(self):
        lines = ['当前任务模型：']
        for task in TASK_LABELS:
            model = self.task_model_vars[task].get()
            lines.append(f'【{TASK_LABELS[task]}】{self.service.model_info_text(model)}')
        self._set_text(self.model_info_text, '\n\n'.join(lines))

    def _get_max_files(self) -> int:
        try:
            return min(200, max(1, int(self.max_files_var.get().strip() or '200')))
        except Exception:
            return 200

    def _append_output(self, text: str):
        old = self._get_text(self.corpus_output)
        self._set_text(self.corpus_output, old + text)

    @staticmethod
    def _get_text(widget) -> str:
        return widget.get('1.0', 'end').rstrip()

    @staticmethod
    def _set_text(widget, text: str):
        widget.delete('1.0', 'end')
        if text:
            widget.insert('1.0', text)

    def on_close(self):
        try:
            self.save_assets(refresh=False)
            self.save_draft_state()
            self.save_model_choices(silent=True)
            save_ui_settings({
                'window_width': self.winfo_width(),
                'window_height': self.winfo_height(),
                'max_files': self._get_max_files(),
                'corpus_dir_default': self.corpus_dir_var.get(),
                'default_combo_path': self.asset_paths['Combo'].get(),
                'default_bible_path': self.asset_paths['Bible'].get(),
                'default_recap_path': self.asset_paths['Recap'].get(),
            })
        except Exception:
            pass
        self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == '__main__':
    main()
