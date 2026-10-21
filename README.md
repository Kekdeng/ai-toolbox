# ai-toolbox — AI 小工具集（stdlib-only · offline-first）

把 AI/LLM 应用里反复出现的小问题，做成**可读、可跑、可改**的最小实现——既是工具，也是教学参考。

- **零第三方依赖**：纯 Python 标准库，clone 即用，不 `pip install` 任何东西
- **离线优先**：核心逻辑全部离线可跑；涉及真实 API 的工具一律「离线默认 + 可选联网」
- **自带自测**：每个工具内嵌 `--selftest`，assert 断言核心逻辑
- **单文件**：一个工具一个文件，可读性优先，适合直接抄进自己的项目

## 使用

```bash
python tools/<name>.py --help      # 看用法
python tools/<name>.py --selftest  # 跑内置自测
```

要求：Python 3.10+（无需安装任何包）。

## 工具清单

| 工具 | 用途 | 自测 |
|---|---|---|
| [bpe_tokenizer](tools/bpe_tokenizer.py) | 最小字节级 BPE 分词器（训练/编码/解码，GPT 系分词核心算法） | `python tools/bpe_tokenizer.py --selftest` |
| [sampling](tools/sampling.py) | LLM 解码采样：temperature / top-k / top-p（nucleus）/ 贪心 | `python tools/sampling.py --selftest` |
| [kv_cache_memory](tools/kv_cache_memory.py) | LLM 推理显存估算：权重 + KV cache（GQA 感知，含常见模型预设） | `python tools/kv_cache_memory.py --selftest` |
| [text_chunker](tools/text_chunker.py) | RAG 文本切块：固定窗口+重叠 / 递归分隔符（无损可还原） | `python tools/text_chunker.py --selftest` |
| [json_repair](tools/json_repair.py) | 修复 LLM 输出的近似 JSON：围栏/废话/尾逗号/单引号/注释/智能引号/Python 字面量 | `python tools/json_repair.py --selftest` |
| [pii_masker](tools/pii_masker.py) | 中文 PII 脱敏粗筛：手机号/身份证/邮箱/银行卡/IP → 占位符 | `python tools/pii_masker.py --selftest` |
| [tfidf_similarity](tools/tfidf_similarity.py) | 零模型文本相似度/粗排：TF-IDF（中文按字+bigram）+ 余弦 | `python tools/tfidf_similarity.py --selftest` |
| [ngram_lm](tools/ngram_lm.py) | 字符级 n-gram 语言模型：训练/困惑度/采样生成（加 k 平滑） | `python tools/ngram_lm.py --selftest` |
| [sse_parser](tools/sse_parser.py) | LLM 流式输出解析/回放：SSE 事件 → JSON payload → 增量文本拼接 | `python tools/sse_parser.py --selftest` |
| [token_estimator](tools/token_estimator.py) | 无 tokenizer 的 prompt token/费用粗估（中英比例启发式+价格表快照） | `python tools/token_estimator.py --selftest` |
| [chat_template](tools/chat_template.py) | 消息列表 → 各家 prompt 模板渲染（ChatML/Llama3/Alpaca） | `python tools/chat_template.py --selftest` |
| [edit_distance](tools/edit_distance.py) | Levenshtein 编辑距离 + 确定性对齐路径回放 + 归一化相似度 | `python tools/edit_distance.py --selftest` |
| [topk_rerank](tools/topk_rerank.py) | 多路检索融合重排：RRF/加权 RRF/top-k（同分稳定可复现） | `python tools/topk_rerank.py --selftest` |
| [trie_filter](tools/trie_filter.py) | Trie 敏感词/关键词过滤：最长匹配、逐位置贪心遮罩 | `python tools/trie_filter.py --selftest` |

## 设计约定

1. 标准库 only——任何引入第三方依赖的提案都会被拆成「离线核心 + 可选适配层」；
2. 每个工具的 `--selftest` 必须覆盖：核心函数的正确性、边界输入（空/单元素）、确定性；
3. 数值类工具给出可手算验证的已知答案（如 7B 模型 fp16 权重 ≈ 14 GB）；
4. 随机类工具用固定种子断言统计性质，不做脆弱的精确序列断言。

## License

MIT
