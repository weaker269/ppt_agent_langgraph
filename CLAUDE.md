# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a PPT generation agent built on LangGraph that uses a "sliding window" strategy for serial content generation. The system transforms text input into HTML-based presentations using reveal.js, avoiding the complexity of concurrent processing while maintaining content coherence.

## Core Architecture

### Tech Stack
- **Framework**: LangGraph for workflow orchestration and state management
- **AI Models**: OpenAI GPT and Google Gemini support
- **Frontend**: reveal.js for HTML presentations
- **Data Modeling**: Pydantic for type safety and validation
- **Templating**: Jinja2 for HTML template rendering
- **Quality Assessment**: 多维度AI评分和反思优化机制 (Phase2新增)

### Key Innovation 1: Sliding Window Content Generation

The core architectural innovation is in `src/agent/generators/content.py` - the sliding window strategy maintains a summary of the last 3 slides to ensure logical coherence when generating new content. This avoids the state explosion and content fragmentation issues of traditional concurrent approaches.

### Key Innovation 2: Quality Reflection Mechanism (Phase2)

Phase2引入了智能质量反思机制，实现双模式生成系统：
- **初始生成模式**: 基于提示词和资料直接生成内容
- **反思优化模式**: 基于AI质量评分和缺陷分析的迭代优化

**核心特性**:
- 多维度质量评分（逻辑性、相关性、语言质量、视觉布局）
- 85分及格线，最大3次重试机制
- 详细的缺陷分析和优化建议生成
- 无缝集成到滑动窗口生成流程

## Development Commands

### Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env .env.local
# Edit .env.local with your API keys
```

### Running the Application
```bash
# Generate PPT from text
python main.py --text "Your presentation content"

# Generate from file
python main.py --file example_input.txt

# Specify model and theme
python main.py --file input.txt --model google --theme creative

# With verbose logging
python main.py --text "Content" --verbose
```

### Development and Debugging
```bash
# View logs
tail -f logs/ppt_agent_$(date +%Y%m%d).log

# Check results
ls -la results/

# Open generated HTML
open results/presentation_*.html
```

## Architecture Deep Dive

### Workflow Pipeline (LangGraph)
The system uses a 6-node serial pipeline in `graph.py`:
```
Input Validation → Outline Generation → Style Selection → Content Generation → HTML Rendering → Save Results
```

Each node handles errors gracefully and passes state through `OverallState` (Pydantic model).

### State Management Philosophy
- **Serial Processing**: Avoids complex concurrent state synchronization
- **Sliding Window**: Maintains context without infinite state growth
- **Type Safety**: All state managed through Pydantic models in `state.py`

### Content Generation Strategy
- **Outline First**: Text analysis creates structured presentation outline
- **Context Preservation**: Each slide generation includes summary of previous 3 slides
- **Style Intelligence**: AI selects visual themes based on content characteristics
- **HTML Output**: Generates reveal.js presentations with custom CSS themes

## Module Structure

### Generators (`src/agent/generators/`)
- `outline.py`: Analyzes input text and creates presentation structure
- `content.py`: **Core module** - implements sliding window content generation with quality reflection
- `style.py`: Intelligent style theme selection based on content analysis

### Quality Assessment (`src/agent/evaluators/`) - **Phase2新增**
- `quality.py`: Multi-dimensional quality scoring and optimization suggestions
- `QualityEvaluator`: AI-powered quality assessment engine
- `QualityScore`: Comprehensive scoring model with dimension breakdown
- `OptimizationSuggestion`: Structured feedback for content improvement

### State Management (`src/agent/state.py`)
- `OverallState`: Global workflow state with quality reflection tracking
- `SlideContent`: Individual slide data model with quality metrics
- `SlidingSummary`: Context preservation for sliding window strategy
- `PresentationOutline`: Structured presentation planning

### Rendering (`src/agent/renderers/`)
- `html.py`: Converts content to reveal.js HTML presentations
- `templates/`: Jinja2 templates with multiple layout options

### Workflow (`src/agent/graph.py`)
- `PPTAgentGraph`: Main workflow orchestrator with integrated quality checks
- Node implementations for each pipeline stage
- Error handling and state persistence

## Key Design Decisions

### Why Serial vs Concurrent?
Traditional concurrent approaches suffer from:
- State synchronization complexity
- Content fragmentation between parallel branches
- Difficulty maintaining logical flow

The sliding window strategy provides:
- Guaranteed content coherence
- Simplified state management
- Better quality control

### Why HTML vs PowerPoint?
- **Flexibility**: HTML+CSS provides unlimited styling possibilities
- **Modern Features**: Interactive elements, responsive design, animations
- **Cross-platform**: Browser-native, no special software required
- **Extensibility**: Easy integration of charts, multimedia, custom components

### Sliding Window Implementation
- **Window Size**: Default 3 slides (configurable via SLIDING_WINDOW_SIZE)
- **Summary Strategy**: Extracts main message and key concepts from each slide
- **Context Passing**: Provides simplified summary of recent content to new slide generation

## Configuration

The `.env` file contains extensive configuration options:
- AI model settings (providers, timeouts, temperature)
- Generation parameters (window size, quality thresholds)
- Style themes and customization
- Output and logging preferences
- Performance and debugging options
- **Quality reflection settings (Phase2)**:
  - `ENABLE_QUALITY_REFLECTION=true`: Enable/disable quality reflection mechanism
  - `QUALITY_THRESHOLD=85`: Quality score threshold (0-100)
  - `MAX_REFLECTION_RETRY=3`: Maximum retry attempts per slide
  - `REFLECTION_DIMENSIONS=logic,relevance,language,layout`: Assessment dimensions
  - Dimension weights for customized scoring criteria

## Extension Points

### Adding New Slide Types
1. Extend `SlideType` enum in `state.py`
2. Add generation logic in `content.py`
3. Update HTML templates in `renderers/html.py`

### Adding New Themes
1. Add configuration in `generators/style.py` → `_load_style_configurations()`
2. Extend CSS generation logic
3. Optionally add specialized templates

### Integrating New AI Models
1. Update `_initialize_model()` methods in generator classes
2. Add provider configuration in `.env`
3. Test compatibility and adjust prompts if needed

## Quality and Performance

### Error Handling
- Graceful degradation at each pipeline stage
- Fallback mechanisms for failed AI calls
- Comprehensive logging for debugging

### Performance Optimizations
- Configurable sliding window size (balance quality vs performance)
- Token usage monitoring and optimization
- Parallel tool calls where safe (within single operations)

This project demonstrates how to balance architectural complexity with functionality in AI content generation systems, showcasing LangGraph's capabilities for creative applications.

## Phase 2 Quality Reflection System

### Dual-Mode Generation Architecture

The system now supports two generation modes:

1. **Initial Generation Mode** (原有流程)
   - Direct content generation based on prompts and source material
   - Used for first-pass slide creation

2. **Reflection Optimization Mode** (Phase2新增)
   - AI-driven quality assessment with multi-dimensional scoring
   - Iterative improvement based on specific feedback
   - Automatic retry with optimization suggestions

### Quality Assessment Framework

**Scoring Dimensions**:
- **Logic (30%)**: Content structure and reasoning coherence
- **Relevance (25%)**: Alignment with presentation theme and objectives  
- **Language (25%)**: Clarity, professionalism, and linguistic quality
- **Layout (20%)**: Information hierarchy and visual organization

**Quality Control**:
- Threshold: 85/100 points for acceptance
- Maximum retries: 3 attempts per slide
- Detailed feedback generation for optimization
- Fallback mechanism for edge cases

### Usage Examples

```bash
# Test quality reflection with sample content
python test_quality_reflection.py

# Generate presentation with quality reflection enabled (default)
python main.py --text "Your content" --verbose

# Disable quality reflection for faster generation
# Set ENABLE_QUALITY_REFLECTION=false in .env
python main.py --file input.txt
```

### Performance Monitoring

The system tracks quality metrics:
- Individual slide quality scores
- Reflection attempt counts  
- Average quality improvements
- Processing time impact

### Integration Benefits

- **Quality Assurance**: Automated content quality validation
- **Consistency**: Maintains coherence across all slides
- **Efficiency**: Reduces manual revision needs
- **Scalability**: Handles varying content quality inputs