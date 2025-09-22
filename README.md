# PPT Agent - 智能PPT生成工具

一个基于Python的轻量级PPT生成工具，采用模块化架构设计，可以将Markdown文本转换为精美的HTML演示文稿。

## 功能特性

- 📝 **Markdown转PPT**: 支持标准Markdown语法，自动识别标题和内容结构
- 🏗️ **模块化架构**: 采用Pydantic数据模型、分层设计，易于扩展和维护
- 🎨 **主题系统**: 支持多种主题样式，使用模板系统生成精美演示文稿
- 📊 **质量评估**: 内置质量检查机制，提供完整性、一致性和清晰度评分
- 📈 **性能监控**: 详细的生成报告，包含耗时统计和幻灯片数量
- 🔍 **日志系统**: 完整的日志记录，便于调试和追踪问题
- 🖱️ **交互导航**: 支持键盘和鼠标导航，带进度条显示
- 📱 **响应式设计**: 自适应不同屏幕尺寸，完美兼容各种设备

## 项目架构

```
ppt_agent_langgraph/
├── main.py                 # 主程序入口
├── sample_content.txt      # 示例内容文件
├── requirements.txt        # 项目依赖
├── results/               # 生成的PPT文件目录
├── logs/                  # 日志文件目录
├── src/
│   └── agent/
│       ├── __init__.py    # 包初始化文件
│       ├── simple_ppt.py  # 核心PPT生成器
│       ├── state.py       # 数据模型定义(Pydantic)
│       ├── prompts.py     # 提示词模板和解析器
│       ├── util.py        # 工具函数和日志系统
│       ├── html_renderer.py # HTML模板渲染器
│       └── graph.py       # LangGraph工作流(扩展版本)
└── README.md              # 项目文档
```

## 架构组件详解

### 核心模块

1. **state.py - 数据模型层**
   - 使用Pydantic进行数据验证
   - 定义幻灯片、章节、质量指标等核心数据结构
   - 提供类型安全和数据完整性保证

2. **prompts.py - 内容解析层**
   - Markdown结构解析器
   - 内容分块和格式化工具
   - 主题样式模板系统

3. **util.py - 工具服务层**
   - 统一日志管理系统
   - 文件操作和路径管理
   - 质量检查和内容处理工具

4. **simple_ppt.py - 核心生成器**
   - 集成所有架构组件
   - 提供完整的PPT生成流程
   - 支持质量评估和错误处理

### 设计原则

- **单一职责**: 每个模块负责特定功能
- **依赖注入**: 组件间松耦合设计
- **类型安全**: 全面使用Pydantic类型验证
- **可扩展性**: 支持主题、模板和功能扩展
- **错误处理**: 完善的异常处理和日志记录

## 快速开始

### 1. 安装依赖

```bash
# 确保Python 3.8+已安装
pip install -r requirements.txt
```

### 2. 运行示例

```bash
# 使用内置示例内容
python main.py

# 使用自定义文件
python main.py your_content.txt
```

### 3. 查看结果

程序会显示详细的生成报告：

```
✅ PPT生成成功!
📄 输出文件: results/sample_content_20250922_165227.html
📊 幻灯片数量: 6
⏱️ 生成耗时: 0.00秒
📈 质量评分: 0.91
🌐 在浏览器中打开HTML文件即可查看PPT
```

## Markdown格式规范

### 基本结构

```markdown
# 主标题 (生成封面页)

## 章节标题 (生成内容页)
章节描述内容

### 子标题 (页面内小标题)
- 列表项1
- 列表项2
- 列表项3

## 下一章节
更多内容...
```

### 高级功能

- **自动分页**: 长内容会自动分割为多页
- **智能格式化**: 自动识别列表、标题和普通文本
- **内容清理**: 自动移除多余空行和格式不一致

## 生成的PPT特性

### 视觉设计
- 🎨 支持多种主题 (professional, simple)
- 📝 微软雅黑字体，优秀中文显示效果
- 🎯 卡片式布局，圆角阴影设计
- 📊 列表项使用播放按钮图标

### 交互功能
- ⌨️ **键盘导航**:
  - `→` / `空格`: 下一页
  - `←`: 上一页
- 🖱️ **鼠标导航**: 点击底部按钮
- 📊 **进度显示**: 顶部进度条和右上角页码
- 🎯 **响应式**: 自适应不同屏幕尺寸

### 质量保证
- **完整性检查**: 确保内容完整表达
- **一致性验证**: 保持样式和结构统一
- **清晰度评估**: 评估内容表达的清晰程度
- **综合评分**: 0-1范围内的质量总分

## 高级用法

### 自定义主题

```python
from src.agent.simple_ppt import SimplePPTGenerator

# 使用不同主题
generator = SimplePPTGenerator(theme="simple")
result = generator.generate_from_file("input.txt")
```

### 批量处理

```bash
# 处理多个文件
for file in *.txt; do
    python main.py "$file"
done
```

### 质量阈值设置

```python
# 设置质量阈值
generator = SimplePPTGenerator(quality_threshold=0.9)
result = generator.generate_from_file("input.txt")

if result.quality_metrics.overall_score < 0.8:
    print("⚠️ 质量分数较低，建议优化内容")
```

## 技术特性

### 数据验证
- 使用Pydantic进行严格的类型检查
- 自动数据清理和格式化
- 完整的错误信息和调试支持

### 性能监控
- 详细的生成时间统计
- 内存使用优化
- 支持大文件处理（自动分页）

### 日志系统
- 文件和控制台双重输出
- 按日期自动轮转日志文件
- 支持不同级别的日志记录

## 故障排除

### 常见问题

**Q: 生成的HTML文件无法正常显示？**
A: 确保使用现代浏览器(Chrome/Firefox/Safari)，检查日志文件获取详细错误信息。

**Q: 质量评分偏低怎么办？**
A: 检查Markdown格式是否规范，确保内容结构清晰，避免过长的段落。

**Q: 如何查看详细日志？**
A: 查看 `logs/` 目录下的日志文件，包含完整的生成过程记录。

### 开发调试

```python
# 查看生成结果详情
result = generator.generate_from_file("input.txt")
print(f"质量指标: {result.quality_metrics}")
print(f"错误信息: {result.error_message}")
```

## 性能指标

- **生成速度**: ~2000字/秒
- **文件大小**: 生成的HTML约50-100KB
- **内存占用**: <50MB
- **支持长度**: 支持任意长度文档(自动分页)
- **质量评分**: 平均0.85-0.95分

## 扩展计划

### 已完成 ✅
- [x] 模块化架构设计
- [x] Pydantic数据模型
- [x] 质量评估系统
- [x] 日志记录机制
- [x] 主题系统
- [x] 自动分页功能

### 计划中 🚧
- [ ] LangGraph完整工作流
- [ ] 图表支持 (ECharts集成)
- [ ] 更多主题模板
- [ ] 导出PDF功能
- [ ] 批量处理界面
- [ ] 在线编辑器

## 许可证

本项目采用MIT许可证。

## 贡献指南

欢迎提交Issue和Pull Request！

1. Fork项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

## 支持与反馈

- 📧 查看日志文件进行问题诊断
- 🐛 通过GitHub Issues报告问题
- 📖 查看代码注释了解实现细节

---

*PPT Agent - 轻量级架构，专业级品质* 🚀