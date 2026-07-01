# Contract Agent

简体中文 | [English](README.md)

Contract Agent 是一个用于合同审查的 Python Agent 运行时。它可以解析合同文件，执行本地规则审查，结合 LLM 补充风险解释和修改建议，从内置法律知识库检索参考依据，并通过 CLI、HTTP/FastAPI 和 gRPC 对外提供服务。

该仓库定位为一个独立的合同审查 Agent 服务：本地可以用于审查 demo，部署时可以通过既有 gRPC 协议接入后端系统。

## 快速启动

需要 Python 3.11+。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

创建本地运行配置：

```bash
mkdir -p .run
cp config.example.yaml .run/config.yaml
```

编辑 `.run/config.yaml`，按需填写 chat、embedding、rerank 模型的 API key。生产或部署环境也可以通过环境变量覆盖敏感配置和服务地址。

启动交互式本地控制台：

```bash
contract-agent demo
```

通过 CLI 执行合同审查：

```bash
contract-agent review ./contract.txt --type purchase --side buyer
contract-agent review ./contract.txt --format json
```

启动 gRPC 服务：

```bash
contract-agent-grpc
```

默认 gRPC 监听地址是 `127.0.0.1:50051`。可以在 `.run/config.yaml` 中修改，也可以用 `AGENT_GRPC_HOST` 和 `AGENT_GRPC_PORT` 覆盖。

## 配置

项目采用 YAML-first 的运行配置方式：

- `config.example.yaml`：提交到仓库的示例配置。
- `.run/config.yaml`：本地运行配置，已被 git ignore。
- `.run/cli_profile.yaml`：CLI demo 初始化向导生成的本地 profile，已被 git ignore。
- 环境变量：用于部署环境覆盖密钥、模型地址、服务地址等。

常见模型环境变量：

```bash
export LLM_PROVIDER=openai_compatible
export LLM_API_KEY=...
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_CHAT_MODEL=gpt-4.1
export LLM_EMBEDDING_MODEL=text-embedding-3-large
```

默认示例配置兼容 DashScope/Qwen 风格的 OpenAI-compatible 接口。旧的 `QWEN_*` 环境变量仍然作为兼容别名支持。

## 包架构

```text
contract_agent/interfaces/       CLI 和 HTTP/FastAPI 入口
contract_agent/agent_rpc/        gRPC 服务、protobuf 绑定和 Docker 入口
contract_agent/config/           YAML 加载、环境变量覆盖、AppContext 注入
contract_agent/runtime/          数据库 schema 和 SQLAlchemy session 工具
contract_agent/parser/           合同文件加载、转换、Markdown 解析和 clause chunks
contract_agent/review/           本地审查门面、规则模型、报告渲染
contract_agent/rulesets/         内置合同审查规则定义
contract_agent/services/         应用服务：review、chat、规则引擎、gateway
contract_agent/schemas/          Pydantic 请求和响应模型
contract_agent/provider/         LLM、embedding、结构化输出、tool-call provider 抽象
contract_agent/knowledge/        法律知识持久化、RAG、向量库、rerank
contract_agent/agents/           reviewer、editor、parser、risk checker、legal reference 等角色
contract_agent/orchestration/    多 Agent 协议、supervisor、runtime、pipeline 事件
contract_agent/memory/           Agent workflow 的 hot/warm/cold memory store
contract_agent/logger/           组件日志和结构化审计日志
contract_agent/constants/        LLM 和 Agent prompt 常量
contract_agent/trace/            token 使用量估算和 trace 汇总
```

顶层辅助目录：

```text
knowledge/          内置法律知识输入和 FAISS 资产
proto/              protobuf 源协议
picture/            架构图和包视图
tests/              单元测试和集成风格测试
```

## 审查流程

服务化审查主链路如下：

1. 输入归一化，支持纯文本、上传文件 bytes、本地文件路径。
2. `contract_agent/parser/` 将支持的文件转换为 Markdown 和结构化 ParsedDocument。
3. `ContractClassifier` 检测或归一化合同类型。
4. `ContractExtractor` 抽取基础合同字段。
5. `RuleEngine` 执行 `contract_agent/rulesets/` 中的本地规则。
6. `contract_agent/knowledge/` 从向量库检索相关法律依据，并按配置执行 rerank。
7. `LLMReviewer` 补充风险解释和建议。
8. `ReviewService` 返回 summary、抽取字段、风险项、报告文本、参考依据和 token trace。

CLI 的 `review` 命令也走同一条服务链路，因此完整审查需要可用的 LLM 和知识库配置。

## Parser 设计

Parser 包采用分层设计：

```text
ParserSource
  -> converter backend
  -> MarkdownDocument
  -> MarkdownParsedService
  -> ParsedDocument
  -> clause chunks / tables / semantic graph / serializers
```

支持的文件后缀由 `parser.allowed_suffixes` 配置；默认支持 `.txt`、`.docx`、`.pdf`、`.md`、`.html`、`.csv`、`.xlsx` 等输入。转换后端由 `ParserBackendRouter` 选择，默认启用 `docling` 和 `builtin`。

## Knowledge 与 RAG

仓库内置了一个小型法律知识库：

```text
knowledge/laws/民法典.txt
knowledge/ingested/laws_chunks.jsonl
knowledge/ingested/laws_faiss/index.faiss
knowledge/ingested/laws_faiss/index.pkl
knowledge/cases/retrieval_recall_gold_seed_50.jsonl
```

默认检索使用 `knowledge/ingested/laws_faiss` 下的本地 FAISS 资产。配置中也保留了 Milvus 连接项，供需要外部向量库的部署使用。

检索相关配置项：

- `retrieval.enable_hybrid`
- `retrieval.enable_rerank`
- `retrieval.fetch_k`
- `retrieval.final_k`
- `vector_store.backend`
- `vector_store.knowledge_vector_store_dir`

## 服务入口

CLI：

```bash
contract-agent demo
contract-agent config
contract-agent review ./contract.txt --type purchase --side buyer
```

gRPC：

```bash
contract-agent-grpc
```

HTTP/FastAPI：

最小 HTTP 接口位于 `contract_agent/interfaces/http.py`，作为同一服务层之上的轻量适配。

## 测试与质量检查

提交前建议运行：

```bash
python -m ruff format --check contract_agent tests
python -m ruff check contract_agent tests
python -m unittest discover -s tests -v
```

测试覆盖 parser 行为、包边界、配置加载、审查规则、RAG 检索和 rerank、gRPC 服务、runtime schema、审计日志和 CLI 流程。

## 审计日志与 Token Trace

服务化审查流程会向 `.run/audit.jsonl` 写入结构化 JSONL 审计事件，包括审查开始、parser 活动、规则执行完成、LLM 增强、审查完成和失败信息。

审查响应中也包含 `trace` 对象，用于展示估算的输入、输出和总 token 使用量。当前实现使用本地字符数估算，因此即使模型 provider 没有返回 token accounting，也能看到大致用量。
