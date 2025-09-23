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

### Key Innovation: Sliding Window Content Generation

The core architectural innovation is in `src/agent/generators/content.py` - the sliding window strategy maintains a summary of the last 3 slides to ensure logical coherence when generating new content. This avoids the state explosion and content fragmentation issues of traditional concurrent approaches.

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
- `content.py`: **Core module** - implements sliding window content generation
- `style.py`: Intelligent style theme selection based on content analysis

### State Management (`src/agent/state.py`)
- `OverallState`: Global workflow state with all generation data
- `SlideContent`: Individual slide data model
- `SlidingSummary`: Context preservation for sliding window strategy
- `PresentationOutline`: Structured presentation planning

### Rendering (`src/agent/renderers/`)
- `html.py`: Converts content to reveal.js HTML presentations
- `templates/`: Jinja2 templates with multiple layout options

### Workflow (`src/agent/graph.py`)
- `PPTAgentGraph`: Main workflow orchestrator
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