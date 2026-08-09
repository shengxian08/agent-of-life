# 🧹 数据清洗完全指南

> 脏数据进，脏结果出。AI 应用的质量，一半靠模型，一半靠洗数据。

---

## 目录

1. [什么是数据清洗？](#1-什么是数据清洗)
2. [文档摄入：从文件到向量](#2-文档摄入从文件到向量)
3. [查询处理：把用户的话变成可检索的问题](#3-查询处理把用户的话变成可检索的问题)
4. [检索引擎：四阶段精排流水线](#4-检索引擎四阶段精排流水线)
5. [工具参数清洗：LLM 的输出不可信](#5-工具参数清洗llm-的输出不可信)
6. [文本规范化：让模糊变精确](#6-文本规范化让模糊变精确)
7. [LLM 输出解析：从垃圾里淘金](#7-llm-输出解析从垃圾里淘金)
8. [清洗的代价：每多一步就多一点延迟](#8-清洗的代价每多一步就多一点延迟)

---

## 1. 什么是数据清洗？

在 AI 应用中，数据清洗不只是"去掉脏东西"，而是**把不可控的外部数据变成 LLM 能理解的稳定输入**。

```
你的项目有 4 条数据流，每条都要洗：

① 用户上传的文件 → 向量库
    PDF/DOCX/TXT → 文本提取 → 中文检测 → 语义分块 → 向量化

② 用户提问 → 检索引擎
    "冰箱有什么菜" → 改写 → HyDE → 多查询 → 检索 → 重排

③ LLM 输出 → 工具调用
    '{"name": "番茄"}' → 类型转换 → 边界校验 → 执行

④ 对话文本 → 记忆 + 缓存
    聊天记录 → 截断 → 规范化 → 摘要 → 存储
```

---

## 2. 文档摄入：从文件到向量

### 2.1 完整流水线（业界标准）

```
用户上传文件 (PDF / DOCX / TXT / HTML / MD)
        │
        ▼
  ① 格式检测 + 文本提取                             ← 你有
    ├─ PDF  → pdfplumber / PyMuPDF
    ├─ DOCX → python-docx
    ├─ TXT  → 直接读取
    ├─ HTML → BeautifulSoup 剥离标签
    └─ MD   → 直接读取
        │
        ▼
  ② 字符级清洗 Character Cleaning                    ← 你刚补了
    ├─ 全角→半角转换（Ａ → A, ０ → 0）
    ├─ Unicode 归一化（NFC/NFKC）
    ├─ 不可见字符剔除（\x00, \x01, BOM）
    ├─ 多余空白合并（3空格→1, 4换行→2）
    └─ 制表符 → 空格统一
        │
        ▼
  ③ 结构化清洗 Structural Cleaning                   ← 没有
    ├─ HTML/XML 标签剥离（<div>...</div> → 纯文本）
    ├─ Markdown 语法清洗（保留内容，去掉 ** ## [] 语法标记）
    ├─ URL 链接处理（保留/替换为 [链接] / 直接丢弃）
    ├─ 邮箱/手机号脱敏（可选）
    └─ 页眉/页脚/页码剔除（PDF 常见噪音，如 "第 3 页 / 共 10 页"）
        │
        ▼
  ④ 空值 + 低质量检测                               ← 你有
    ├─ 完全空文本 → 拒绝
    ├─ 只有标点/数字/空格 → 拒绝
    └─ 有效信息密度 < 阈值 → 告警
        │
        ▼
  ⑤ 语言/编码检测                                   ← 你有（仅中文占比）
    ├─ 主流语言识别（中文/英文/日文/韩文）
    ├─ 乱码检测（连续生僻 Unicode → 乱码）
    ├─ 混合语言比例判断
    └─ 编码修复（GBK → UTF-8, 乱码回退）
        │
        ▼
  ⑥ 内容去重 Deduplication                          ← 你刚补了
    ├─ 完全重复（MD5/SHA256 hash）→ 跳过
    ├─ 高度相似（>95% MinHash）→ 合并或跳过
    └─ 跨文档去重（同一份 PDF 传了两次）
        │
        ▼
  ⑦ 文本质量评分 Quality Scoring                    ← 你刚补了（基础版）
    ├─ 有效信息密度（中英数占比/总字符数）
    ├─ 句子完整性检测（是否全是半截句）
    ├─ 段落结构合理性（有没有自然段分隔）
    └─ 扫描件检测（文字量极少 → 提示用 OCR）
        │
        ▼
  ⑧ 文档结构解析 Structure Parsing                  ← 没有
    ├─ 按标题层级拆分（# → ## → ###）
    ├─ 保留章节结构元数据（chunk 属于哪个章节）
    ├─ 表格识别与结构化保存（Markdown table / CSV）
    ├─ 列表/编号检测（保持格式）
    └─ 图片 alt-text 提取
        │
        ▼
  ⑨ 元数据提取 Metadata Extraction                  ← 没有
    ├─ 文件名 → source 字段
    ├─ 文档标题（第一个 # 或文件名）
    ├─ 作者/创建时间（PDF metadata / Word 属性）
    ├─ 页数/字数统计
    └─ 自定义标签（用户上传时手动标注）
        │
        ▼
  ⑩ 分块 Chunking                                   ← 你有
    ├─ 语义分块（主策略）
    ├─ 递归分块（降级策略）
    └─ 命题级分块（前沿方案，见 9.2 节）
        │
        ▼
  ⑪ 向量化 + 入库                                   ← 你有
```

### 2.2 格式检测与文本提取

```python
ext = os.path.splitext(file_path)[1].lower()

if ext in (".txt", ".md"):
    text = open(file_path).read()

elif ext == ".pdf":
    with pdfplumber.open(file_path) as pdf:
        text = "\n\n".join(page.extract_text() or "" for page in pdf.pages)

elif ext == ".docx":
    doc = Document(file_path)
    text = "\n\n".join(p.text for p in doc.paragraphs)

elif ext in (".html", ".htm"):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(open(file_path).read(), "html.parser")
    # 去掉 script/style 标签
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
else:
    return {"error": f"不支持的文件类型: {ext}"}
```

### 2.3 字符级清洗：全角→半角 + Unicode 归一化

```python
import unicodedata
import re

def clean_characters(text: str) -> str:
    # ① Unicode 归一化 — 把 é (单个字符) 和 e + ́ (组合字符) 统一
    text = unicodedata.normalize('NFKC', text)

    # ② 全角→半角转换
    result = []
    for c in text:
        code = ord(c)
        if 0xFF01 <= code <= 0xFF5E:      # 全角标点/字母/数字
            result.append(chr(code - 0xFEE0))
        elif code == 0x3000:               # 全角空格
            result.append(' ')
        else:
            result.append(c)
    text = ''.join(result)

    # ③ 不可见字符剔除（NULL, SOH, STX 等控制字符）
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # ④ 多余空白合并
    text = re.sub(r'\n{3,}', '\n\n', text)   # 连续空行 → 2 个
    text = re.sub(r' {2,}', ' ', text)       # 多余空格 → 1 个
    text = re.sub(r'\t+', ' ', text)         # 制表符 → 空格

    return text.strip()
```

**为什么重要**：

```
用户从微信复制: "红烧肉：３００ｇ五花肉，５０ｇ冰糖。    步骤１：焯水。"
                         ↑ 全角数字              ↑ 全角     ↑ 全角数字

清洗后:          "红烧肉：300g五花肉，50g冰糖。 步骤1：焯水。"

不洗的后果: BGE-M3 向量空间中 "３００" ≠ "300" → 用户搜 "300" 搜不到这个文档
```

### 2.4 结构化清洗：HTML/Markdown 语法剥离

```python
def clean_structure(text: str, source_type: str = "") -> str:
    """去掉格式标记，保留纯文本内容"""

    # ① HTML 标签剥离（如果文本是 HTML 提取的）
    if source_type == "html":
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n")

    # ② Markdown 语法清洗 — 保留内容，去掉标记符
    #    **加粗** → 加粗
    #    [链接文字](url) → 链接文字
    #    ![图片](url) → [图片]
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)         # 加粗
    text = re.sub(r'\*(.+?)\*', r'\1', text)             # 斜体
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)      # 链接
    text = re.sub(r'!\[.*?\]\(.+?\)', '[图片]', text)    # 图片
    text = re.sub(r'`{1,3}[^`]*`{1,3}', '', text)       # 行内代码
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # 标题标记

    # ③ URL 链接处理 — 替换为占位符
    text = re.sub(r'https?://\S+', '[链接]', text)

    # ④ 页眉页脚页码（PDF 常见）
    text = re.sub(r'^\d+\s*$', '', text, flags=re.MULTILINE)      # 纯数字行
    text = re.sub(r'第\s*\d+\s*页', '', text)                      # "第3页"
    text = re.sub(r'Page\s+\d+\s+of\s+\d+', '', text, flags=re.IGNORECASE)

    return text.strip()
```

### 2.5 空值 + 低质量检测

```python
def quality_detect(text: str) -> dict:
    """多维度质量检测"""
    total = len(text)

    # ① 完全空
    if total == 0:
        return {"pass": False, "reason": "空文本"}

    # ② 只有标点/数字/空格（不含任何有意义文字）
    letters = sum(1 for c in text if c.isalpha() or '一' <= c <= '鿿')
    if letters == 0 and total > 3:
        return {"pass": False, "reason": "只有标点/数字，无有效文本"}

    # ③ 有效信息密度
    meaningful = sum(1 for c in text
                     if '一' <= c <= '鿿' or c.isalpha() or c.isdigit())
    ratio = meaningful / max(total, 1)

    if ratio < 0.3 and total > 100:
        return {"pass": True, "warning": f"信息密度 {ratio:.0%}，可能是扫描件或乱码"}

    return {"pass": True, "score": round(ratio, 3)}
```

### 2.6 内容去重

```python
import hashlib

_ingested_hashes: set[str] = set()

def deduplicate(text: str) -> tuple[bool, str]:
    """MD5 去重 + MinHash 近似去重"""

    # ① 精确去重（MD5）
    text_hash = hashlib.md5(text.encode()).hexdigest()
    if text_hash in _ingested_hashes:
        return False, "文档已存在（完全重复）"

    _ingested_hashes.add(text_hash)
    return True, ""
```

**MinHash 近似去重（高级版，适合大批量文档）**：

```python
# 用于检测"改了两个字就重新上传"的文档
def minhash_similarity(text1: str, text2: str) -> float:
    """MinHash 估算 Jaccard 相似度"""
    # 把文本拆成 n-gram (3-gram)
    def shingles(text, n=3):
        return set(text[i:i+n] for i in range(len(text) - n + 1))

    set1, set2 = shingles(text1), shingles(text2)
    if not set1 or not set2:
        return 0.0
    return len(set1 & set2) / len(set1 | set2)

# 相似度 > 95% → 视为重复
```

### 2.7 语言检测 + 编码修复

```python
def detect_language(text: str) -> dict:
    """检测文本主要语言 + 编码健康度"""
    total = len(text)
    if total == 0:
        return {"lang": "unknown", "encoding_ok": False}

    # 各语言字符统计
    cn = sum(1 for c in text if '一' <= c <= '鿿')
    jp = sum(1 for c in text if 'ぁ' <= c <= 'ヿ')
    kr = sum(1 for c in text if '가' <= c <= '힣')
    en = sum(1 for c in text if c.isascii() and c.isalpha())

    # 判断主流语言
    counts = {"zh": cn, "ja": jp, "ko": kr, "en": en}
    main_lang = max(counts, key=counts.get)

    # 乱码检测：全是生僻 Unicode 但不是任何已知语言
    known_chars = cn + jp + kr + en
    ratio = known_chars / max(total - text.count(' '), 1)
    encoding_ok = ratio > 0.3

    return {"lang": main_lang, "encoding_ok": encoding_ok, "cn_ratio": round(cn/max(total,1), 3)}
```

### 2.8 文档结构解析

```python
def parse_structure(text: str) -> list[dict]:
    """按 Markdown 标题层级拆分文档结构"""
    sections = []
    current_title = ""
    current_level = 0
    current_content = []

    for line in text.split('\n'):
        # 检测标题行 "## 食材清单"
        match = re.match(r'^(#{1,6})\s+(.+)', line)
        if match:
            # 保存上一节
            if current_content:
                sections.append({
                    "title": current_title,
                    "level": current_level,
                    "content": '\n'.join(current_content),
                })
            current_level = len(match.group(1))
            current_title = match.group(2)
            current_content = []
        else:
            current_content.append(line)

    # 保存最后一节
    if current_content:
        sections.append({
            "title": current_title,
            "level": current_level,
            "content": '\n'.join(current_content),
        })

    return sections
```

**为什么重要**：分块时带上章节标题作为元数据，检索时 LLM 能知道"这段话出自红烧肉的食材章节"而不是凭空猜测。

### 2.9 元数据提取

```python
def extract_metadata(file_path: str, text: str) -> dict:
    """从文件和内容中提取元数据"""
    import os
    from datetime import datetime

    meta = {
        "filename": os.path.basename(file_path),
        "file_ext": os.path.splitext(file_path)[1],
        "file_size_kb": round(os.path.getsize(file_path) / 1024, 1),
        "char_count": len(text),
        "ingested_at": datetime.now().isoformat(),
    }

    # 提取文档标题（第一个 # 标题 或 第一行非空文本）
    first_line = text.strip().split('\n')[0] if text else ""
    title_match = re.match(r'^#\s+(.+)', first_line)
    meta["title"] = title_match.group(1) if title_match else first_line[:100]

    # PDF 元数据
    if meta["file_ext"] == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                pdf_meta = pdf.metadata or {}
                meta["author"] = pdf_meta.get("Author", "")
                meta["pdf_created"] = pdf_meta.get("CreationDate", "")
        except Exception:
            pass

    return meta
```

### 2.10 智能分块：语义分块 (Semantic Chunking)

这是清洗后最核心的一步。不是按固定字数切，而是**在语义变化处切**。

```
传统分块（按 500 字强制切）:
  ┌───────────────────┐ ┌───────────────────┐
  │ 红烧肉是一道经典...  │ │ 做法：1.五花肉切块  │
  │ 需要准备五花肉...   │ │ 2.热锅凉油...      │
  │ 这道菜起源于...    │ │ 3.加入冰糖...       │
  └───────────────────┘ └───────────────────┘
  块1：历史和食材混在一起    块2：只有做法，缺开头

语义分块（在主题切换处切）:
  ┌───────────────────┐ ┌───────────────────────────┐
  │ 红烧肉是一道经典...  │ │ 做法：1.五花肉切块        │
  │ 起源于宋代...      │ │ 2.热锅凉油，加入冰糖炒糖色  │
  └───────────────────┘ │ 3.小火炖40分钟...         │
   块1：历史背景         └───────────────────────────┘
                         块2：完整做法
```

**实现原理**：

```python
def _semantic_split(self, text):
    sentences = self._split_sentences(text)
    embeddings = embedder.embed_sync(sentences)

    # 计算相邻句子余弦相似度
    similarities = []
    for i in range(len(embeddings) - 1):
        sim = cosine_similarity(embeddings[i], embeddings[i+1])
        similarities.append(sim)
    # [0.92, 0.88, 0.31, 0.85, ...]
    #               ↑ 骤降！这里切断

    # 自适应阈值
    threshold = np.mean(similarities) - np.std(similarities)
    breakpoints = [i+1 for i, sim in enumerate(similarities) if sim < threshold]
    return merge_sentences_by_size(sentences, breakpoints)
```

### 2.11 降级：递归分块

语义分块失败时自动降级：

```python
separators = [
    "\n\n",    # 段落级
    "\n",      # 换行级
    "。！？",  # 句子级
    ".!?",     # 英文句号
    "；;",     # 分号级
    "，,",     # 逗号级
    " ",       # 单词级（最后手段）
]
```

---

## 3. 查询处理：把用户的话变成可检索的问题

用户的问题往往不够"精确"。人类随意说的一句话，直接拿去搜向量库效果很差。**查询处理的核心目标：把用户的口语，变成搜索系统能理解的查询。**

### 3.1 查询处理的完整流水线

```
用户输入: "我想弄个红烧肉吃吃，家里好像还有点五花肉"
        │
        ▼
  ① Query Rewrite（查询改写）               ← 你有
     "红烧肉家常做法"、"红烧肉正宗教程"、"五花肉怎么烧"
        │
        ▼
  ② HyDE（假设文档嵌入）                     ← 你有（可选）
     先让 LLM 编一段答案 → 用答案去搜
        │
        ▼
  ③ Step-back Prompting（抽象回退）          ← 没有
     把具体问题抽象成更宽泛的概念再搜
        │
        ▼
  ④ Multi-hop Decomposition（多跳分解）      ← 没有
     复杂问题拆成子问题链，逐步检索
        │
        ▼
  ⑤ Query2Doc（生成伪文档）                  ← 前沿
     LLM 生成一篇假文档，用假文档去搜真文档
        │
        ▼
     多查询并行检索 → 结果融合
```

### 3.2 Query Rewrite（查询改写）— 你有

```python
用户原文: "红烧肉怎么做"
  ↓ LLM 改写
改写1: "红烧肉的家常做法步骤"
改写2: "红烧肉需要哪些食材和调料"
改写3: "正宗红烧肉烹饪教程"
改写4: "红烧肉制作过程详解"

原始查询权重 = 1.0
改写查询权重 = 0.7  （改写可能有偏差，不能跟原问题等权重）
```

**为什么改写？** 用户的措辞和知识库里的措辞可能完全不同。同一个意思用多种说法搜，提高命中率。

### 3.3 HyDE（假设文档嵌入）— 你有

```
用户问题: "菠菜快过期了能做什么"
  ↓ 让 LLM 先编一个假设答案
假设答案: "临近过期的菠菜可以做蒜蓉菠菜，只需大蒜和油。
          也可以做菠菜鸡蛋汤，搭配鸡蛋和枸杞..."
  ↓ 把这个假设答案也当成一个查询去检索

HyDE 的论文发现: 假设答案的 embedding 向量
  比问题的 embedding 向量更接近真实答案的 embedding 向量。
  
原因: 问题的向量在"问题空间"，答案的向量在"答案空间"，
      假设答案虽然可能是错的，但它在"答案空间"里。
```

### 3.4 Step-back Prompting（抽象回退）— 你没有

这是 Google DeepMind 2023 年提出的技术。思路是：**先问一个更抽象的问题，获取更广泛的上下文，再回答具体问题**。

```
用户问: "特斯拉 Model 3 的续航在冬天会打几折？"
  
  传统做法: 直接搜 "特斯拉 Model 3 冬天续航" → 可能找不到

  Step-back:
    ① 先抽象化: "电动车冬天续航衰减原理" → 搜到锂电池低温特性
    ② 再具体化: "特斯拉 Model 3 电池容量 60kWh" → 搜到具体参数
    ③ 结合两者 → 回答: "冬天约打 7 折，因为锂电池在 0°C 以下容量约降 30%"
```

```python
async def stepback_rewrite(query: str):
    """生成一个更抽象的'退一步'查询"""
    prompt = """把以下问题抽象成一个更宽泛、更基础的问题。
    只输出一个问题，不要解释。
    
    例子: "特斯拉冬天续航打几折" → "电动车锂电池低温性能"
          "红烧肉怎么做"       → "中式红烧类菜肴的基本烹饪方法"
    """
    abstract_query = await llm.chat(prompt, query)
    # 两个查询都去检索，结果合并
    return abstract_query
```

### 3.5 Multi-hop Decomposition（多跳分解）— 你没有

复杂问题需要分步检索，每一步的答案决定下一步的方向。

```
用户问: "发明电话的人哪年出生？"

  一步到位（传统 RAG）:
    搜 "发明电话的人 出生年份" → 可能找不到（知识库里"贝尔"和"电话发明"是分开的）
  
  两步分解（Multi-hop）:
    Step 1: "谁发明了电话？"
      → 找到: "亚历山大·格拉汉姆·贝尔发明了电话"
    Step 2: "亚历山大·格拉汉姆·贝尔哪年出生？"
      → 找到: "贝尔出生于 1847 年"
    
  答案: 1847 年
```

```python
async def decompose_query(query: str) -> list[str]:
    """LLM 把复杂问题拆成子问题链"""
    resp = await llm.chat(
        prompt="把复杂问题拆成 2-3 个依次依赖的子问题。每行一个。",
        message=query
    )
    # "发明电话的人哪年出生" →
    # ["谁发明了电话？", "{上一步答案}哪年出生？"]
    return resp.split("\n")
```

### 3.6 Query2Doc（生成伪文档）— 前沿

这是 2023 年提出的技术，比 HyDE 更进一步：**让 LLM 生成一篇完整的"伪文档"，用伪文档去匹配真文档。**

```
HyDE:  问题 → LLM生成假设答案（2-3句话） → 搜
Query2Doc: 问题 → LLM 生成完整伪文档（200-500字） → 拼到问题后面 → 一起搜

伪文档的语义空间和真文档几乎重叠 → 召回率极高。
代价: 每次多 500ms （生成一篇短文）
```

```python
async def query2doc(query: str) -> str:
    resp = await llm.chat(
        prompt="请你扮演一个知识库助手，为以下问题撰写一篇 200 字的回答。"
               "这篇回答将用于搜索引擎找到最相关的真实文档。",
        message=query,
        max_tokens=300,
    )
    # 把伪文档拼到原始 query 后面当做一个整体去搜
    enhanced_query = f"{query}\n{resp}"
    return enhanced_query
```

### 3.7 各种查询增强技术的适用场景总结

```
简单事实型（"番茄多少钱"）:
  → 原始查询直接搜即可，不需要增强

中等复杂度（"红烧肉怎么做"）:
  → Query Rewrite + HyDE ← 你现在有
  
知识密集型（"电动车冬天续航衰减原理"）:
  → + Step-back Prompting ← 值得加

多步推理型（"中国 GDP 最高的省的省会是哪里"）:
  → + Multi-hop Decomposition ← 明显提升
  
长尾问题（知识库里可能没有直接答案）:
  → + Query2Doc ← 召回率暴涨，但成本高
```

---

## 4. 检索引擎：从四阶段到八仙过海

### 4.1 你现在的四阶段流水线

```
Query（经改写增强后）
  │
  ├─→ Dense 向量召回 (BGE-M3, 1024维)
  │    语义匹配，找"意思相近"的文档
  │    召回 Top 20
  │
  ├─→ BM25 关键词召回 (jieba 分词)
  │    精确匹配，找"字面相同"的文档
  │    召回 Top 20
  │    ── 并行执行（asyncio.gather）
  │
  ▼
RRF 融合 (Reciprocal Rank Fusion)
  公式: α/(k+rank_d) + (1-α)/(k+rank_b)
  α = 0.7, k = 60
  输出 Top 20 融合候选
  
  ▼
BGE-Reranker 精排 (CrossEncoder)
  query + 候选文档 → 逐对打分 → 归一化
  final_score = RRF×0.3 + Rerank×0.7
  输出 Top 5 最终结果
  
  ▼
质量门槛过滤
  dense_score ≥ 0.15 | 元数据匹配 | 截断 max_chars
```

### 4.2 双路召回详解：Dense + BM25 为什么互补

```
"Dense 向量擅长语义，BM25 擅长精确"

"红烧肉" 的召回对比:
  Dense 向量 (BGE-M3):
    找到 "东坡肉"、 "回锅肉"、 "梅菜扣肉" 
    → 语义相似（都是中式肉类菜肴），但不精确
    
  BM25 (jieba 分词):
    找到 "红烧肉家常做法"、 "红烧肉怎么做好吃"
    → 精确命中 "红烧肉" 关键词，但没有语义泛化

  RRF 融合后:
    排名1: "红烧肉家常做法"      (Dense rank=1, BM25 rank=1) ← 双料冠军
    排名2: "红烧肉正宗教程"      (Dense rank=2, BM25 rank=2)
    排名3: "东坡肉做法"          (Dense rank=3, BM25 rank=20+) ← Dense 拉上来的
    排名4: "各种红烧菜谱"        (Dense rank=5, BM25 rank=5)
```

**为什么不用 BM25 就亏了？**

```
中文的特殊问题：专有名词在 Dense 向量里跟普通词区分度不够

"海尔冰箱" vs "海信冰箱" → Dense 可能分不清
"油烟机"   vs "抽油烟机" → Dense 以为是一回事

BM25 能精准区分这些词汇差异。
```

### 4.3 RRF 融合公式详解

```python
rrf_score = α / (k + dense_rank) + (1-α) / (k + bm25_rank)

# 参数含义:
#   α=0.7 → Dense 的权重更大（语义搜索更可靠，主力）
#   k=60  → 平滑常数，防止 rank=1 和 rank=2 差距过大
#           k 越大，rank 的影响越小，分数越平均
#           k 越小，rank 的影响越大，第1名和第2名差距很大

# 直观理解:
#   rank=1 在 Dense → 贡献 0.7/(60+1) ≈ 0.0115
#   rank=2 在 Dense → 贡献 0.7/(60+2) ≈ 0.0113
#   差距很小（0.0002），这意味着"第1和第2没有那么大的差别"
#   k=60 的作用就是"别太迷信排名"
```

### 4.4 CrossEncoder 精排：为什么比向量检索更精确

```
Bi-Encoder (BGE-M3):
  Query  "红烧肉" → encode → [0.12, -0.34, 0.56, ...]
  Doc1   "东坡肉" → encode → [0.11, -0.32, 0.55, ...]
  → 余弦相似度 0.89 → 高相关！
  
  问题: Query 和 Doc 是分别编码的，无法交互理解

CrossEncoder (BGE-Reranker):
  Input: ["红烧肉怎么做？", "东坡肉是一道..."]
  → 两个文本拼在一起输入模型 → 直接输出相关性分数 0.45
  → 模型看到了"红烧肉"和"东坡肉"的关系，知道它们不完全相同

  Input: ["红烧肉怎么做？", "红烧肉的家常做法是..."]
  → 直接输出 0.92 ← 这才是真正的相关
```

```
Bi-Encoder (召回阶段):  速度极快（向量已经预计算），精度中等
CrossEncoder (精排阶段): 速度较慢（每次都要重新算），精度极高

组合: Bi-Encoder 召回 Top 20 → CrossEncoder 精排取 Top 5
      既快又准
```

### 4.5 业界还有哪些检索方式？

除了你用的 Dense + BM25 + CrossEncoder，业界还有这些派系：

#### ① ColBERT — 晚交互 Late Interaction（Meta 力推）

```
传统 Bi-Encoder:
  Query → 1 个向量       ← 整句话压成一个向量，信息损失大
  Doc   → 1 个向量
  → 两个向量算余弦

ColBERT:
  Query → ["红", "烧", "肉"] → 3 个 token 向量
  Doc   → ["红", "烧", "肉", "的", "做", "法"] → 6 个 token 向量
  → 每个 query token 找最相似的 doc token
  → MaxSim 求和 → 最终分数
  
  "红烧肉" 中的 "肉" 会和 doc 中的 "肉"、"猪肉"、"五花肉" 分别匹配
  ↑ 粒度更细，信息保留更好
```

**代价**：每个文档要存 N 个向量（N = token 数量），存储量暴涨 10-100 倍。

#### ② SPLADE — 学出来的稀疏检索

```
BM25 (你用的): 用 jieba 分词 → 每个词独立 → 词之间没关联
SPLADE:       用神经网络学习 → 每个词的权重是学出来的 →
               "红烧肉" 检索时会自动激活 "东坡肉"、"回锅肉" 等关联词

SPLADE 本质: 把 Dense 的"语义理解"和 BM25 的"稀疏高效"缝合到一起。
```

#### ③ GraphRAG — 知识图谱加持（Microsoft 开源，2024 年最火）

```
传统 RAG: 
  用户问 "番茄炒蛋用什么油？"
  → 检索 "番茄炒蛋 油" → 可能找到 10 个文档
  → LLM 自己从 10 个文档里拼答案

GraphRAG:
  ① 离线: 把知识库变成知识图谱
     实体: 番茄炒蛋、食用油、花生油、菜籽油
     关系: (番茄炒蛋)-(使用)-(食用油)
           (食用油)-(子类)-(花生油)
           (食用油)-(子类)-(菜籽油)

  ② 查询时: 在图谱里做社区发现
     找到"烹饪用油"这个知识社区 → 提取社区摘要 → 给 LLM

  效果: 回答更全面（能看到整个知识社区，而不是零散的 5 个文档片段）
  代价: 离线建图很慢（几万个文档要跑几个小时）
```

#### ④ RankGPT — 让 LLM 自己排序

```
CrossEncoder (你用的): 专门的小模型（BGE-Reranker）打分
RankGPT:              直接用 GPT-4 / DeepSeek 打分

输入 LLM:
  "请对以下文档按与问题的相关度排序，输出排名列表。
   问题: 红烧肉怎么做？
   文档1: 东坡肉做法...
   文档2: 红烧肉家常做法...
   文档3: 回锅肉教程..."
  
  LLM 输出: [文档2, 文档1, 文档3]  ← LLM 自身做排序

优点: 理解力远超小模型，能处理复杂语义
缺点: 贵（每次排序调一次 LLM），慢（1-2秒）
```

#### ⑤ Contextual Retrieval — Anthropic 2024 年提出

```
传统: 每个 chunk 单独存，"红烧肉 | 需要五花肉500g"
Contextual: 每个 chunk 前面拼上文档标题/上下文

  "《中式菜谱大全》> 第三章：肉类菜谱 > 红烧肉 | 需要五花肉500g"
  ↑ 这个 chunk 现在自带"我在聊什么"的上下文
  
  检索时: "五花肉适合做什么菜？"
    → 找到 "肉类菜谱 > 红烧肉 | 需要五花肉500g"
    → 还知道这来自"中式菜谱" → 可以进一步检索中式菜谱的其他内容
```

Anthropic 声称加了这一行上下文前缀之后，检索失败率降低了 49%。

#### ⑥ RAPTOR — 树状索引（2024）

```
传统: 所有 chunk 平铺 → 检索 Top K
RAPTOR: 把 chunk 组织成树

  Level 2:    [摘要: 中式肉类菜谱概述]
               ↙          ↓         ↘
  Level 1: [红烧类]     [清蒸类]    [爆炒类]
            ↙    ↘       ↙  ↘       ↙   ↘
  Level 0: [红烧肉] [红烧排骨] [清蒸鱼] [蒸蛋] [宫保鸡丁] [回锅肉]

检索流程:
  ① 先在 Level 2 搜 → 确定大类是"中式肉类菜谱"
  ② 再到 Level 1 搜 → 缩小到"红烧类"
  ③ 最后 Level 0 精搜 → 返回 "红烧肉" 和 "红烧排骨"

  ← 不需要遍历所有 chunk，逐层缩小范围，检索更快
```

### 4.6 各种检索技术的定位

```
                              精度 →
    低                        中                        高
    │                         │                         │
快   │  纯 BM25               │                         │
    │  (精确匹配，无语义)      │                         │
    │                         │  Dense向量              │
    │                         │  (BGE-M3, 语义匹配)     │
    │                         │                         │
    │                         │  Dense + BM25 + RRF     │  ColBERT
    │                         │  ← 你现在在这里          │  (token级匹配)
    │                         │                         │
    │                         │  + CrossEncoder Reranker│  RankGPT
    │                         │  ← 你也有（生产关了）     │  (LLM排序)
    │                         │                         │
慢   │                         │                         │  GraphRAG
    │                         │                         │  (知识图谱)
    
    你的最优策略:
      Dense + BM25 + RRF → Top 20 → CrossEncoder → Top 5
      在"速度"和"精度"的甜点区
```

---

## 5. 工具参数清洗：LLM 的输出不可信

LLM 调用工具时返回的参数，永远是脏的。必须清洗。

### 5.1 类型强制转换

```python
# LLM 可能返回: {"limit": "5"}  ← 字符串，不是整数
# LLM 可能返回: {"limit": 5.0}  ← 浮点数，不是整数

# 清洗：
for key, prop_info in props.items():
    val = arguments[key]
    expected_type = prop_info.get("type", "string")

    if expected_type == "integer" and not isinstance(val, int):
        val = int(val)           # "5" → 5, 5.0 → 5

    elif expected_type == "number" and not isinstance(val, (int, float)):
        val = float(val)         # "3.5" → 3.5

    elif expected_type == "boolean" and isinstance(val, str):
        val = val.lower() in ("true", "1", "yes")  # "true" → True

    valid_args[key] = val
```

### 5.2 边界校验

```python
# 数量不能 <= 0
if quantity <= 0:
    return {"error": f"数量必须大于0，传入 {quantity}"}

# 过期天数不能为负
if expiry_days < 0:
    return {"error": f"过期天数不能为负数，传入 {expiry_days}"}

# 名称不能为空
if not name or not name.strip():
    return {"error": "食材名称不能为空"}
```

### 5.3 缺失参数检测

```python
required = set(schema.get("required", []))
for key in required:
    if key not in arguments:
        return {"error": f"缺少必需参数: {key}"}
```

### 5.4 数据格式兼容

```python
# LLM 可能这样传 meal_plan:
#   {"日1": ["菜1", "菜2"]}        ← dict 格式（正确）
#   ["菜1", "菜2"]                 ← list 格式（错误！但 LLM 经常这么干）

# 清洗：两种都兼容
if isinstance(meals_data, dict):
    all_meals = [m for day_list in meals_data.values() for m in (day_list or [])]
elif isinstance(meals_data, list):
    all_meals = meals_data
else:
    all_meals = []
```

---

## 6. 文本规范化：让模糊变精确

### 6.1 意图路由的关键词匹配

```python
# 用户可能打: "冰箱...里...有什么？？？"
# 清洗：直接用 `in` 做子串匹配
if any(kw in msg for kw in ["冰箱", "购物清单", "比价"]):
    return "shopping"

# 寒暄的特殊处理：
short_greetings = {"你好", "hi", "hello", "在吗"}
if msg.lower() in short_greetings or len(msg) < 3:
    return "general"
```

### 6.2 语义缓存的 Key 规范化

```python
def _cache_key(session_id, query):
    normalized = query.strip().lower()[:200]  # 归一化：去空格、全小写、截断
    return hashlib.md5(f"{session_id}:{normalized}".encode()).hexdigest()
```

### 6.3 对话历史的截断与拼接

```python
# 拼对话时每条截断到 300 字符
for msg in history[-10:]:
    role_name = "用户" if msg.role == "user" else "助手"
    dialog_text += f"{role_name}: {msg.content[:300]}\n"  # ← 防止单条消息太长
```

### 6.4 LLM 分类输出的清理

```python
# LLM 可能输出: "shopping.\n\n" 或 "Shopping" 或 "  shopping,"
label = resp.content.strip().lower()
label = label.split("\n")[0]           # 只取第一行
label = label.strip().rstrip(".,，。")  # 去掉句号和逗号
```

---

## 7. LLM 输出解析：从垃圾里淘金

### 7.1 JSON 提取

LLM 经常在 JSON 外面包 Markdown 或废话：

```python
# LLM 输出可能是:
#   ```json
#   {"preferences": ["酸辣口味"]}
#   ```
# 或者:
#   "好的，以下是提取结果：{"preferences": ["酸辣口味"]}"

# 清洗：
if "```" in content:
    content = content.split("```")[1]       # 取代码块内容
    if content.startswith("json"):
        content = content[4:]                # 去掉 "json" 标记
result = json.loads(content.strip())
```

### 7.2 工具调用参数 JSON 异常捕获

```python
for tc in msg.tool_calls:
    try:
        args = json.loads(tc.function.arguments)
    except json.JSONDecodeError:
        args = {}  # LLM 输出了非法 JSON → 给空字典，工具内部自己处理
```

### 7.3 置信度过滤

```python
# RAG 答案自省：LLM 生成的回答是否真的基于检索到的文档？
resp = await llm.chat(
    prompt="判断以下答案是否完全基于提供的参考信息。只回答 YES 或 NO。",
    message=f"参考: {context}\n答案: {answer}"
)
is_reliable = "YES" in resp.upper()  # 不是 YES 就是不可靠
```

---

## 8. 清洗的代价：每多一步就多一点延迟

```
一条完整请求的清洗成本:

文档摄入:
  格式提取:    ~10ms (文件 I/O)
  中文检测:    ~1ms  (纯内存计算)
  语义分块:    ~500ms (BGE-M3 向量化每个句子)
  向量化入库:  ~200ms

查询处理:
  Query Rewrite: ~300ms (LLM 调用)
  HyDE:          ~300ms (LLM 调用)
  Dense 检索:    ~50ms
  BM25 检索:     ~20ms
  RRF 融合:      ~1ms
  Reranker 精排: ~200ms (CrossEncoder)

总计: 每步都是几百毫秒，加起来就一两秒了
```

**所以你的项目做了取舍**：

| 清洗步骤 | 开发环境 | 生产环境 |
|---------|---------|---------|
| Query Rewrite | ✅ | ✅ |
| HyDE | ✅（可选） | ✅（可选） |
| Reranker | ✅ | ❌ 关闭（省 200ms） |
| 语义分块 | ✅ | ✅ |

> **清洗的哲学**：不是洗得越干净越好，而是在"干净"和"快"之间找一个平衡点。有时候宁可容忍一点脏数据，也不能让用户等太久。

---

## 9. 实话：这个领域到底还有没有新东西？

### 9.1 对你当前的需求：够了

四阶段检索（Query Rewrite → Dense+BM25 → RRF → Reranker）、语义分块、参数清洗、LLM 输出解析——这就是 2024-2025 年 RAG 数据清洗的**标准工业套餐**。LlamaIndex、LangChain、Cohere、Voyage AI 做的也是同一套流水线。

### 9.2 七股力量在改写游戏规则

#### ① 超长上下文模型 — 可能让整个 RAG 流水线消失

```
传统 RAG:
  文档 → 分块 → 向量化 → 检索 Top5 → 拼接 → LLM 生成

超长上下文（2025 年趋势）:
  用户提问 → 把相关文档完整塞给 LLM（128K~1M tokens）→ 直接回答
  
  不再需要分块、向量化、检索、Reranker。
  整条 RAG 流水线被一句 "把文档完整给他" 取代。
```

**现状**：Gemini 已经支持 1M+ tokens（可以一次塞进整部《三体》）。如果你的知识库只有几百篇文档，直接用超长上下文比 RAG 简单且效果好。RAG 的价值正在收缩到 **"几万篇文档远超上下文窗口"** 的极端场景。

#### ② GraphRAG — 从"检索片段"到"知识社区发现"（Microsoft 2024）

这是 2024 年最受关注的检索技术，由微软研究院提出：

```
传统 RAG: 搜到 5 个碎片 → 拼给 LLM → 生成的答案可能片面

GraphRAG:
  ① 离线建图: 所有文档 → 提取实体和关系 → 构建知识图谱
     实体: 番茄、食用油、花生油、菜籽油、张三、过敏
     关系: (番茄炒蛋)-(需要)-(食用油)
           (张三)-(过敏)-(花生)

  ② 社区发现: 在图里检测紧密连接的"知识社区"
     "烹饪用油"社区: 花生油、菜籽油、橄榄油、烟点、用法
     "用户偏好"社区: 张三、花生过敏、偏好川菜

  ③ 社区摘要: 每个社区生成一段自然语言摘要

  ④ 检索: 用户问 → 找到相关社区 → 返回社区摘要（而非碎片）
       → LLM 获得的是"完整的知识图景"，不是孤立的 5 个片段
```

**效果**：回答的全面性显著优于传统 RAG（因为看到了整个知识社区），特别适合需要全局视角的问题（"总结我们家的饮食习惯"）。

**代价**：
- 建图极慢（几万文档跑几小时）
- 每次建图要大量 LLM 调用（提取实体、生成摘要）
- 更适合"一次性导入、多次查询"的知识库

#### ③ ColBERT + 多向量检索 — 从"文档级"到"Token 级"

```
传统: 一个文档 = 1 个向量（1024 维）
  "红烧肉需要五花肉、冰糖、酱油、八角、桂皮..."
  → encode → [0.12, -0.34, ...]  ← 这么多信息压成一个向量，信息损失大

ColBERT: 一个文档 = N 个向量（每个 token 一个）
  "红" → [0.12, ...]
  "烧" → [0.34, ...]
  "肉" → [0.56, ...]
  
  检索: query 的每个 token 跟 doc 的每个 token 逐对匹配（MaxSim）
  → 精度极高（token-level interaction）
  → 存储量暴涨 50-100 倍（一个文档从 1 个向量变成 100 个向量）
```

**现状**：ColBERT v2、PLAID 等优化版本已经在工业界可用。适合对精度要求极高但文档量不大（<100 万篇）的场景。

#### ④ Agentic RAG — 让 Agent 自己编排检索策略

```
传统 RAG（你的）:
  固定流水线，不管什么问题，流程完全一样

Agentic RAG:
  Agent 收到问题后自己决定"怎么查"

  简单问题 "番茄多少钱？"
    → Router: 单跳检索 → 直接 Dense → 返回 → 快（200ms）

  对比问题 "永辉和美团哪个买番茄便宜？"
    → Router: 并行检索 → 同时查永辉和美团 → 对比 → 中速

  推理问题 "如果我想做红烧肉，现有食材还缺什么？"
    → Router: 多跳检索 → 
      第1跳: 冰箱有什么？→ 菠菜、鸡蛋
      第2跳: 红烧肉要什么？→ 五花肉、冰糖、酱油
      第3跳: 缺什么？→ 五花肉、冰糖、酱油
      → 慢但完整

  自适应: Agent 自己判断问题复杂度 → 自己选择检索深度
```

**代表项目**：LangGraph Agentic RAG、Cohere Compass、CrewAI。

#### ⑤ Self-RAG / CRAG — 检索后自我纠错

```
传统 RAG: 检索 → 生成 → 完事。检索质量差了也没人管。

Self-RAG (你的项目有雏形):
  生成答案后 → LLM 自省: "这个答案真的基于检索到的文档吗？"
  → 不可靠 → 重新检索或标注"仅供参考"

CRAG (Corrective RAG, 2024):
  检索后先评估质量:
    ① 检索到的文档相关度 > 阈值 → 直接生成 ✅
    ② 相关度中等 → 再用 Web 搜索补充 📡
    ③ 相关度太低 → 全部丢弃，纯 LLM 回答 💬
  
  相当于: 检索 → 自检 → 纠错 → 生成
          不是"搜到什么就信什么"
```

#### ⑥ 命题级分块 + Late Chunking

```
当前语义分块: 800 字一块，语义断点处切
命题级分块:   每个原子事实一个 chunk
  "番茄 3.0元/500g" → chunk
  "番茄产自山东"     → chunk
  "番茄富含维生素C"  → chunk

检索精度天壤之别: "番茄多少钱" → 直接命中价格 chunk，0 噪音

Late Chunking (Jina AI 2024):
  不分块！整个文档一起 embedding → 拿到文档级向量 →
  检索时再动态分块 → 每个 chunk 从文档向量中"切出"自己的部分
  
  好处: 不分块保留了全局上下文，但检索时又有 chunk 粒度
```

#### ⑦ HippoRAG — 受海马体启发的记忆检索（2024 顶会论文）

```
人类大脑如何记住事物？
  海马体: 把新记忆跟已有知识关联起来（不是孤立存储）

HippoRAG 模仿这个机制:
  ① 新文档 → LLM 提取关键实体 → 
  ② 在已有知识图谱中找到关联结点 →
  ③ 建立新的连接 → 记忆按照"关系网络"存储

检索时: 不走向量相似度，走图上的"关系路径"
  "张三喜欢吃什么？"
  → (张三) -[偏好]-> (川菜) -[典型菜品]-> (麻婆豆腐、宫保鸡丁)
  → 回答: 麻婆豆腐和宫保鸡丁（可能文档里根本没同时出现过"张三"和"麻婆豆腐"）
  
这种"推理式检索"完全不同于"相似度检索"。
```

### 9.3 全行业技术成熟度一览

```
技术                    成熟度    落地难度   适用于

Query Rewrite           ★★★★★     ⭐      任何 RAG
HyDE                    ★★★★☆     ⭐      长尾问题多时
Step-back Prompting     ★★★☆☆     ⭐⭐    需要背景知识时
Multi-hop Decomposition ★★★☆☆     ⭐⭐⭐   复杂推理问题
Query2Doc               ★★★☆☆     ⭐⭐    召回率不够时
Dense + BM25 + RRF      ★★★★★     ⭐      任何 RAG ← 你有
CrossEncoder Reranker   ★★★★★     ⭐⭐     精度要求高 ← 你有
ColBERT                 ★★★★☆     ⭐⭐⭐⭐  存储够、精度要求极高
SPLADE                  ★★★☆☆     ⭐⭐⭐   想要 BM25 的升级版
RankGPT                 ★★★☆☆     ⭐⭐⭐   不差钱、追求极致精度
GraphRAG                ★★★☆☆     ⭐⭐⭐⭐⭐ 知识密集、需要全局视角
Agentic RAG             ★★★☆☆     ⭐⭐⭐⭐  问题复杂度差异大
Self-RAG / CRAG         ★★★★☆     ⭐⭐     检索质量不稳定时
Proposition Chunking    ★★★☆☆     ⭐⭐⭐   需要最高检索精度
Late Chunking           ★★☆☆☆     ⭐⭐⭐⭐  前沿，生态不成熟
Contextual Retrieval    ★★★★☆     ⭐       Anthropic 主推，简单有效
HippoRAG                ★☆☆☆☆     ⭐⭐⭐⭐⭐ 研究阶段
```

### 9.4 你现在的位置 + 性价比最高的下一步

```
                         你现在         性价比最高的一步
分块      语义分块 ──→  +Contextual Retrieval（加文档标题前缀）
查询      改写+HyDE ──→  +Step-back Prompting（抽象回退）
检索      Dense+BM25+RRF+CrossEncoder ──→ 已经够好了
后处理    无 ──────────→  +CRAG 自检（检索质量门槛）
```

**性价比公式**：`Contextual Retrieval (10行代码) + Step-back (20行代码) + CRAG (30行代码) = 显著提升，不到 100 行`

### 9.5 行业玩家的真实动作

| 谁 | 在干嘛 | 跟你的关系 |
|----|--------|-----------|
| **OpenAI** | 上下文做到 128K → 让 RAG 很多步骤变得多余 | 小知识库可以直接塞 |
| **Anthropic** | Contextual Retrieval + Prompt Caching | 你应该用：加文档标题前缀 |
| **Google** | Gemini 1M+ 上下文 → 想干掉检索 | 大趋势：上下文越大，越不需要检索 |
| **Microsoft** | GraphRAG 开源，知识图谱+LLM | 知识密集型场景的终局方案 |
| **Meta** | ColBERT + 开源 RAG 基准 | 开源界的精度标杆 |
| **Cohere** | 多语言 Reranker + Compass 多跳检索 | 企业级 API 方案 |
| **Jina AI** | Late Chunking + 多向量检索 | 下一代 embedding 方案 |
| **DeepSeek** | 128K 上下文 + Context Caching | 你现在就在用 |

> **一针见血的总结**：你现在在 RAG 技术栈的"黄金平衡点"——不是最先进，但是最成熟、最稳定、最高性价比的组合。往上每爬一级，成本成倍增加，收益边际递减。家务 AI 管家的定位决定了 Dense+BM25+RRF+CrossEncoder 就是正确答案。真要追前沿，GraphRAG 和 Agentic RAG 值得关注，但等生态再成熟一年，配套工具更完善了再上。
