# Aetheria

多智能体安全评估流水线的轻量实现，涵盖 Python 评估器、FastAPI BFF 以及基于 Vue 3 的操作台 UI。该项目复用原始 Aetheria 数据集与输出格式，聚焦于 Azure OpenAI 模型、Top-K 检索式 RAG 与可视化审阅体验，方便快速集成到内部工具链或产品 Demo 中。

## 仓库结构

| 路径 | 说明 |
| --- | --- |
| `aetheria_simple/` | Python 版简化评估器：多智能体图 (`graph.py`)、角色定义 (`agents.py`)、配置与提示 (`config.py`, `prompts.py`)、命令行入口 (`main.py`)。 |
| `aetheria_simple/bff/` | FastAPI 后端（`app.py`），通过 `ReviewService` 暴露 `/api/review` 供前端调用，可并发处理文本 + Base64 图片请求。 |
| `aetheria_simple/scripts/` | 维护工具：构建/再平衡案例库、生成 Chroma 向量库、提取误判样本等。 |
| `aetheria_simple/case_libraries/` | 预制案例库 JSON，支持 Supporter/RAG 模块直接消费。 |
| `aetheria_simple/chroma_db/` | 默认 Chroma 向量数据库持久化目录（可用脚本重建）。 |
| `frontend/` | Vue 3 + Vite 前端，含审核表单、RAG 结果、样例展示等视图。 |
| `result/` (运行生成) | CLI 评估输出的 JSON 报告与 CSV 详单。 |
| `logs/` (运行生成) | `ReviewService` 记录的单次审核日志与模型对话。 |

## 运行前提

- **Python** 3.10+，建议使用虚拟环境（`venv`/`uv`/`conda` 均可）。
- **Node.js** 20.19+（与 `frontend/package.json` 的 `engines` 对齐）、`npm` 10+。
- **Azure OpenAI** 资源，至少包含 GPT-4o/GPT-4o mini 与 text-embedding-3-large（或自定义部署映射）。
- 可访问的 **Chroma 持久化目录**（默认 `aetheria_simple/chroma_db`）。首次使用可通过脚本构建。

## 安装步骤

```bash
# 1. Python 依赖
cd aetheria_simple
python -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install fastapi uvicorn[standard] langchain langchain-openai \
            langchain-community chromadb openai python-dotenv tqdm

# 2. 前端依赖
cd ../frontend
npm install
```

> 根据需要可将 Python 依赖写入自定义 `requirements.txt`/`pyproject.toml` 以便团队共享。

## 环境变量

所有 Python 端模块会自动加载根目录下的 `.env`（通过 `python-dotenv`），同时支持以下键：

### 必填

| 变量 | 备用名 | 说明 |
| --- | --- | --- |
| `AETHERIA_SIMPLE_AZURE_ENDPOINT` | `AZURE_ENDPOINT` | Azure OpenAI 终端地址（https://...openai.azure.com/）。 |
| `AETHERIA_SIMPLE_API_KEY` | `API_KEY`, `AZURE_API_KEY` | Azure OpenAI API Key。 |

### 可选

| 变量 | 用途 | 默认 |
| --- | --- | --- |
| `AETHERIA_SIMPLE_API_VERSION` | Azure OpenAI API 版本 | `2024-12-01-preview` |
| `AETHERIA_SIMPLE_SUPPORTER_MODEL` 等（`STRICT/LOOSE/ARBITER`） | 指定各角色模型 | `gpt-4o-mini` / `gpt-4o` |
| `AETHERIA_SIMPLE_RAG_TOP_K` | Supporter 检索案例数量 | `3` |
| `AETHERIA_SIMPLE_ROUNDS` | 辩论轮次 | `2` |
| `AETHERIA_SIMPLE_EMBEDDING_MODEL` | 案例库嵌入模型 | `text-embedding-3-large` |
| `AETHERIA_SIMPLE_CHROMA_PERSIST_DIR` | Chroma 持久化目录 | `./aetheria_simple/chroma_db` |
| `AETHERIA_SIMPLE_CHROMA_COLLECTION` | 默认集合名 | `usb_only_img_case_library` |
| `AETHERIA_SIMPLE_CASE_LIBRARY_PATH` | Supporter 案例库 JSON | `./aetheria_simple/case_libraries/default_case_library.json` |
| `AETHERIA_SIMPLE_DEPLOYMENT_MAP` | 模型→部署 JSON 映射 | identity |
| `AETHERIA_SIMPLE_DEPLOYMENT_<MODEL>` | 单模型部署 ID 覆盖 | — |
| `AETHERIA_SIMPLE_ENABLE_SUPPORTER/STRICT/LOOSE` | 打开/关闭单个角色 | `True` |

前端另可在 `frontend/.env` 设置 `VITE_API_BASE_URL=http://localhost:8000` 指向 BFF。

## 使用方式

### 1. 命令行批量评估

```bash
cd aetheria_simple
python -m aetheria_simple.main \
  --dataset /path/to/usb_text_img_relabeled.json \
  --limit 200 --workers 8 --skip 0
```

- 任务完成后会在 `result/` 写入 `*.json` 汇总与 `*_details.csv` 详单（参见 `evaluate.py`）。
- 数据集字段映射可通过 `aetheria_simple/data_configs.py` 的预设（文字/图像/纯文本）定制。

### 2. FastAPI BFF

```bash
uvicorn aetheria_simple.bff.app:app --host 0.0.0.0 --port 8000 --reload
```

- `POST /api/review`：参见 `aetheria_simple/bff/app.py` 与 `services/review_service.py`。`input_2` 支持 Base64 图像，服务会在 `logs/` 保存每次推理的对话及 RAG 结果。
- `GET /health`：健康检查。

### 3. Vue 评估面板

```bash
cd frontend
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

- 默认监听 `5173` 端口，见 `frontend/src/App.vue`。
- UI 包含「审核工作台」与「样例展示」两种视图，实时展示模型得分、RAG 命中案例、辩手轮次曲线等。

## 案例库与向量数据库

1. **构建/维护案例库**  
   - `python aetheria_simple/scripts/build_balanced_case_library.py`：融合多数据源并平衡标签分布。  
   - `python aetheria_simple/scripts/rebalance_dataset.py`：根据策略重抽样。  
   - `python aetheria_simple/scripts/case_maintainer.py`：增删改单条案例的元数据。

2. **构建 Chroma 向量库**  
   ```bash
   python aetheria_simple/scripts/build_database.py \
     --library-path aetheria_simple/case_libraries/default_case_library.json \
     --persist-dir aetheria_simple/chroma_db \
     --collection-name safety_cases_default
   ```
   运行结束后，Supporter 会直接从新的集合中检索相似案例并生成 `background_info`。

## 日志与排障

- **CLI 输出**：进度由 `tqdm` 展示，最终指标（准确率、召回、F1）与配置摘要会写入 `stdout`，详情写入 `result/`。
- **BFF/服务端日志**：`ReviewService` 默认写入 `logs/<request_id>.jsonl`，含所有消息（`messages` 字段）与 RAG 细节，便于复现问题。
- **常见问题**  
  - `Chroma collection not found`：确认 `AETHERIA_SIMPLE_CHROMA_PERSIST_DIR`、`AETHERIA_SIMPLE_CHROMA_COLLECTION` 与构建脚本保持一致。  
  - `Vision model is not configured`：当 `input_2` 为图像时需设置 `AETHERIA_SIMPLE_DEPLOYMENT_MAP` 或 `AETHERIA_SIMPLE_DEPLOYMENT_GPT_4O` 指向可用的多模态部署。
  - Azure 429/内容策略拦截会在 CLI 中标记为 `api_error`，BFF 会返回 500，需检查速率限制或输入内容。

## 开发提示

- 可在 `aetheria_simple/prompts.py` 中调整角色语气或输出格式，以快速实验不同的评估策略。
- `SimpleRunConfig`（`config.py`）支持通过环境变量热切换模型、RAG Top-K 与辩手开关，便于做消融实验。
- 若需扩展前端字段，可在 `frontend/src/services/reviewService.js` 中更新响应 Schema，并同步修改组件。

欢迎根据团队需求扩展脚本、补充测试或将依赖固化为内部制品库。
