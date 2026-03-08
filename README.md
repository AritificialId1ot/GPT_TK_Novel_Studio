# Novel Studio GUI v7

AI-assisted novel writing workstation with draft workflow, corpus analysis, and structured prompt assets.

Novel Studio is a desktop writing environment for long-form fiction creation built with Python and Tkinter.  
It integrates conversational AI, structured drafting workflows, writing assets, and local corpus analysis into a unified writing system.

Unlike typical chat tools, this application organizes writing projects using **sessions, assets, drafts, and corpus references**, allowing long-term writing projects to maintain style consistency and narrative coherence.

---

# Features

## Conversational Writing

The application provides a persistent conversation interface for interactive writing.

Features include:

- session-based writing projects
- persistent conversation history
- AI response generation
- structured prompt assembly
- conversation export and import

Each message is stored in a database and associated with a specific writing session.

---

# Draft Workspace

The draft workspace implements a structured writing pipeline.

The workflow consists of three stages:

1. Draft generation
2. Draft review
3. Draft revision

Workspace fields:

| Field | Description |
|------|-------------|
| Draft Task | Writing instruction or scene description |
| Current Draft | Generated draft text |
| Review Result | AI critique and suggestions |
| Extra Requirements | Additional revision instructions |
| Review Prompt Template | Prompt template controlling review behavior |

Typical workflow:

```
Write draft task
→ Generate draft
→ Review draft
→ Add modification instructions
→ Revise draft
→ Accept to conversation history
```

All workspace fields are automatically saved.

---

# Asset System

Writing context is controlled through structured assets.

Supported asset types:

| Asset | Purpose |
|------|--------|
| Combo | Tag bundles and thematic combinations |
| Style DNA | Writing style rules |
| Lexicon | Vocabulary preferences |
| Bible | Worldbuilding information |
| Recap | Previous chapter summary |

When enabled, assets are injected into the **system prompt** during generation.

This ensures the model respects project-specific style and narrative constraints.

---

# Corpus Analysis

The system supports scanning a local corpus directory.

Supported file formats:

```
.txt
.md
.markdown
.text
```

For each file the system records:

- file path
- modification time
- file size
- SHA1 hash
- inferred tags
- analysis results

All metadata is stored in SQLite.

---

# Tag Inference

The corpus scanner includes a built-in tag ontology.

Major tag categories include:

- setting
- genre
- content
- characters
- body parts

Tags are inferred by matching keywords in filenames and text content.

Example synonym group:

```
tickling
挠痒
胳肢
呵痒
くすぐり
```

Detected tags are stored for indexing and analysis.

---

# Pixiv Tag Discovery

The system can optionally retrieve related tags from Pixiv.

Process:

1. map internal tags to Pixiv queries
2. fetch Pixiv tag pages
3. extract related tags
4. identify unknown tags
5. classify discovered tags

This helps expand vocabulary and theme coverage of the corpus.

---

# Model Routing

Different tasks use different AI models.

Default routing:

| Task | Model |
|----|------|
| Chat | gpt-5-mini |
| Draft generation | gpt-5.4 |
| Draft review | gpt-5-mini |
| Draft revision | gpt-5.4 |
| Corpus analysis | gpt-5-nano |

Task-specific routing helps balance cost, speed, and generation quality.

---

# System Architecture

The application follows a three-layer architecture.

```
run_app.py
      ↓
GUI Layer (gui_app.py)
      ↓
Backend Layer (core_adapter.py)
```

---

# Project Structure

```
project-root
│
├── run_app.py
├── gui_app.py
├── core_adapter.py
│
├── README.md
└── requirements.txt
```

Description:

| File | Description |
|-----|-------------|
| run_app.py | Application entry point |
| gui_app.py | Tkinter graphical interface |
| core_adapter.py | Backend logic and model interface |

---

# Module Description

## run_app.py

Application entry point.

Responsibilities:

- start the program
- launch the GUI interface

No business logic is implemented here.

---

## gui_app.py

Implements the graphical interface using Tkinter.

Responsibilities include:

- main window layout
- session management
- conversation interface
- draft workspace interface
- corpus management interface
- background task execution
- progress indicator

Main class:

```
App
```

---

## core_adapter.py

Backend service layer.

Responsibilities include:

- database initialization
- schema migration
- session storage
- draft state storage
- model invocation
- system prompt construction
- corpus scanning
- tag inference
- Pixiv tag discovery

Main backend class:

```
BackendService
```

---

# Database Design

SQLite database stores all persistent data.

Main tables:

| Table | Purpose |
|------|--------|
| sessions | writing projects and assets |
| turns | conversation history |
| draft_states | draft workspace state |
| corpus_files | indexed corpus files |
| file_analyses | corpus analysis results |

Example structure:

```
sessions
 ├ combo
 ├ style_dna
 ├ lexicon
 ├ bible
 └ recap

turns
 ├ role
 ├ content
 ├ timestamp
 └ meta

draft_states
 ├ task_text
 ├ draft_text
 ├ review_text
 └ extra_text
```

---

# Prompt Construction

The system prompt is dynamically assembled from enabled assets.

Possible prompt sections:

```
Combo
Style DNA
Lexicon
Bible
Recap
Runtime corpus reference
```

These sections are concatenated to form the final system prompt.

---

# Token Handling

To prevent exceeding model limits, the system truncates long inputs.

Strategy:

```
text_head
...
text_tail
```

For message lists:

```
system prompt preserved
latest messages prioritized
older messages truncated
```

---

# Background Task System

Long operations run in background threads.

Examples:

- model generation
- corpus scanning
- tag analysis

Pipeline:

```
worker thread
↓
result queue
↓
GUI polling
```

This prevents the interface from freezing.

---

# Installation

Requirements:

```
Python 3.9+
```

Dependencies:

```
openai
requests
beautifulsoup4
```

Install dependencies:

```
pip install openai requests beautifulsoup4
```

Tkinter and SQLite are included with standard Python installations.

---

# Running the Application

Start the program:

```
python run_app.py
```

The GUI interface will launch automatically.

---

# Configuration

User configuration is stored in:

```
~/.novel_studio_gui/
```

Example structure:

```
.novel_studio_gui
 ├ ui_settings.json
 └ train_corpus/
```

Database location is determined in the following order:

1. environment variable `NOVEL_STUDIO_DB`
2. program directory
3. working directory
4. user home directory
5. fallback database file

---

# Typical Workflow

Example writing workflow:

1. create a new session
2. add worldbuilding assets (Bible, Style DNA, Lexicon)
3. enable required assets
4. write a draft task
5. generate draft
6. review draft
7. add revision instructions
8. revise draft
9. accept draft into conversation history

---

# Troubleshooting

## Application does not start

Check Python version:

```
python --version
```

Minimum required version:

```
Python 3.9
```

---

## Model responses are empty

Possible causes:

- missing API key
- network connection issues
- input exceeding model limits

Set API key:

```
export OPENAI_API_KEY=your_key
```

---

## Corpus scanning does not detect files

Ensure files are in supported formats:

```
.txt
.md
.markdown
.text
```

---

# Limitations

Current limitations include:

- progress bar shows activity rather than exact percentage
- Pixiv scraping depends on page structure
- Tkinter interface is visually simple
- very long contexts may be truncated

---

# Future Improvements

Possible upgrades include:

- streaming model responses
- embedding-based corpus search
- chapter management system
- improved GUI framework
- project packaging and export

---

# License

This project is intended for research and creative writing use.

Users must ensure compliance with the terms of service of any AI models used with the software.
