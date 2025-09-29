# 代码风格与约束
- 遵循 PEP 8，使用四空格缩进；变量与函数采用 snake_case；枚举使用 UPPER_CASE。
- 领域层统一使用 Pydantic BaseModel/Enum，新增结构需在 `domain.py` 扩展并添加对应测试。
- CLI/日志输出保持中文信息；新增注释与文档需使用中文描述。
- LangGraph 工作流节点按职责划分在 `generators/`、`evaluators/`、`validators/`、`renderers/` 子模块，保持模块化拆分。