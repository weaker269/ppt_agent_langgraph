#!/usr/bin/env python3
"""
PPT Agent 项目启动入口

这是一个轻量级的PPT生成智能体。
使用方法：
    python main.py input_file.txt
    python main.py --help
"""

import sys
import os
from pathlib import Path

# 确保项目路径在sys.path中
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入简化版程序
from src.agent.simple_ppt import SimplePPTGenerator

def create_sample_content():
    """创建示例内容文件"""
    sample_content = """# 新能源汽车发展现状与前景

## 引言
新能源汽车作为未来汽车产业的重要发展方向，正在全球范围内快速发展。本报告分析了新能源汽车的现状、技术发展、市场前景等关键问题。

## 新能源汽车市场现状

### 全球市场概况
- 2023年全球新能源汽车销量突破1000万辆
- 中国、欧洲、美国是主要市场
- 市场渗透率持续提升

### 中国市场表现
- 中国新能源汽车销量占全球50%以上
- 政策支持力度持续加大
- 产业链相对完善

## 技术发展趋势

### 电池技术
- 能量密度不断提升
- 充电速度大幅改善
- 成本持续下降

### 智能化技术
- 自动驾驶技术快速发展
- 车联网应用日益丰富
- 人机交互体验提升

## 挑战与机遇

### 主要挑战
- 充电基础设施建设滞后
- 电池安全性问题
- 成本仍然较高

### 发展机遇
- 政策持续支持
- 技术不断突破
- 消费者接受度提高

## 未来展望
预计到2030年，新能源汽车将在全球汽车市场中占据重要地位，技术成熟度和市场接受度将显著提升。
"""

    sample_file = "sample_content.txt"
    with open(sample_file, 'w', encoding='utf-8') as f:
        f.write(sample_content)
    return sample_file

if __name__ == "__main__":
    # 如果没有参数，显示帮助和创建示例
    if len(sys.argv) == 1:
        print("🤖 PPT Agent - 智能PPT生成工具 (简化版)")
        print()
        print("📋 使用方法:")
        print("  python main.py input_file.txt")
        print()

        # 检查是否存在示例文件
        sample_file = "sample_content.txt"
        if not os.path.exists(sample_file):
            print("📝 创建示例内容文件...")
            sample_file = create_sample_content()
            print(f"✅ 示例文件已创建: {sample_file}")

        print(f"💡 快速开始: python main.py {sample_file}")
        print()
        print("ℹ️  当前为简化版本，直接从文本生成PPT，无需API密钥")
        sys.exit(0)

    input_file = sys.argv[1]

    if not os.path.exists(input_file):
        print(f"❌ 文件不存在: {input_file}")
        sys.exit(1)

    try:
        generator = SimplePPTGenerator()
        result = generator.generate_from_file(input_file)

        if result.success:
            print("✅ PPT生成成功!")
            print(f"📄 输出文件: {result.output_file}")
            print(f"📊 幻灯片数量: {result.slides_count}")
            print(f"⏱️ 生成耗时: {result.generation_time:.2f}秒")
            print(f"📈 质量评分: {result.quality_metrics.overall_score:.2f}")
            print("🌐 在浏览器中打开HTML文件即可查看PPT")
        else:
            print(f"❌ 生成失败: {result.error_message}")
            sys.exit(1)

    except Exception as e:
        print(f"❌ 系统错误: {e}")
        sys.exit(1)