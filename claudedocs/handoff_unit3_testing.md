# 单元三测试移交文档

**移交时间**: 2025-10-27
**实现完成**: Claude
**测试负责**: Codex
**目标**: 完成"三、一致性与反思联动"单元的全面测试验证

---

## 一、实施摘要

### 阶段 3.1：质量评估证据化

**改动文件**:
- `src/agent/domain.py:217-225` - 扩展 `QualityFeedback`，新增 `evidence_refs` 字段
- `src/agent/models.py:122-135` - 扩展 `QualityAssessmentResponse`，新增 `issues` 结构化字段
- `src/agent/evaluators/quality.py:40-62` - 修改 Prompt，要求 LLM 标注证据引用
- `src/agent/evaluators/quality.py:145-193` - 重构 `_build_feedback`，支持新旧格式与证据引用提取
- `src/agent/evaluators/quality.py:137-170` - 增强 `evaluate`，添加证据 ID 验证逻辑
- `src/agent/ai_client.py:682-701` - 更新 Stub 实现，返回包含 `issues` 的新格式

**核心功能**:
1. 质量反馈现在包含证据引用列表（`evidence_refs`）
2. 自动验证证据 ID 的有效性，记录无效引用
3. 生成证据验证快照到 `snapshots/<run_id>/04_quality/slide_XX_evidence_validation.json`
4. 向后兼容旧的 `weaknesses/suggestions` 格式

**验收标准**:
- `QualityFeedback` 对象包含 `evidence_refs` 字段
- 证据验证快照正确记录 `total_refs`, `valid_refs`, `invalid_refs`
- 无效证据 ID 触发警告日志
- Stub 模式和真实模式均正常工作

---

### 阶段 3.2：反思阶段闭环

**改动文件**:
- `src/agent/generators/content.py:109-135` - 增强 `_REFLECTION_PROMPT_TEMPLATE`，明确证据一致性要求
- `src/agent/generators/content.py:609-626` - 修改 `_regenerate`，添加证据变更记录
- `src/agent/generators/content.py:628-662` - 新增 `_validate_evidence_consistency` 辅助方法

**核心功能**:
1. 反思 Prompt 要求保留原始证据引用，禁止臆造数据
2. 检测反思前后的证据 ID 变化（added/removed/retained）
3. 生成证据变更快照到 `snapshots/<run_id>/03_content/slide_XX_reflection_evidence_diff_N.json`
4. 记录是否需要补充新证据（通过 speaker_notes 中的 `[需补充证据]` 标记）

**验收标准**:
- 反思后的幻灯片保留或更新 `metadata['evidence_refs']`
- 证据变更快照包含完整的 diff 信息
- 证据删除或新增触发警告日志
- 反思循环中证据引用完整性得到维护

---

### 阶段 3.3：一致性检查增强

**改动文件**:
- `src/agent/domain.py:236-249` - 扩展 `ConsistencyIssue`，新增 `evidence_refs` 和 `conflicting_evidence_pairs` 字段
- `src/agent/validators/consistency.py:31-49` - 修改 Prompt，要求标注证据 ID
- `src/agent/validators/consistency.py:114-141` - 重构 `_convert_issue`，提取并验证证据引用
- `src/agent/validators/consistency.py:148-193` - 新增 `_augment_with_evidence_conflicts` 启发式证据冲突检测
- `src/agent/validators/consistency.py:85-91` - 增强 `check`，调用证据冲突检测并记录统计信息

**核心功能**:
1. 一致性问题现在包含证据引用和冲突证据对
2. 自动检测应该有证据但缺少引用的问题，记录警告
3. 启发式检测同一证据在不同页面的潜在冲突
4. 日志输出问题总数和包含证据引用的问题数

**验收标准**:
- 一致性报告的 `issues` 中至少 50% 包含 `evidence_refs`（在真实数据上）
- 缺少证据引用的应有证据问题触发警告
- 证据冲突检测能识别同一 ID 但内容不同的情况
- 一致性检查快照包含证据引用信息

---

## 二、测试需求规格

### 单元测试（需新增）

#### 1. `tests/agent/test_quality_evidence.py`

**测试目标**: 验证质量评估的证据引用功能

**必需测试用例**:
```python
def test_quality_feedback_has_evidence_refs()
    """测试 QualityFeedback 对象包含 evidence_refs 字段"""

def test_evidence_validation_with_valid_ids()
    """测试所有证据 ID 均有效的情况"""

def test_evidence_validation_with_invalid_ids()
    """测试包含无效证据 ID 时触发警告"""

def test_evidence_validation_snapshot_generated()
    """测试生成证据验证快照文件"""

def test_build_feedback_with_issues_format()
    """测试从新格式 issues 构建反馈"""

def test_build_feedback_backward_compatibility()
    """测试向后兼容旧的 weaknesses/suggestions 格式"""

def test_missing_evidence_warning()
    """测试缺少证据引用时记录 warning"""
```

**断言重点**:
- `QualityFeedback.evidence_refs` 字段存在且为列表
- 证据验证快照文件路径正确且包含 total_refs/valid_refs/invalid_refs
- 无效证据 ID 出现在 invalid_refs 列表中
- 日志中包含相应的 warning 记录

---

#### 2. `tests/agent/test_reflection_evidence.py`

**测试目标**: 验证反思阶段的证据一致性校验

**必需测试用例**:
```python
def test_validate_evidence_consistency_no_change()
    """测试证据引用无变化的情况"""

def test_validate_evidence_consistency_with_added()
    """测试新增证据引用的情况"""

def test_validate_evidence_consistency_with_removed()
    """测试删除证据引用的情况"""

def test_evidence_diff_snapshot_generated()
    """测试生成证据变更快照文件"""

def test_reflection_prompt_includes_evidence_requirement()
    """测试反思 Prompt 包含证据一致性要求"""

def test_needs_new_evidence_detection()
    """测试检测 [需补充证据] 标记"""

def test_reflection_preserves_evidence_metadata()
    """测试反思后保留原幻灯片的 evidence 元数据"""
```

**断言重点**:
- `_validate_evidence_consistency` 返回结构包含 has_changes/added/removed/retained
- 证据变更快照包含完整的 diff 信息
- speaker_notes 中的 `[需补充证据]` 标记被正确识别
- 日志中包含证据变更的 warning（当 has_changes 为 true 时）

---

#### 3. `tests/agent/test_consistency_evidence.py`

**测试目标**: 验证一致性检查的证据引用和冲突检测

**必需测试用例**:
```python
def test_consistency_issue_has_evidence_refs()
    """测试 ConsistencyIssue 对象包含 evidence_refs 字段"""

def test_convert_issue_extracts_evidence_refs()
    """测试从 LLM 响应中提取证据引用"""

def test_missing_evidence_refs_warning()
    """测试应有证据但缺少引用时触发 warning"""

def test_augment_with_evidence_conflicts()
    """测试启发式证据冲突检测"""

def test_evidence_conflict_detection_same_id_different_content()
    """测试检测同一 ID 但内容不同的证据冲突"""

def test_consistency_check_logs_evidence_stats()
    """测试日志输出证据引用统计信息"""
```

**断言重点**:
- `ConsistencyIssue.evidence_refs` 字段可选且为列表或 None
- 证据冲突检测能识别至少一个冲突案例
- 日志包含"问题数=X（含证据引用=Y）"格式的统计信息
- 缺少证据引用的应有证据问题触发 warning

---

### 集成测试（端到端）

#### 4. `tests/test_workflow_evidence_integration.py`

**测试目标**: 验证完整流程中证据流转的完整性

**必需测试用例**:
```python
def test_evidence_flow_through_full_workflow()
    """测试证据从检索到质量评估再到一致性检查的完整流转"""

def test_evidence_snapshot_files_generated()
    """测试所有证据相关快照文件均被生成"""

def test_reflection_triggered_with_evidence_preservation()
    """测试触发反思时证据引用得到保留"""

def test_consistency_check_references_evidence()
    """测试一致性检查能引用证据进行问题定位"""
```

**断言重点**:
- 快照目录包含 `*_evidence.json`, `*_evidence_validation.json`, `*_evidence_diff_*.json`
- 质量评估、反思、一致性检查三个阶段的证据引用保持连贯
- 端到端运行无 error，仅在预期情况下有 warning
- 生成的 HTML 包含证据元数据（可选增强）

---

## 三、测试数据准备

### 基础数据（Stub 模式）

当前 Stub 实现已支持新格式：
- 质量评估返回包含证据引用的 `issues`（E1, E2）
- 一致性检查返回空的 `issues` 列表（可根据需要扩展）

### 真实数据（可选）

为更全面的测试，建议准备：
1. **多证据文档**: 包含至少 5 个可检索的证据块
2. **冲突证据**: 同一主题但数值/术语不同的证据对
3. **低质量输入**: 触发质量反思的输入文本

**示例**:
```
# docs/test_evidence_conflict.md
## 销售数据

2024年Q1销售额为500万元。

## 财务报告

2024年第一季度销售额达到600万元。
```

---

## 四、测试覆盖率目标

**整体目标**: >85%

**分项目标**:
- `src/agent/evaluators/quality.py`: >90%（核心逻辑）
- `src/agent/generators/content.py`: >80%（反思部分）
- `src/agent/validators/consistency.py`: >85%（新增方法）
- `src/agent/domain.py`: 100%（数据模型）
- `src/agent/models.py`: 100%（数据模型）

**关键路径覆盖**:
- 证据引用提取与验证
- 证据一致性校验
- 证据冲突检测
- 快照文件生成

---

## 五、验收标准总结

### 阶段 3.1 验收标准
- [x] QualityFeedback 包含 evidence_refs 字段
- [x] 证据验证快照正确生成
- [x] 无效证据 ID 触发警告
- [x] Stub 模式返回新格式
- [ ] 单元测试覆盖率 >90%（待 Codex 完成）

### 阶段 3.2 验收标准
- [x] 反思 Prompt 包含证据一致性要求
- [x] 证据变更快照正确生成
- [x] 证据变化触发警告
- [x] `_validate_evidence_consistency` 方法正确实现
- [ ] 单元测试覆盖率 >80%（待 Codex 完成）

### 阶段 3.3 验收标准
- [x] ConsistencyIssue 包含 evidence_refs 字段
- [x] 一致性 Prompt 要求标注证据
- [x] 证据缺失检测触发警告
- [x] 启发式证据冲突检测实现
- [x] 日志输出证据引用统计
- [ ] 单元测试覆盖率 >85%（待 Codex 完成）

---

## 六、运行指令

### 运行单元测试
```bash
source .venv/bin/activate
pytest tests/agent/test_quality_evidence.py -v
pytest tests/agent/test_reflection_evidence.py -v
pytest tests/agent/test_consistency_evidence.py -v
```

### 运行集成测试
```bash
pytest tests/test_workflow_evidence_integration.py -v
```

### 查看测试覆盖率
```bash
pytest --cov=src/agent/evaluators --cov=src/agent/validators --cov=src/agent/generators --cov-report=html
```

### Stub 模式验证
```bash
python main.py --text "测试输入" --model-provider stub --use-stub
```

---

## 七、注意事项

1. **证据 ID 格式**: 统一使用 "E1", "E2" 格式，不要使用 "e1" 或 "evidence_1"
2. **快照验证**: 所有测试应检查快照文件存在性和内容正确性
3. **日志级别**: 证据相关的警告使用 `logger.warning`，统计信息使用 `logger.info`
4. **向后兼容**: 旧格式（weaknesses/suggestions）必须继续工作，不能破坏现有功能
5. **Stub 更新**: 如需修改 Stub 返回格式，务必确保测试数据一致性

---

## 八、问题反馈

测试过程中如遇到问题，请记录：
1. 失败的测试用例名称
2. 预期行为 vs 实际行为
3. 相关日志或错误堆栈
4. 建议的修复方案（可选）

反馈至项目 issue 或直接联系开发者。

---

**移交状态**: ✅ 代码实现完成，准备交接
**下一步**: Codex 完成测试验证并更新 TODO.md
