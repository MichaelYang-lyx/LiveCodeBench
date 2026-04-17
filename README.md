# LiveCodeBench

## 环境配置

### 安装依赖

推荐使用 [uv](https://github.com/astral-sh/uv) 管理依赖：

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e .
```

也可以用 pip：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 数据集缓存

数据集会自动缓存到项目根目录下的 `data/` 文件夹，首次运行时自动下载。

如果已有离线数据，可以设置 `HF_DATASETS_OFFLINE=1` 跳过网络请求：

```bash
export HF_DATASETS_OFFLINE=1
```

---

## 使用说明

### 结果存储位置

- 生成结果：`output/{model_repr}/{scenario}_{n}_{temperature}.json`
- 评估结果（汇总）：`output/{model_repr}/{scenario}_{n}_{temperature}_eval.json`
- 评估结果（逐题）：`output/{model_repr}/{scenario}_{n}_{temperature}_eval_all.json`
- 缓存文件：`cache/{model_repr}/{scenario}_{n}_{temperature}.json`

其中 `model_repr` 为模型名称，未注册模型（使用 `--model_style`）时与 `--model` 值相同。

---

### 常用参数说明

| 参数 | 说明 |
|------|------|
| `--model` | 模型名称，需在 `lm_styles.py` 中注册，或配合 `--model_style` 使用 |
| `--model_style` | 未注册模型时指定调用风格，如 `OpenAIChat`、`Claude3`、`LLaMa3`、`DeepSeekR1` 等 |
| `--scenario` | 评测场景：`codegeneration` / `testoutputprediction` / `codeexecution` |
| `--release_version` | 数据集版本，如 `release_v5`、`release_v6`、`v5_v6`（跨版本合并） |
| `--n` | 每题生成答案数，`pass@1` 评测用 `1` |
| `--temperature` | 采样温度，默认 `0.2` |
| `--max_tokens` | 最大生成 token 数 |
| `--multiprocess` | API 并发请求数（根据服务端限速调整） |
| `--use_cache` | 启用请求缓存，避免重复调用 |
| `--cache_batch_size` | 缓存批次大小 |
| `--continue_existing` | 跳过已生成的题目，断点续跑 |
| `--continue_existing_with_eval` | 同上，同时复用已有评估结果 |
| `--openai_timeout` | API 请求超时时间（秒），推理模型建议设大 |
| `--evaluate` | 生成完成后自动评估 |
| `--debug` | 只跑前 15 题，用于快速验证配置 |
| `--start_date` / `--end_date` | 按题目发布日期过滤，格式 `YYYY-MM-DD` |

---

### 示例

#### Claude（通过 Anthropic API 或兼容代理）

```bash
export ANTHROPIC_KEY="your-anthropic-api-key"
export ANTHROPIC_BASE_URL="https://your-anthropic-proxy.com"

python -m lcb_runner.runner.main \
    --model claude-4.6-opus \
    --scenario codegeneration \
    --release_version v5_v6 \
    --n 1 \
    --temperature 0.2 \
    --multiprocess 10 \
    --use_cache \
    --cache_batch_size 20 \
    --max_tokens 64000 \
    --continue_existing \
    --openai_timeout 1200 \
    --evaluate
```

#### 自定义 OpenAI 兼容服务（本地部署模型）

未在 `lm_styles.py` 注册的模型，通过 `--model_style` 指定调用风格即可，无需修改代码。

```bash
HF_DATASETS_OFFLINE=1 \
OPENAI_KEY=dummy \
OPENAI_API_BASE=http://10.210.1.23:5163/v1 \
python -m lcb_runner.runner.main \
    --model Qwen3.5-35B-A3B2 \
    --model_style OpenAIChat \
    --scenario codegeneration \
    --release_version v5_v6 \
    --n 1 \
    --temperature 0.2 \
    --multiprocess 1 \
    --use_cache \
    --cache_batch_size 1 \
    --max_tokens 64000 \
    --continue_existing \
    --openai_timeout 1200 \
    --evaluate
```

`--model_style` 可选值（对应 `lm_styles.py` 中的 `LMStyle` 枚举）：

| 值 | 适用场景 |
|----|---------|
| `OpenAIChat` | 标准 OpenAI chat 格式（大多数本地服务） |
| `OpenAIReason` | OpenAI o1/o3 系列推理模型（需在模型名后加 `__low/medium/high`） |
| `Claude3` | Anthropic Claude 3/3.5 |
| `Claude3Thinking` | Claude 3.7+ 带 thinking |
| `LLaMa3` | LLaMA 3 系列 |
| `DeepSeekR1` | DeepSeek R1 及蒸馏模型 |
| `CodeQwenInstruct` | Qwen 系列 |
| `QwQ` | QwQ 推理模型 |
| `Gemini` / `GeminiThinking` | Google Gemini |

---

### 数据集版本

| 版本 | 题目范围 | 题目数 |
|------|---------|--------|
| `release_v1` | 2023-05 ~ 2024-03 | 400 |
| `release_v2` | 2023-05 ~ 2024-05 | 511 |
| `release_v3` | 2023-05 ~ 2024-07 | 612 |
| `release_v4` | 2023-05 ~ 2024-09 | 713 |
| `release_v5` | 2023-05 ~ 2025-01 | 880 |
| `release_v6` | 2023-05 ~ 2025-04 | 1055 |

跨版本合并格式：`v5_v6`（只包含 v5 到 v6 新增的题目）。

---

## Citation

```bibtex
@article{jain2024livecodebench,
  author    = {Naman Jain, King Han, Alex Gu, Wen-Ding Li, Fanjia Yan, Tianjun Zhang, Sida Wang, Armando Solar-Lezama, Koushik Sen, Ion Stoica},
  title     = {LiveCodeBench: Holistic and Contamination Free Evaluation of Large Language Models for Code},
  year      = {2024},
  journal   = {arXiv preprint},
}
```
