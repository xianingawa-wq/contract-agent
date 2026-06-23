# Contract Agent Agent Memory

本文件是 Codex 在本仓库工作的持久化项目记忆。详细架构以 `docs/architecture.md` 为准；本文件只沉淀高频、需要每次开发都遵守的规则。

## 项目定位

- Contract Agent 是独立的 Python 合同审查智能体运行时，承载合同解析、规则审查、LLM 辅助审查、法律知识 RAG、多智能体编排、合同改写、审计日志和 gRPC 服务。
- Java 后端通过 gRPC 调用本项目；协议定义在 `contract_agent/agent_rpc/proto/agent.proto`，生成代码为 `agent_pb2.py` 和 `agent_pb2_grpc.py`。
- 用户可见能力优先围绕合同审查、合同对话、法律知识检索、合同改写和结构化审计展开。

## 架构边界

- 接口层：`contract_agent/interfaces/`、`contract_agent/agent_rpc/server.py`，负责 CLI、HTTP、gRPC、控制台入口。
- 服务层：`contract_agent/services/`，负责审查、对话、ReAct runtime、解析、分类、抽取、规则引擎、分块等编排逻辑。
- 核心层：`contract_agent/provider/`、`model_config/`、`knowledge/`、`orchestration/`、`agents/`、`memory/`。
- 基础设施层：`contract_agent/runtime/`、`logger/`、`trace/`，负责配置、数据库、schema、审计日志、token 追踪。
- 扩展型包优先遵循 `interface -> service -> impl -> factory` 模式，尤其是 `provider/`、`model_config/`、`knowledge/rag/rerank/`。

## 关键设计决策

- LLM 抽象使用 `typing.Protocol` 风格，避免要求显式继承。
- Provider 使用字符串注册工厂；新增 provider 时要在 factory 中注册清楚，注意运行时拼写风险。
- 配置存在模块级 `settings` 兼容对象；新增代码优先使用 `settings_snapshot()`、`temporary_settings()`、入口级快照或构造注入，减少全局可变状态影响。
- OpenAI provider 优先走 Responses API，异常时回退 Chat Completions；DashScope/Qwen 按 OpenAI 兼容方式处理但不假设支持 Responses。
- 记忆系统分为热、温、冷三层：Redis、PostgreSQL、Vector。
- LLM 输出 JSON 解析目前有正则容错历史，修改相关逻辑时要重点防止误提取非 JSON 大括号。

## 开发约定

- 依赖声明以 `pyproject.toml` 为权威来源；`requirements.txt` 是兼容/历史文件，修改依赖时保持一致性。
- Python 版本要求 `>=3.11`。
- LangChain chain 组合使用 `prompt | llm`。
- Pydantic 使用 `model_dump()` 和 `model_validate()`。
- 可选或重依赖放在方法内部懒加载，避免导入公共 API 时拉起 LangChain、Redis、SQLAlchemy 等重依赖。
- 用户可见消息、prompt、日志使用中文；代码标识符使用英文。
- 所有公开方法应有类型标注。
- 新增公共入口时维护关键包的显式 re-export；不要把 `impl` 私有实现直接暴露成公共 API。

## 常用变更位置

- 新审查规则：编辑 `contract_agent/rulesets/built_in.py`，规则字段包括 `rule_id`、`title`、`severity`、`description`、`risk_domain`、`check_scope`、`applies_to`、`exclusions`、`trigger_keywords`、`suggestion` 等。
- 新 LLM Provider：在 `contract_agent/provider/impl/<provider>/provider.py` 实现 `LLMProvider` 需要的能力，并在 `contract_agent/provider/factory.py` 注册。
- 新智能体：在 `contract_agent/agents/` 增加函数，返回 `AgentOutput`，再接入 supervisor 或 pipeline。
- RAG 检索链路在 `contract_agent/knowledge/rag/`，重排器在 `contract_agent/knowledge/rag/rerank/`。
- 审查入口路由在 `contract_agent/services/review_gateway.py`；多智能体执行编排在 `contract_agent/orchestration/`，包括 supervisor、pipeline、single、events、runtime、task_registry、message_queue。

## 本地环境与验证

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
python -c "from contract_agent.runtime.schema import ensure_runtime_schema; ensure_runtime_schema()"
python -m unittest discover -s tests -v
python -m compileall -q contract_agent tests
```

- 需要法律知识入库时运行 `python -m contract_agent.knowledge.rag.ingest`。
- 若改动 gRPC 协议，检查 proto、生成代码、gRPC servicer 直接调用测试、端口级冒烟测试。
- 当前测试覆盖跨服务真实集成仍有缺口：Milvus、DashScope、PostgreSQL、Redis、gRPC 网络端口级启动与流式 RPC。

## 配置记忆

- 常用 LLM 配置前缀：`LLM_*`、`CHAT_*`、`EMBEDDING_*`、`RERANK_*`。
- 默认 provider 倾向：`LLM_PROVIDER=openai_compatible`，`RERANK_PROVIDER=qwen`。
- 向后兼容别名包括 `QWEN_*` 和 `OPENAI_*`，但用户提示优先使用新的 `CHAT_API_KEY` / `LLM_API_KEY`。
- 向量后端支持 `milvus` / `faiss`；默认 Milvus collection 为 `legal_knowledge_chunks`。

## 技术债务提醒

- 继续避免直接修改模块级 `settings` 兼容对象。
- 新增测试时优先覆盖配置注入、线程安全边界、RAG 检索链路、多智能体路由、gRPC servicer 和公共 API re-export。
- Dockerfile 已是 multi-stage runtime，包含非 root 用户和 gRPC 健康检查；变更部署逻辑时保持这些约束。
- `.env.example` 应覆盖新增环境变量。
