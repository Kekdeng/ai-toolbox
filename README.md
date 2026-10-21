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

## 设计约定

1. 标准库 only——任何引入第三方依赖的提案都会被拆成「离线核心 + 可选适配层」；
2. 每个工具的 `--selftest` 必须覆盖：核心函数的正确性、边界输入（空/单元素）、确定性；
3. 数值类工具给出可手算验证的已知答案（如 7B 模型 fp16 权重 ≈ 14 GB）；
4. 随机类工具用固定种子断言统计性质，不做脆弱的精确序列断言。

## License

MIT
