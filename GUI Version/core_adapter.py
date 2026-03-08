from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent
APP_DIR = Path.home() / '.novel_studio_gui'
APP_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_TRAIN_DIR = str(APP_DIR / 'train_corpus')
Path(DEFAULT_TRAIN_DIR).mkdir(parents=True, exist_ok=True)
UI_SETTINGS_PATH = str(APP_DIR / 'ui_settings.json')

# ---------------------------
# MODEL CATALOG
# ---------------------------
MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    'gpt-5.4': {'label': 'GPT-5.4', 'context_window': 1_000_000, 'tier1_tpm': 500_000},
    'gpt-5': {'label': 'GPT-5', 'context_window': 400_000, 'tier1_tpm': 500_000},
    'gpt-5-mini': {'label': 'GPT-5 mini', 'context_window': 400_000, 'tier1_tpm': 500_000},
    'gpt-5-nano': {'label': 'GPT-5 nano', 'context_window': 400_000, 'tier1_tpm': 200_000},
    'gpt-5-chat-latest': {'label': 'GPT-5 Chat', 'context_window': 128_000, 'tier1_tpm': 30_000},
    'gpt-5.4-pro': {'label': 'GPT-5.4 Pro', 'context_window': 1_000_000, 'tier1_tpm': 30_000},
}

TASK_MODEL_DEFAULTS = {
    'chat': 'gpt-5-mini',
    'draft': 'gpt-5.4',
    'review': 'gpt-5-mini',
    'revise': 'gpt-5.4',
    'analysis': 'gpt-5-nano',
}

# ---------------------------
# UI SETTINGS
# ---------------------------
def load_ui_settings() -> Dict[str, Any]:
    default = {
        'font_size': 14,
        'font_family': 'Microsoft YaHei UI',
        'text_border_width': 1,
        'window_width': 1800,
        'window_height': 1100,
        'pane_history_width': 900,
        'pane_right_width': 800,
        'max_files': 200,
        'corpus_dir_default': DEFAULT_TRAIN_DIR,
        'default_combo_path': '',
        'default_bible_path': '',
        'default_recap_path': '',
        'task_models': TASK_MODEL_DEFAULTS,
        'custom_tag_tree': {},
    }
    if not os.path.exists(UI_SETTINGS_PATH):
        return default
    try:
        with open(UI_SETTINGS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        default.update(data)
    except Exception:
        pass
    return default


def save_ui_settings(data: Dict[str, Any]):
    payload = load_ui_settings()
    payload.update(data)
    with open(UI_SETTINGS_PATH, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def merge_tag_trees(base: Dict[str, Dict[str, List[str]]], extra: Dict[str, Dict[str, List[str]]] | None) -> Dict[str, Dict[str, List[str]]]:
    merged = {cat: {tag: list(vals) for tag, vals in children.items()} for cat, children in base.items()}
    for cat, children in (extra or {}).items():
        slot = merged.setdefault(cat, {})
        for tag, synonyms in (children or {}).items():
            cur = slot.setdefault(tag, [])
            for s in [tag] + list(synonyms or []):
                if s and s not in cur:
                    cur.append(s)
    return merged

# ---------------------------
# TAG SYSTEM
# ---------------------------
BASE_TAG_TREE: Dict[str, Dict[str, List[str]]] = {
    '背景': {
        '历史': ['历史', '史向', '史实'], '古风': ['古风', '古代', '古言', '中式古代'], '架空古代': ['架空古代', '架空', '古代架空'],
        '现代': ['现代', '都市', '当代'], '校园': ['校园', '学校', '学园', '学院'], '奇幻': ['奇幻', '幻想', '异世界'], '武侠': ['武侠', '江湖'],
        '宫廷': ['宫廷', '后宫', '深宫'], '牢狱': ['牢狱', '牢房', '狱中', '监牢', '囚室'], '军旅': ['军旅', '军营', '军中', '营帐'],
    },
    '题材': {
        '日常': ['日常', '生活流'], '调教': ['调教', '驯服', '训诫'], '拷问': ['拷问', '刑讯', '上刑', '用刑'],
        '审讯': ['审讯', '审问', '讯问', '逼供', '盘问', '过堂'], '羞辱': ['羞辱', '耻辱', '难堪'], '囚禁': ['囚禁', '关押', '拘押', '羁押', '收监'],
        '搜身': ['搜身', '查身', '搜检', '验身', '身体检查'], '惩罚': ['惩罚', '责罚', '处罚'], '游戏': ['游戏', '玩闹', '恶作剧'], '制服': ['制服', '制伏', '压服'],
    },
    '内容': {
        '挠痒': ['挠痒', '挠痒痒', '呵痒', '胳肢', '痒刑', 'くすぐり', 'tickling'], '失禁': ['失禁', '尿失禁', '尿意失控'],
        '精神崩溃': ['精神崩溃', '崩溃', '心防崩塌'], '求饶': ['求饶', '讨饶', '饶了我', '求放过'], '昏迷': ['昏迷', '失去意识', '晕厥', '昏过去'],
        '服从': ['服从', '顺从', '听命'], '反抗': ['反抗', '挣扎', '抵抗'], '屈服': ['屈服', '低头', '认输'], '忍耐': ['忍耐', '强忍', '硬忍', '忍住'],
        '破防': ['破防', '失守', '绷不住', '撑不住'], '哭泣': ['哭泣', '哭', '落泪', '呜咽'],
    },
    '人物': {
        '单女主': ['单女主', '女主', '单一女主'], '单男主': ['单男主', '男主', '单一男主'], '多女主': ['多女主', '双女主'], '多男主': ['多男主'],
        '群像': ['群像', '多角色'], '主从关系': ['主从关系', '支配', '臣服'], '敌对关系': ['敌对关系', '对立'], '审讯者与囚犯': ['审讯者与囚犯', '主审与囚犯', '看守与囚犯'],
    },
    '部位': {
        '腋下': ['腋下', '胳肢窝', '腋窝'], '脚底': ['脚底', '足底', '足心', '袜底'], '腰': ['腰', '腰侧', '侧腰', '腰肢', '腰间'],
        '脖子': ['脖子', '颈侧', '后颈', '脖颈'], '膝弯': ['膝弯', '膝后', '腿弯'], '全身': ['全身'],
    },
}



def load_custom_tag_tree() -> Dict[str, Dict[str, List[str]]]:
    data = load_ui_settings().get('custom_tag_tree', {}) or {}
    out: Dict[str, Dict[str, List[str]]] = {}
    if not isinstance(data, dict):
        return out
    for cat, children in data.items():
        if not isinstance(children, dict):
            continue
        out[cat] = {}
        for tag, synonyms in children.items():
            out[cat][str(tag)] = [str(x) for x in synonyms] if isinstance(synonyms, list) else []
    return out


def save_custom_tag_tree(tree: Dict[str, Dict[str, List[str]]]):
    save_ui_settings({'custom_tag_tree': tree})


def current_tag_tree() -> Dict[str, Dict[str, List[str]]]:
    return merge_tag_trees(BASE_TAG_TREE, load_custom_tag_tree())


def refresh_tag_runtime() -> None:
    global TAG_TREE, TAG_LOOKUP, TAG_SYNONYMS, CANONICAL_TAGS, TAG_DISPLAY
    TAG_TREE = current_tag_tree()
    TAG_LOOKUP, TAG_SYNONYMS, CANONICAL_TAGS = _build_tag_lookup()
    TAG_DISPLAY = {tag: tag for tag in CANONICAL_TAGS}


TAG_TREE: Dict[str, Dict[str, List[str]]] = current_tag_tree()

def _build_tag_lookup() -> Tuple[Dict[str, Tuple[str, str]], Dict[str, List[str]], List[str]]:
    lookup: Dict[str, Tuple[str, str]] = {}
    flat: Dict[str, List[str]] = {}
    canonical: List[str] = []
    for cat, children in TAG_TREE.items():
        for tag, synonyms in children.items():
            canonical.append(tag)
            flat[tag] = list(dict.fromkeys([tag] + synonyms))
            for token in flat[tag]:
                lookup[token.strip().lower()] = (cat, tag)
    return lookup, flat, canonical


TAG_LOOKUP, TAG_SYNONYMS, CANONICAL_TAGS = _build_tag_lookup()
TAG_DISPLAY = {tag: tag for tag in CANONICAL_TAGS}


def canonicalize_tag(tag: str) -> str:
    raw = (tag or '').strip()
    if not raw:
        return ''
    return TAG_LOOKUP.get(raw.lower(), ('', raw))[1]


def normalize_tags(tags: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in tags:
        canon = canonicalize_tag(item)
        if not canon or canon in seen:
            continue
        seen.add(canon)
        out.append(canon)
    return out


def display_tag(tag: str) -> str:
    return TAG_DISPLAY.get(tag, tag)


def tag_category(tag: str) -> str:
    canon = canonicalize_tag(tag)
    for cat, children in TAG_TREE.items():
        if canon in children:
            return cat
    return '未分类'


def infer_controlled_tags(text: str) -> List[str]:
    lower = (text or '').lower()
    scored: List[Tuple[int, str]] = []
    for canon, tokens in TAG_SYNONYMS.items():
        score = 0
        for token in tokens:
            tok = token.strip().lower()
            if tok and tok in lower:
                score += max(1, len(tok))
        if score:
            scored.append((score, canon))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [canon for _, canon in scored[:24]]


def tags_to_tree_text(tags: Iterable[str]) -> str:
    grouped: Dict[str, List[str]] = {}
    for t in normalize_tags(tags):
        grouped.setdefault(tag_category(t), []).append(t)
    lines: List[str] = []
    for cat in TAG_TREE:
        vals = grouped.get(cat, [])
        if not vals:
            continue
        lines.append(f'【{cat}】')
        lines.extend(f'- {v}' for v in vals)
    return '\n'.join(lines)

PIXIV_QUERY_MAP: Dict[str, List[str]] = {
    '历史': ['歴史', '時代物'], '古风': ['古風', '中華風', '時代劇'], '架空古代': ['中華風ファンタジー', '架空歴史'], '现代': ['現代'], '校园': ['学園', '学校'],
    '奇幻': ['ファンタジー'], '武侠': ['武侠', '江湖'], '宫廷': ['宮廷'], '牢狱': ['牢獄', '監獄'], '调教': ['調教'], '拷问': ['拷問'], '审讯': ['尋問'],
    '囚禁': ['監禁'], '羞辱': ['羞辱'], '搜身': ['身体検査'], '惩罚': ['お仕置き'], '挠痒': ['くすぐり', 'tickling'], '失禁': ['失禁'], '精神崩溃': ['精神崩壊'],
    '求饶': ['命乞い'], '昏迷': ['気絶'], '服从': ['服従'], '反抗': ['抵抗'], '屈服': ['屈服'], '忍耐': ['我慢'], '破防': ['限界'], '哭泣': ['泣き顔', '泣く'],
    '单女主': ['女主人公'], '单男主': ['男主人公'], '群像': ['群像劇'], '主从关系': ['主従'], '敌对关系': ['対立'], '审讯者与囚犯': ['尋問官', '囚人'],
    '腋下': ['脇', '脇の下'], '脚底': ['足裏'], '腰': ['腰', '脇腹'], '脖子': ['首筋'], '膝弯': ['膝裏'],
}


def estimate_tokens(text: str) -> int:
    text = text or ''
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    non_ascii = len(text) - ascii_chars
    return max(1, ascii_chars // 4 + non_ascii)


def model_input_limit(model: str) -> int:
    info = MODEL_CATALOG.get(model, {})
    context_window = int(info.get('context_window', 128000))
    tpm = int(info.get('tier1_tpm', context_window))
    return max(4000, min(context_window, tpm))


def trim_text_to_token_limit(text: str, limit: int) -> str:
    if estimate_tokens(text) <= limit:
        return text
    if limit <= 32:
        return text[: max(80, limit)]
    head_chars = max(200, int(len(text) * 0.45))
    tail_chars = max(200, int(len(text) * 0.45))
    head = text[:head_chars]
    tail = text[-tail_chars:]
    merged = head + '\n\n【中间内容已按模型输入上限自动省略】\n\n' + tail
    while estimate_tokens(merged) > limit and (head_chars > 120 or tail_chars > 120):
        head_chars = max(120, int(head_chars * 0.9))
        tail_chars = max(120, int(tail_chars * 0.9))
        head = text[:head_chars]
        tail = text[-tail_chars:]
        merged = head + '\n\n【中间内容已按模型输入上限自动省略】\n\n' + tail
    return merged

def trim_messages_to_limit(messages: List[Dict[str, str]], model: str) -> List[Dict[str, str]]:
    limit = model_input_limit(model)
    current: List[Dict[str, str]] = []
    total = 0
    # keep system first, then newest messages
    system = messages[:1] if messages and messages[0].get('role') == 'system' else []
    rest = messages[1:] if system else messages[:]
    if system:
        sys_content = trim_text_to_token_limit(system[0].get('content', ''), max(1200, limit // 3))
        current.append({'role': 'system', 'content': sys_content})
        total += estimate_tokens(sys_content)
    for msg in reversed(rest):
        content = msg.get('content', '')
        room = max(600, limit - total)
        if room <= 0:
            break
        content = trim_text_to_token_limit(content, room)
        msg_tokens = estimate_tokens(content)
        if total + msg_tokens > limit and current:
            continue
        current.append({'role': msg.get('role', 'user'), 'content': content})
        total += msg_tokens
    if system:
        kept = [current[0]] + list(reversed(current[1:]))
    else:
        kept = list(reversed(current))
    return kept


def available_models() -> List[str]:
    return list(MODEL_CATALOG.keys())


def pixiv_expand_queries(tags: Iterable[str]) -> List[str]:
    queries: List[str] = []
    for tag in normalize_tags(tags):
        queries.append(tag)
        queries.extend(PIXIV_QUERY_MAP.get(tag, []))
    return list(dict.fromkeys([q for q in queries if q]))


def guess_tag_category(tag: str, selected_tags: Iterable[str] | None = None) -> str:
    refresh_tag_runtime()
    canon = canonicalize_tag(tag)
    if canon in CANONICAL_TAGS:
        return tag_category(canon)
    raw = (tag or '').strip()
    if not raw:
        return '内容'
    selected_categories = [tag_category(t) for t in normalize_tags(selected_tags or []) if tag_category(t) != '未分类']
    preferred = selected_categories[0] if len(set(selected_categories)) == 1 else ''
    hints = {
        '背景': ['历史', '古', '现代', '校园', '学院', '宫廷', '江湖', '牢', '狱', '军'],
        '题材': ['审', '讯', '刑', '拷', '囚', '禁', '搜', '罚', '辱', '调'],
        '内容': ['求饶', '崩溃', '服从', '失禁', '昏', '哭', '笑', '忍', '破防', '反抗', '屈服', '挠'],
        '人物': ['女主', '男主', '群像', '主从', '敌对', '囚犯', '审讯者'],
        '部位': ['腋', '腰', '脚', '足', '膝', '脖', '颈', '全身'],
    }
    for cat, words in hints.items():
        if any(w in raw for w in words):
            return cat
    return preferred or '内容'


def fetch_pixiv_tag_suggestions(seed_tags: Iterable[str], max_terms: int = 60) -> Dict[str, Any]:
    try:
        import re
        import urllib.parse
        import urllib.request
    except Exception:
        return {'matched': [], 'suggestions': [], 'sources': []}
    refresh_tag_runtime()
    known = set(CANONICAL_TAGS)
    matched: Dict[str, int] = {}
    unknown: Dict[str, Dict[str, Any]] = {}
    seen_urls: List[str] = []
    for query in pixiv_expand_queries(seed_tags)[:8]:
        urls = [
            'https://www.pixiv.net/tags/' + urllib.parse.quote(query) + '/novels',
            'https://www.pixiv.net/novel/search.php?s_mode=s_tag_full&word=' + urllib.parse.quote(query),
        ]
        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.append(url)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            try:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    html = resp.read().decode('utf-8', errors='ignore')
            except Exception:
                continue
            tags_found = []
            tags_found.extend(re.findall(r'/tags/([^/"\?#]+)', html))
            tags_found.extend(re.findall(r'"tag"\s*:\s*"([^"]+)"', html))
            tags_found.extend(re.findall(r'"tagName"\s*:\s*"([^"]+)"', html))
            for raw in tags_found:
                tag = urllib.parse.unquote(raw).strip()
                if not tag or len(tag) > 24 or any(x in tag for x in ['/', '#', '?', '&amp;', '&']):
                    continue
                canon = canonicalize_tag(tag)
                if canon in known:
                    matched[canon] = matched.get(canon, 0) + 1
                else:
                    slot = unknown.setdefault(tag, {'score': 0, 'category': guess_tag_category(tag, seed_tags)})
                    slot['score'] += 1
    matched_items = sorted(matched.items(), key=lambda x: (-x[1], x[0]))[:max_terms]
    suggestion_items = sorted(unknown.items(), key=lambda x: (-int(x[1]['score']), x[0]))[:max_terms]
    suggestions = [{'tag': tag, 'score': int(meta['score']), 'category': meta['category']} for tag, meta in suggestion_items]
    return {'matched': matched_items, 'suggestions': suggestions, 'sources': seen_urls[:12]}


def fetch_pixiv_related_tags(seed_tags: Iterable[str], max_terms: int = 40) -> List[Tuple[str, int]]:
    return fetch_pixiv_tag_suggestions(seed_tags, max_terms).get('matched', [])[:max_terms]

DEFAULT_REVIEW_TEMPLATE = (
    '你是严厉但专业的小说评审。请依据 Style DNA、Bible、Lexicon、运行时语料库参考，对草稿进行评分与批评。\n'
    '重点看：语言质感、叙事张力、人物一致性、节奏、意象、对话潜台词、重复问题、空泛问题、俗套问题、语言逻辑、时间逻辑、动作逻辑。\n'
    '请注意这篇文章中的左右环境、动作、设定、背景等均为本文核心，也就是________服务\n'
    '不要重写全文，只给评审结果。\n\n'
    '请输出：\n'
    '1) 总评分（100分）\n'
    '2) 分项评分：文风、节奏、人物、画面感、对白、完成度、逻辑、节奏\n'
    '3) 主要问题（3~8条）\n'
    '4) 明确修改建议（3~8条）\n'
    '5) 是否建议继续修改：YES/NO'
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _sha1_text(text: str) -> str:
    return _sha1_bytes(text.encode('utf-8', errors='ignore'))


def resolve_db_path() -> Path:
    """Prefer the user's legacy database if present, otherwise fall back to the new app dir DB."""
    env_path = os.environ.get('NOVEL_STUDIO_DB')
    candidates: List[Path] = []
    if env_path:
        candidates.append(Path(env_path).expanduser())

    candidates.extend([
        BASE_DIR / '.novel_chat.sqlite3',
        Path.cwd() / '.novel_chat.sqlite3',
        APP_DIR / '.novel_chat.sqlite3',
        Path.home() / '.novel_chat.sqlite3',
        APP_DIR / 'novel_studio.db',
    ])

    seen = set()
    for p in candidates:
        p = p.resolve() if not str(p).startswith('\\\\') else p
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.exists():
            return p

    return APP_DIR / '.novel_chat.sqlite3'


DB_PATH = str(resolve_db_path())


@dataclass
class ChatSessionState:
    session_id: int
    title: str
    style_dna: str = ''
    lexicon_text: str = ''
    bible: str = ''
    recap: str = ''
    use_style: bool = False
    use_lexicon: bool = False
    use_bible: bool = False
    use_recap: bool = False
    use_runtime_corpus: bool = False
    use_combo: bool = False
    combo_text: str = ''
    combo_path: str = ''
    combo_tags_json: str = ''
    combo_name: str = ''
    previous_response_id: str = ''
    bible_path: str = ''
    recap_path: str = ''
    created_at: str = ''
    updated_at: str = ''


@dataclass
class SessionRow:
    id: int
    title: str
    updated_at: str


class ProgressProxy:
    def __init__(self, callback: Optional[Callable[[str, bool], None]] = None):
        self.callback = callback

    def start(self, text: str):
        if self.callback:
            self.callback(text, True)

    def update(self, text: str):
        if self.callback:
            self.callback(text, True)

    def done(self, text: str = 'Ready'):
        if self.callback:
            self.callback(text, False)


class LLMClient:
    def __init__(self):
        self.api_key = os.environ.get('OPENAI_API_KEY_TICKLE') or os.environ.get('OPENAI_API_KEY')
        self._client = None
        if self.api_key:
            try:
                from openai import OpenAI  # type: ignore
                self._client = OpenAI(api_key=self.api_key)
            except Exception:
                self._client = None

    def available(self) -> bool:
        return self._client is not None

    def _extract_response_text(self, resp: Any) -> str:
        text = (getattr(resp, 'output_text', '') or '').strip()
        if text:
            return text
        output = getattr(resp, 'output', None) or []
        chunks: List[str] = []
        for item in output:
            item_type = getattr(item, 'type', '') or (item.get('type', '') if isinstance(item, dict) else '')
            if item_type != 'message':
                continue
            content = getattr(item, 'content', None) or (item.get('content', []) if isinstance(item, dict) else [])
            for part in content or []:
                part_type = getattr(part, 'type', '') or (part.get('type', '') if isinstance(part, dict) else '')
                if part_type not in ('output_text', 'text'):
                    continue
                value = getattr(part, 'text', '') or (part.get('text', '') if isinstance(part, dict) else '')
                if value:
                    chunks.append(str(value))
        return '\n'.join(x.strip() for x in chunks if str(x).strip()).strip()

    def generate(self, messages: List[Dict[str, str]], model: str = 'gpt-5') -> str:
        messages = trim_messages_to_limit(messages, model)
        if not self._client:
            prompt_preview = '\n\n'.join(f"[{m['role']}]\n{m['content'][:1200]}" for m in messages)
            return (
                '【离线占位输出】\n'
                '当前没有可用的 OpenAI 客户端或 API Key。\n\n'
                '请设置环境变量 OPENAI_API_KEY 或 OPENAI_API_KEY_TICKLE 后重试。\n\n'
                '本次输入摘要：\n' + prompt_preview
            )
        try:
            resp = self._client.responses.create(model=model, input=messages)
            text = self._extract_response_text(resp)
            if text:
                return text
            return '【模型返回为空】\n本次请求已完成，但响应中没有可显示的文本输出。请重试一次，或切换评审模型后再试。'
        except Exception as e:
            return f'【模型调用失败】\n{e}'


class LocalCorpus:
    TEXT_EXTS = {'.txt', '.md', '.markdown', '.text'}

    @staticmethod
    def read_text(path: str) -> str:
        for enc in ('utf-8', 'utf-8-sig', 'gb18030', 'latin-1'):
            try:
                with open(path, 'r', encoding=enc) as f:
                    return f.read()
            except Exception:
                continue
        raise UnicodeDecodeError('unknown', b'', 0, 1, f'Cannot decode {path}')


def summarize_text_block(text: str, max_chars: int = 6000) -> str:
    text = (text or '').strip()
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return head + '\n\n...[截断]...\n\n' + tail


class BackendService:
    def __init__(self):
        self.db_path_obj = Path(DB_PATH)
        self.db_path_obj.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path_obj), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.client = LLMClient()
        self._ensure_schema()
        self._refresh_schema_flags()

    @property
    def db_path(self) -> str:
        return str(self.db_path_obj)

    def _table_exists(self, name: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        return row is not None

    def _columns(self, table: str) -> List[str]:
        if not self._table_exists(table):
            return []
        rows = self.conn.execute(f'PRAGMA table_info({table})').fetchall()
        return [r['name'] for r in rows]

    def _ensure_column(self, table: str, column_sql: str):
        col_name = column_sql.split()[0]
        if col_name not in self._columns(table):
            self.conn.execute(f'ALTER TABLE {table} ADD COLUMN {column_sql}')

    def _refresh_schema_flags(self):
        self.sessions_cols = set(self._columns('sessions'))
        self.turns_cols = set(self._columns('turns'))
        self.draft_cols = set(self._columns('draft_states'))
        self.corpus_cols = set(self._columns('corpus_files'))
        self.analysis_cols = set(self._columns('file_analyses'))
        self._legacy_corpus = 'name' not in self.corpus_cols or 'snippet' not in self.corpus_cols

    def get_task_models(self) -> Dict[str, str]:
        settings = load_ui_settings()
        data = dict(TASK_MODEL_DEFAULTS)
        data.update(settings.get('task_models', {}) or {})
        return data

    def get_task_model(self, task_name: str) -> str:
        return self.get_task_models().get(task_name, TASK_MODEL_DEFAULTS.get(task_name, 'gpt-5-mini'))

    def set_task_models(self, task_models: Dict[str, str]):
        clean = dict(TASK_MODEL_DEFAULTS)
        for k, v in (task_models or {}).items():
            if v:
                clean[k] = v
        save_ui_settings({'task_models': clean})

    def model_info_text(self, model: str) -> str:
        info = MODEL_CATALOG.get(model, {})
        if not info:
            limit = model_input_limit(model)
            return f'{model}：按默认上限 {limit} token 处理。'
        limit = model_input_limit(model)
        return f"{info['label']}：上下文 {info['context_window']:,}，Tier1 TPM {info['tier1_tpm']:,}，本软件采用较小值 {limit:,} 作为单次输入上限。"

    def _ensure_schema(self):
        with self.conn:
            self.conn.executescript(
                '''
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS sessions (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  previous_response_id TEXT,
                  bible TEXT DEFAULT '',
                  recap TEXT DEFAULT '',
                  use_bible INTEGER DEFAULT 0,
                  use_recap INTEGER DEFAULT 0,
                  style_dna TEXT DEFAULT '',
                  use_style INTEGER DEFAULT 0,
                  lexicon_text TEXT DEFAULT '',
                  use_lexicon INTEGER DEFAULT 0,
                  combo_tags_json TEXT DEFAULT '[]',
                  combo_name TEXT DEFAULT '',
                  use_runtime_corpus INTEGER DEFAULT 0,
                  use_combo INTEGER DEFAULT 0,
                  combo_text TEXT DEFAULT '',
                  combo_path TEXT DEFAULT '',
                  bible_path TEXT DEFAULT '',
                  recap_path TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS turns (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  session_id INTEGER NOT NULL,
                  role TEXT NOT NULL,
                  content TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  response_id TEXT,
                  meta_json TEXT,
                  FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS draft_states (
                  session_id INTEGER PRIMARY KEY,
                  task_text TEXT DEFAULT '',
                  draft_text TEXT DEFAULT '',
                  review_text TEXT DEFAULT '',
                  extra_text TEXT DEFAULT '',
                  review_prompt TEXT DEFAULT '',
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS corpus_files (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  path TEXT NOT NULL UNIQUE,
                  mtime INTEGER NOT NULL DEFAULT 0,
                  size INTEGER NOT NULL DEFAULT 0,
                  sha1 TEXT NOT NULL DEFAULT '',
                  tags_json TEXT NOT NULL DEFAULT '[]',
                  created_at TEXT NOT NULL DEFAULT '',
                  updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS file_analyses (
                  file_path TEXT PRIMARY KEY,
                  file_sha1 TEXT NOT NULL,
                  auto_tags_json TEXT NOT NULL DEFAULT '[]',
                  single_style_dna TEXT DEFAULT '',
                  single_lexicon TEXT DEFAULT '',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                '''
            )

            # Upgrade/compat columns for sessions.
            self._ensure_column('sessions', "previous_response_id TEXT DEFAULT ''")
            self._ensure_column('sessions', "bible TEXT DEFAULT ''")
            self._ensure_column('sessions', "recap TEXT DEFAULT ''")
            self._ensure_column('sessions', 'use_bible INTEGER DEFAULT 0')
            self._ensure_column('sessions', 'use_recap INTEGER DEFAULT 0')
            self._ensure_column('sessions', "style_dna TEXT DEFAULT ''")
            self._ensure_column('sessions', 'use_style INTEGER DEFAULT 0')
            self._ensure_column('sessions', "lexicon_text TEXT DEFAULT ''")
            self._ensure_column('sessions', 'use_lexicon INTEGER DEFAULT 0')
            self._ensure_column('sessions', "combo_tags_json TEXT DEFAULT '[]'")
            self._ensure_column('sessions', "combo_name TEXT DEFAULT ''")
            self._ensure_column('sessions', 'use_runtime_corpus INTEGER DEFAULT 0')
            self._ensure_column('sessions', 'use_combo INTEGER DEFAULT 0')
            self._ensure_column('sessions', "combo_text TEXT DEFAULT ''")
            self._ensure_column('sessions', "combo_path TEXT DEFAULT ''")
            self._ensure_column('sessions', "bible_path TEXT DEFAULT ''")
            self._ensure_column('sessions', "recap_path TEXT DEFAULT ''")

            self._ensure_column('turns', "response_id TEXT DEFAULT ''")
            self._ensure_column('turns', "meta_json TEXT DEFAULT ''")

            self._ensure_column('draft_states', "task_text TEXT DEFAULT ''")
            self._ensure_column('draft_states', "draft_text TEXT DEFAULT ''")
            self._ensure_column('draft_states', "review_text TEXT DEFAULT ''")
            self._ensure_column('draft_states', "extra_text TEXT DEFAULT ''")
            self._ensure_column('draft_states', "review_prompt TEXT DEFAULT ''")
            self._ensure_column('draft_states', "updated_at TEXT DEFAULT ''")

        if not self.list_sessions():
            self.create_session('New Session')

    def _row_to_state(self, row: sqlite3.Row) -> ChatSessionState:
        data = dict(row)
        defaults = {
            'style_dna': '', 'lexicon_text': '', 'bible': '', 'recap': '',
            'use_style': 0, 'use_lexicon': 0, 'use_bible': 0, 'use_recap': 0,
            'use_runtime_corpus': 0, 'use_combo': 0, 'combo_text': '', 'combo_path': '', 'combo_tags_json': '[]', 'combo_name': '',
            'previous_response_id': '', 'created_at': '', 'updated_at': '', 'bible_path': '', 'recap_path': '',
        }
        for k, v in defaults.items():
            data.setdefault(k, v)
        for key in ('use_style', 'use_lexicon', 'use_bible', 'use_recap', 'use_runtime_corpus', 'use_combo'):
            data[key] = bool(data.get(key, 0))
        return ChatSessionState(
            session_id=data['id'],
            title=data['title'],
            style_dna=data['style_dna'],
            lexicon_text=data['lexicon_text'],
            bible=data['bible'],
            recap=data['recap'],
            use_style=data['use_style'],
            use_lexicon=data['use_lexicon'],
            use_bible=data['use_bible'],
            use_recap=data['use_recap'],
            use_runtime_corpus=data['use_runtime_corpus'],
            use_combo=data['use_combo'],
            combo_text=data['combo_text'],
            combo_path=data['combo_path'],
            combo_tags_json=data['combo_tags_json'],
            combo_name=data['combo_name'],
            previous_response_id=data['previous_response_id'],
            bible_path=data['bible_path'],
            recap_path=data['recap_path'],
            created_at=data['created_at'],
            updated_at=data['updated_at'],
        )

    def list_sessions(self) -> List[SessionRow]:
        rows = self.conn.execute('SELECT id, title, updated_at FROM sessions ORDER BY updated_at DESC, id DESC').fetchall()
        return [SessionRow(id=r['id'], title=r['title'], updated_at=r['updated_at']) for r in rows]

    def create_session(self, title: str) -> ChatSessionState:
        ts = now_iso()
        cur = self.conn.execute(
            'INSERT INTO sessions(title, created_at, updated_at) VALUES(?,?,?)',
            (title or 'New Session', ts, ts),
        )
        sid = int(cur.lastrowid)
        self.conn.execute(
            'INSERT OR REPLACE INTO draft_states(session_id, review_prompt, updated_at) VALUES(?,?,?)',
            (sid, DEFAULT_REVIEW_TEMPLATE, ts),
        )
        self.conn.commit()
        return self.load_session(sid)

    def load_session(self, session_id: int) -> ChatSessionState:
        row = self.conn.execute('SELECT * FROM sessions WHERE id=?', (session_id,)).fetchone()
        if row is None:
            raise ValueError(f'Session {session_id} not found')
        self._touch_draft_state(session_id)
        return self._row_to_state(row)

    def update_session(self, s: ChatSessionState, **kwargs) -> ChatSessionState:
        allowed = {
            'title', 'style_dna', 'lexicon_text', 'bible', 'recap', 'use_style', 'use_lexicon',
            'use_bible', 'use_recap', 'use_runtime_corpus', 'use_combo', 'combo_text', 'combo_path', 'combo_tags_json', 'combo_name', 'previous_response_id', 'bible_path', 'recap_path'
        }
        sets = []
        vals: List[Any] = []
        for k, v in kwargs.items():
            if k not in allowed:
                continue
            sets.append(f'{k}=?')
            vals.append(int(v) if isinstance(v, bool) else v)
        if not sets:
            return self.load_session(s.session_id)
        sets.append('updated_at=?')
        vals.append(now_iso())
        vals.append(s.session_id)
        self.conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id=?", tuple(vals))
        self.conn.commit()
        return self.load_session(s.session_id)

    def delete_session(self, session_id: int):
        with self.conn:
            self.conn.execute('DELETE FROM turns WHERE session_id=?', (session_id,))
            self.conn.execute('DELETE FROM draft_states WHERE session_id=?', (session_id,))
            self.conn.execute('DELETE FROM sessions WHERE id=?', (session_id,))
        if not self.list_sessions():
            self.create_session('New Session')

    def rename_session(self, session_id: int, new_title: str):
        s = self.load_session(session_id)
        return self.update_session(s, title=new_title.strip() or s.title)

    def _touch_draft_state(self, session_id: int):
        self.conn.execute(
            '''
            INSERT INTO draft_states(session_id, review_prompt, updated_at)
            VALUES(?,?,?)
            ON CONFLICT(session_id) DO UPDATE SET updated_at=excluded.updated_at
            ''',
            (session_id, DEFAULT_REVIEW_TEMPLATE, now_iso())
        )
        self.conn.commit()

    def get_gui_state(self, session_id: int) -> Dict[str, str]:
        self._touch_draft_state(session_id)
        row = self.conn.execute('SELECT * FROM draft_states WHERE session_id=?', (session_id,)).fetchone()
        if row is None:
            return {
                'review_prompt_template': DEFAULT_REVIEW_TEMPLATE,
                'draft_task': '', 'draft_current': '', 'draft_review': '', 'draft_extra': '', 'last_opened_at': ''
            }
        return {
            'review_prompt_template': row['review_prompt'] or DEFAULT_REVIEW_TEMPLATE,
            'draft_task': row['task_text'] or '',
            'draft_current': row['draft_text'] or '',
            'draft_review': row['review_text'] or '',
            'draft_extra': row['extra_text'] or '',
            'last_opened_at': row['updated_at'] or '',
        }

    def save_gui_state(self, session_id: int, **kwargs):
        mapping = {
            'review_prompt_template': 'review_prompt',
            'draft_task': 'task_text',
            'draft_current': 'draft_text',
            'draft_review': 'review_text',
            'draft_extra': 'extra_text',
        }
        sets = []
        vals: List[Any] = []
        for k, v in kwargs.items():
            col = mapping.get(k)
            if col:
                sets.append(f'{col}=?')
                vals.append(v)
        if not sets:
            return
        self._touch_draft_state(session_id)
        ts = now_iso()
        vals.extend([ts, session_id])
        self.conn.execute(f"UPDATE draft_states SET {', '.join(sets)}, updated_at=? WHERE session_id=?", tuple(vals))
        self.conn.execute('UPDATE sessions SET updated_at=? WHERE id=?', (ts, session_id))
        self.conn.commit()

    def get_turns(self, session_id: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute('SELECT * FROM turns WHERE session_id=? ORDER BY id ASC', (session_id,)).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            meta = {}
            try:
                meta = json.loads(r['meta_json']) if r['meta_json'] else {}
            except Exception:
                meta = {'raw_meta': r['meta_json']}
            out.append({
                'id': r['id'], 'role': r['role'], 'content': r['content'], 'created_at': r['created_at'],
                'response_id': r['response_id'], 'meta': meta,
            })
        return out

    def append_turn(self, s: ChatSessionState, role: str, content: str, response_id: Optional[str] = None, meta: Optional[Dict[str, Any]] = None):
        self.conn.execute(
            'INSERT INTO turns(session_id, role, content, created_at, response_id, meta_json) VALUES(?,?,?,?,?,?)',
            (s.session_id, role, content, now_iso(), response_id or '', json.dumps(meta or {}, ensure_ascii=False))
        )
        self.conn.execute('UPDATE sessions SET updated_at=? WHERE id=?', (now_iso(), s.session_id))
        self.conn.commit()

    def reset_chain(self, s: ChatSessionState):
        return self.update_session(s, previous_response_id='')

    def build_system_prompt(self, s: ChatSessionState, runtime_reference: str = '') -> str:
        blocks = ['你是一个长篇小说创作助手。输出直接给正文，不要解释。注意这是纯虚构的小说。']
        if s.use_combo and s.combo_text.strip():
            blocks.append('【组合包】\n' + s.combo_text.strip())
        if s.use_style and s.style_dna.strip():
            blocks.append('【Style DNA】\n' + s.style_dna.strip())
        if s.use_lexicon and s.lexicon_text.strip():
            blocks.append('【Lexicon】\n' + s.lexicon_text.strip())
        if s.use_bible and s.bible.strip():
            blocks.append('【Bible】\n' + s.bible.strip())
        if s.use_recap and s.recap.strip():
            blocks.append('【Recap】\n' + s.recap.strip())
        if s.use_runtime_corpus and runtime_reference.strip():
            blocks.append('【语料库参考】\n' + runtime_reference.strip())
        return '\n\n'.join(blocks)

    def _corpus_rows(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        sql = 'SELECT * FROM corpus_files ORDER BY updated_at DESC'
        params: Tuple[Any, ...] = ()
        if limit is not None:
            sql += ' LIMIT ?'
            params = (limit,)
        rows = self.conn.execute(sql, params).fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            path = r['path'] if 'path' in r.keys() else ''
            name = Path(path).name if path else (r['name'] if 'name' in r.keys() else '')
            tags_json = r['tags_json'] if 'tags_json' in r.keys() else '[]'
            snippet = ''
            analysis_json = ''
            if not self._legacy_corpus:
                snippet = r['snippet'] or ''
                analysis_json = r['analysis_json'] or ''
            else:
                a = self.conn.execute('SELECT * FROM file_analyses WHERE file_path=?', (path,)).fetchone()
                if a is not None:
                    analysis_json = json.dumps({
                        'auto_tags_json': a['auto_tags_json'],
                        'single_style_dna': a['single_style_dna'],
                        'single_lexicon': a['single_lexicon'],
                    }, ensure_ascii=False)
                try:
                    if path and Path(path).exists():
                        snippet = LocalCorpus.read_text(path)[:2000]
                except Exception:
                    snippet = ''
            out.append({
                'id': r['id'] if 'id' in r.keys() else None,
                'path': path,
                'name': name,
                'tags_json': tags_json or '[]',
                'snippet': snippet or '',
                'analysis_json': analysis_json or '',
                'updated_at': r['updated_at'] if 'updated_at' in r.keys() else '',
            })
        return out

    def build_runtime_reference_bundle(self, max_chars: int = 5000) -> str:
        rows = self._corpus_rows(limit=8)
        if not rows:
            return ''
        parts: List[str] = []
        total = 0
        for r in rows:
            extra = ''
            if self._legacy_corpus and r['analysis_json']:
                try:
                    a = json.loads(r['analysis_json'])
                    extra_bits = []
                    if a.get('single_style_dna'):
                        extra_bits.append('单文件 Style DNA:\n' + summarize_text_block(a['single_style_dna'], 600))
                    if a.get('single_lexicon'):
                        extra_bits.append('单文件 Lexicon:\n' + summarize_text_block(a['single_lexicon'], 600))
                    extra = '\n'.join(extra_bits)
                except Exception:
                    extra = ''
            block = f"文件: {r['name']}\n标签: {r['tags_json']}\n摘录:\n{r['snippet']}\n{extra}\n"
            if total + len(block) > max_chars:
                break
            parts.append(block)
            total += len(block)
        return '\n---\n'.join(parts)

    def build_input(self, text: str, s: ChatSessionState, model: str = 'gpt-5') -> List[Dict[str, str]]:
        runtime_reference = self.build_runtime_reference_bundle() if s.use_runtime_corpus else ''
        messages = [{'role': 'system', 'content': self.build_system_prompt(s, runtime_reference)}]
        recent = self.get_turns(s.session_id)[-10:]
        for t in recent:
            messages.append({'role': t['role'], 'content': t['content']})
        messages.append({'role': 'user', 'content': text})
        return trim_messages_to_limit(messages, model)

    def chat_once(self, s: ChatSessionState, text: str, progress: Optional[ProgressProxy] = None) -> Tuple[ChatSessionState, str]:
        progress = progress or ProgressProxy()
        progress.start('正在生成回复…')
        self.append_turn(s, 'user', text)
        model = self.get_task_model('chat')
        out = self.client.generate(self.build_input(text, s, model), model=model)
        s = self.update_session(s, previous_response_id='')
        self.append_turn(s, 'assistant', out, meta={'model': model, 'offline': not self.client.available()})
        progress.done('回复完成')
        return self.load_session(s.session_id), out

    def build_custom_review_prompt(self, draft: str, s: ChatSessionState, template: str) -> List[Dict[str, str]]:
        runtime_reference = self.build_runtime_reference_bundle(3000) if s.use_runtime_corpus else ''
        sys = '你是小说评审与编辑助手。请严格按用户给出的模板输出。'
        user = '\n\n'.join(x for x in [
            ('【组合包】\n' + s.combo_text.strip()) if s.use_combo and s.combo_text.strip() else '',
            ('【Style DNA】\n' + s.style_dna.strip()) if s.use_style and s.style_dna.strip() else '',
            ('【Bible】\n' + s.bible.strip()) if s.use_bible and s.bible.strip() else '',
            ('【Lexicon】\n' + s.lexicon_text.strip()) if s.use_lexicon and s.lexicon_text.strip() else '',
            ('【语料库参考】\n' + runtime_reference.strip()) if runtime_reference.strip() else '',
            '【待评审草稿】\n' + draft,
            '【评审模板】\n' + template,
        ] if x)
        model = self.get_task_model('review')
        return trim_messages_to_limit([{'role': 'system', 'content': sys}, {'role': 'user', 'content': user}], model)

    def build_custom_revision_prompt(self, original_task: str, draft: str, review: str, extra: str, s: ChatSessionState):
        runtime_reference = self.build_runtime_reference_bundle(4000) if s.use_runtime_corpus else ''
        sys = self.build_system_prompt(s, runtime_reference)
        user = (
            '【原始任务】\n' + (original_task or '') +
            '\n\n【当前草稿】\n' + (draft or '') +
            '\n\n【评审意见】\n' + (review or '') +
            '\n\n【用户额外要求】\n' + (extra or '') +
            '\n\n请综合以上信息，输出新的完整正文。'
        )
        model = self.get_task_model('review')
        return trim_messages_to_limit([{'role': 'system', 'content': sys}, {'role': 'user', 'content': user}], model)

    def draft_generate(self, s: ChatSessionState, task: str, progress: Optional[ProgressProxy] = None) -> str:
        progress = progress or ProgressProxy()
        progress.start('正在生成草稿…')
        model = self.get_task_model('draft')
        out = self.client.generate(self.build_input(task, s, model), model=model)
        out = (out or '').strip()

        self.save_gui_state(
            s.session_id,
            draft_task=task,
            draft_current=out,
        )

        progress.done('草稿生成完成' if out else '草稿生成完成（结果为空）')
        return out

    def draft_review(self, s: ChatSessionState, draft: str, review_template: str, progress: Optional[ProgressProxy] = None) -> str:
        progress = progress or ProgressProxy()
        progress.start('正在评审草稿…')
        model = self.get_task_model('review')
        out = (self.client.generate(self.build_custom_review_prompt(draft, s, review_template), model=model) or '').strip()
        if not out:
            out = '【评审结果为空】\n模型本次没有返回可显示文本。建议重试一次，或切换到 gpt-5.4 / gpt-5 后再评审。'
        self.save_gui_state(s.session_id, review_prompt_template=review_template, draft_current=draft, draft_review=out)
        progress.done('评审完成')
        return out

    def draft_revise(self, s: ChatSessionState, task: str, draft: str, review: str, extra: str, progress: Optional[ProgressProxy] = None) -> str:
        progress = progress or ProgressProxy()
        progress.start('正在改稿…')
        model = self.get_task_model('revise')
        out = self.client.generate(self.build_custom_revision_prompt(task, draft, review, extra, s), model=model)
        self.save_gui_state(s.session_id, draft_task=task, draft_current=out, draft_review=review, draft_extra=extra)
        progress.done('改稿完成')
        return out

    def accept_draft_to_history(self, s: ChatSessionState, final_text: str):
        self.append_turn(s, 'assistant', final_text, meta={'mode': 'draft_review_revise'})

    def corpus_scan(self, folder: str) -> Tuple[int, int]:
        total = 0
        updated = 0
        folder_path = Path(folder)
        if not folder_path.exists():
            return 0, 0
        for p in folder_path.rglob('*'):
            if not p.is_file() or p.suffix.lower() not in LocalCorpus.TEXT_EXTS:
                continue
            total += 1
            try:
                text = LocalCorpus.read_text(str(p))
            except Exception:
                continue
            stat = p.stat()
            sha1 = _sha1_text(text)
            tags = infer_controlled_tags(p.name + '\n' + text[:8000])
            ts = now_iso()
            self.conn.execute(
                '''
                INSERT INTO corpus_files(path, mtime, size, sha1, tags_json, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET
                  mtime=excluded.mtime,
                  size=excluded.size,
                  sha1=excluded.sha1,
                  tags_json=excluded.tags_json,
                  updated_at=excluded.updated_at
                ''',
                (str(p), int(stat.st_mtime), int(stat.st_size), sha1, json.dumps(tags, ensure_ascii=False), ts, ts)
            )
            self.conn.execute(
                '''
                INSERT INTO file_analyses(file_path, file_sha1, auto_tags_json, single_style_dna, single_lexicon, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(file_path) DO UPDATE SET
                  file_sha1=excluded.file_sha1,
                  auto_tags_json=excluded.auto_tags_json,
                  updated_at=excluded.updated_at
                ''',
                (str(p), sha1, json.dumps(tags, ensure_ascii=False), '', '', ts, ts)
            )
            updated += 1
        self.conn.commit()
        return total, updated

    def corpus_infer(self, max_files: Optional[int]):
        rows = self._corpus_rows(limit=max_files or 200)
        for r in rows:
            text = (r['name'] or '') + '\n' + (r['snippet'] or '')
            tags = infer_controlled_tags(text)
            ts = now_iso()
            self.conn.execute('UPDATE corpus_files SET tags_json=?, updated_at=? WHERE path=?', (json.dumps(tags, ensure_ascii=False), ts, r['path']))
            self.conn.execute(
                '''
                INSERT INTO file_analyses(file_path, file_sha1, auto_tags_json, single_style_dna, single_lexicon, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(file_path) DO UPDATE SET auto_tags_json=excluded.auto_tags_json, updated_at=excluded.updated_at
                ''',
                (r['path'], _sha1_text(r['snippet']), json.dumps(tags, ensure_ascii=False), '', '', ts, ts)
            )
        self.conn.commit()
        return len(rows)

    def corpus_analyze(self, max_files: Optional[int]):
        rows = self._corpus_rows(limit=max_files or 200)
        for r in rows:
            snippet = r['snippet'] or ''
            analysis = {
                'chars': len(snippet),
                'paragraphs': len([p for p in snippet.splitlines() if p.strip()]),
                'quote_count': snippet.count('“') + snippet.count('"'),
                'tags_guess': infer_controlled_tags(snippet),
            }
            arow = self.conn.execute('SELECT * FROM file_analyses WHERE file_path=?', (r['path'],)).fetchone()
            style_text = arow['single_style_dna'] if arow else ''
            lexicon_text = arow['single_lexicon'] if arow else ''
            ts = now_iso()
            self.conn.execute(
                '''
                INSERT INTO file_analyses(file_path, file_sha1, auto_tags_json, single_style_dna, single_lexicon, created_at, updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(file_path) DO UPDATE SET
                  file_sha1=excluded.file_sha1,
                  auto_tags_json=excluded.auto_tags_json,
                  single_style_dna=excluded.single_style_dna,
                  single_lexicon=excluded.single_lexicon,
                  updated_at=excluded.updated_at
                ''',
                (r['path'], _sha1_text(snippet), json.dumps(analysis.get('tags_guess', []), ensure_ascii=False), style_text, lexicon_text, ts, ts)
            )
        self.conn.commit()
        return len(rows)

    def corpus_tag_counts(self) -> List[Tuple[str, int]]:
        counts: Dict[str, int] = {}
        rows = self.conn.execute('SELECT tags_json FROM corpus_files').fetchall()
        for r in rows:
            try:
                tags = json.loads(r['tags_json'] or '[]')
            except Exception:
                tags = []
            for t in tags:
                counts[t] = counts.get(t, 0) + 1
        return sorted(counts.items(), key=lambda x: (-x[1], x[0]))

    def refresh_recap_from_path(self, s: ChatSessionState) -> ChatSessionState:
        recap_path = getattr(s, 'recap_path', '') or ''
        if not recap_path:
            return s
        path = Path(recap_path)
        if not path.exists():
            return s
        try:
            latest = read_text_file(str(path))
        except Exception:
            return s
        if latest == (s.recap or ''):
            return s
        return self.update_session(s, recap=latest)

    def available_tag_dictionary_text(self) -> str:
        lines = ['受控标签词典（树状）']
        for cat, children in TAG_TREE.items():
            lines.append(f'【{cat}】')
            for tag, aliases in children.items():
                lines.append(f'- {tag}: ' + '、'.join(aliases))
        return '\n'.join(lines)

    def tag_tree(self) -> Dict[str, Dict[str, List[str]]]:
        refresh_tag_runtime()
        return TAG_TREE

    def add_custom_tags(self, items: List[Dict[str, Any]]) -> int:
        current = load_custom_tag_tree()
        added = 0
        for item in items or []:
            tag = str(item.get('tag', '')).strip()
            category = str(item.get('category', '')).strip() or guess_tag_category(tag)
            if not tag or canonicalize_tag(tag) in CANONICAL_TAGS:
                continue
            current.setdefault(category, {})[tag] = [tag]
            added += 1
        if added:
            save_custom_tag_tree(current)
            refresh_tag_runtime()
        return added

    def pixiv_auto_analyze_tags(self, tags: List[str]) -> Dict[str, Any]:
        return fetch_pixiv_tag_suggestions(tags)

    def _select_corpus_by_tags(self, tags: List[str], max_files: int) -> List[Dict[str, Any]]:
        rows = self._corpus_rows()
        out = []
        wanted = set(normalize_tags(tags))
        for r in rows:
            try:
                row_tags = set(json.loads(r['tags_json'] or '[]'))
            except Exception:
                row_tags = set()
            if not wanted or wanted & row_tags:
                out.append(r)
            if len(out) >= max_files:
                break
        return out

    def style_build_from_tags(self, tags: List[str], max_files: int) -> str:
        rows = self._select_corpus_by_tags(tags, max_files)
        snippets = []
        legacy_notes = []
        tag_text = tags_to_tree_text(tags) or '（未选择）'
        for r in rows:
            if r['snippet']:
                snippets.append(r['snippet'])
            a = self.conn.execute('SELECT single_style_dna FROM file_analyses WHERE file_path=?', (r['path'],)).fetchone()
            if a and a['single_style_dna']:
                legacy_notes.append(a['single_style_dna'])
        if legacy_notes:
            merged = summarize_text_block('\n\n---\n\n'.join(legacy_notes), 5000)
            return f'风格标签：\n{tag_text}\n样本数量：{len(rows)}\n\n综合 Style DNA：\n{merged}'
        return (
            f'风格标签：\n{tag_text}\n'
            f'样本数量：{len(rows)}\n\n'
            '建议风格 DNA：\n'
            '1. 句长保持有张有弛，关键动作段落用短句提速。\n'
            '2. 对话避免纯信息传递，尽量带潜台词和情绪位移。\n'
            '3. 场景描写优先服务叙事张力，不堆砌空泛形容。\n'
            '4. 重复意象可保留，但要控制近距离重复。\n\n'
            '样本摘录参考：\n' + summarize_text_block('\n\n'.join(snippets), 5000)
        )

    def lexicon_build_from_tags(self, tags: List[str], max_files: int) -> str:
        rows = self._select_corpus_by_tags(tags, max_files)
        legacy_notes = []
        vocab: Dict[str, int] = {}
        tag_text = tags_to_tree_text(tags) or '（未选择）'
        for r in rows:
            a = self.conn.execute('SELECT single_lexicon FROM file_analyses WHERE file_path=?', (r['path'],)).fetchone()
            if a and a['single_lexicon']:
                legacy_notes.append(a['single_lexicon'])
            text_block = (r['snippet'] or '').replace('\n', ' ')
            for token in text_block.split():
                token = token.strip(",.!?;:()[]{}<>\"'“”‘’")
                if 2 <= len(token) <= 16:
                    vocab[token] = vocab.get(token, 0) + 1
        if legacy_notes:
            return f'词库标签：\n{tag_text}\n样本数量：{len(rows)}\n\n' + summarize_text_block('\n\n---\n\n'.join(legacy_notes), 6000)
        top = sorted(vocab.items(), key=lambda x: (-x[1], x[0]))[:150]
        lines2 = [f'{w}  x{c}' for w, c in top]
        return f'词库标签：\n{tag_text}\n样本数量：{len(rows)}\n\n' + '\n'.join(lines2)

    def combo_build_from_tags(self, tags: List[str], max_files: int) -> Tuple[str, str, List[str], str, str]:
        style_text = self.style_build_from_tags(tags, max_files)
        lexicon_text = self.lexicon_build_from_tags(tags, max_files)
        combo_tags = normalize_tags(tags)
        combo_name = '组合包_' + '_'.join(combo_tags[:6]) if combo_tags else '组合包_默认'
        save_path = save_combo_package(combo_name, combo_tags, style_text, lexicon_text)
        return style_text, lexicon_text, combo_tags, save_path.stem, str(save_path)

    def load_combo_package(self, path: str) -> Dict[str, Any]:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        combo_tags = normalize_tags(data.get('combo_tags', []) or [])
        style_text = str(data.get('style_dna', '') or '')
        lexicon_text = str(data.get('lexicon', '') or '')
        combo_name = str(data.get('combo_name', Path(path).stem) or Path(path).stem)
        combo_text = (f"组合包名称：{combo_name}\n标签：\n{tags_to_tree_text(combo_tags)}\n\n"
                      f"{style_text}\n\n{lexicon_text}").strip()
        return {'combo_name': combo_name, 'combo_tags': combo_tags, 'style_dna': style_text,
                'lexicon': lexicon_text, 'combo_text': combo_text, 'combo_path': path}

    def save_text(self, path: str, text: str):
        write_text_file(path, text)

    def load_text(self, path: str) -> str:
        return read_text_file(path)


def write_text_file(path: str, text: str):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def read_text_file(path: str) -> str:
    return LocalCorpus.read_text(path)


def export_session_json(conn: sqlite3.Connection, s: ChatSessionState, path: str):
    turns = conn.execute('SELECT role, content, created_at, response_id, meta_json FROM turns WHERE session_id=? ORDER BY id ASC', (s.session_id,)).fetchall()
    payload = {
        'session': asdict(s),
        'turns': [dict(t) for t in turns],
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def save_combo_package(combo_name: str, combo_tags: List[str], style_text: str, lexicon_text: str) -> Path:
    out_dir = APP_DIR / 'combos'
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = ''.join(c if c.isalnum() or c in ('_', '-', '.') else '_' for c in combo_name)
    path = out_dir / f'{safe_name}.json'
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({
            'combo_name': combo_name,
            'combo_tags': combo_tags,
            'style_dna': style_text,
            'lexicon': lexicon_text,
            'saved_at': now_iso(),
        }, f, ensure_ascii=False, indent=2)
    return path


backend = SimpleNamespace(
    DEFAULT_TRAIN_DIR=DEFAULT_TRAIN_DIR,
    export_session_json=export_session_json,
    MODEL_CATALOG=MODEL_CATALOG,
    TASK_MODEL_DEFAULTS=TASK_MODEL_DEFAULTS,
    CANONICAL_TAGS=CANONICAL_TAGS,
)
