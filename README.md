# Project Hina 🌸

> An anime-inspired desktop assistant designed as a lightweight ambient desktop companion.

Project Hina is a Python-based desktop assistant that combines desktop automation, voice interaction, natural command parsing, and a modern popup interface into a single assistant-oriented system.

Unlike traditional chatbot applications, Hina is designed to function as a background desktop presence capable of assisting with everyday tasks through natural interaction.

The long-term vision of the project is to evolve Hina from a lightweight desktop utility into a fully embodied anime assistant with memory, intelligent reasoning, expressive UI, and eventually Live2D or 3D avatar integration.

---

# ✨ Features

## 🖥️ Desktop Assistant Features

### Application Control

* Open applications
* Close applications
* Restart applications
* Alias support for common apps

Examples:

* `open chrome`
* `launch vscode`
* `close spotify`
* `restart notepad`

---

### 📂 File Management

* Find files by name
* Find folders by name
* Search and open files
* Smart file/app fallback behavior

Examples:

* `find my notes.pdf`
* `open org.pdf`
* `find project_hina folder`

---

### ⚙️ System Utilities

* Tell current time
* Tell current date
* Battery status
* Disk usage

Examples:

* `what time is it`
* `check battery`
* `disk usage`

---

### 🧮 Productivity Utilities

* Calculator
* Timer system
* Countdown system

Examples:

* `calculate 45*9`
* `timer 60`
* `countdown 5`

---

### 🌸 Conversational Layer

* Greetings
* Personality responses
* Startup messages
* Goodbye messages
* Utility descriptions

Examples:

* `hello`
* `who are you`
* `thanks`

---

### 🔊 Voice Output

* Neural text-to-speech responses
* Real-time spoken replies
* Emoji-cleaned speech pipeline
* Integrated GUI + voice workflow

Powered by:

* `edge-tts`
* `pygame`

---

### 🪟 Popup GUI Assistant

* Modern popup interface
* Hotkey-based visibility toggle
* Always-on-top assistant window
* Lightweight workflow
* Background-assistant behavior

Current hotkey:

* `CTRL + H`

---

# 🧠 Project Philosophy

Project Hina is intentionally designed around the idea of:

> “Ambient desktop presence.”

The project is not intended to become a traditional chatbot application.

Instead, the goal is to create:

* a lightweight desktop companion
* an assistant-oriented workflow
* an anime-inspired personality
* a utility-focused assistant
* a future AI companion platform

---

# 🏗️ Architecture Overview

## System Flow

```text
User Input
    ↓
parser.py
    ↓
actions.py
    ↓
voice.py
    ↓
gui.py
```

The project uses a modular architecture to separate:

* parsing
* execution
* speech
* interface

This makes the system easier to scale and maintain.

---

# 📁 Project Structure

```text
project_hina/
│
├── gui.py
│   Main popup GUI interface
│   Handles:
│   - UI rendering
│   - command routing
│   - hotkeys
│   - popup behavior
│   - assistant responses
│
├── parser.py
│   Natural language normalization layer
│   Converts human-friendly phrases into executable commands
│
├── actions.py
│   Core desktop automation engine
│   Handles:
│   - app control
│   - file search
│   - utilities
│   - timers
│   - system functions
│
├── voice.py
│   Neural voice synthesis system
│   Uses edge-tts for speech generation
│
├── assets/
│   UI assets and future avatar resources
│
├── memory/
│   Future persistent memory systems
│
├── requirements.txt
│   Python dependencies
│
├── .gitignore
│   Git exclusions
│
└── README.md
    Project documentation
```

---

# 🛠️ Tech Stack

## Core

* Python

## GUI

* CustomTkinter

## Voice

* edge-tts
* pygame

## System Interaction

* keyboard
* subprocess
* psutil
* os

---

# 🚀 Installation

## Clone Repository

```bash
git clone <repository_url>
cd project_hina
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Run Project

```bash
python gui.py
```

---

# 🎮 Usage

## Toggle Assistant

Press:

```text
CTRL + H
```

to show or hide the assistant popup.

---

## Example Commands

### App Control

```text
open chrome
close spotify
restart vscode
```

### System Utilities

```text
what time is it
check battery
```

### File Management

```text
find my dbms notes
open org.pdf
```

### Productivity

```text
calculate 99*42
countdown 5
```

---

# 🌸 UI Direction

Project Hina is being designed around an anime-inspired minimal desktop aesthetic.

Planned visual direction:

* rounded UI elements
* soft dark themes
* pastel accents
* floating popup behavior
* anime avatar integration
* transparent overlay UI

The goal is to create:

> “A calm futuristic anime desktop assistant.”

---

# 🔮 Future Roadmap

## V2 — Polished Desktop Companion

Focus:

* tray mode
* anime-themed UI
* PNG avatar integration
* notifications
* transparent popup
* persistent memory
* parser improvements

---

## V3 — Intelligent Assistant

Focus:

* local LLM integration
* contextual understanding
* smarter reasoning
* conversational improvements
* task chaining
* semantic memory

---

## V4 — Embodied Assistant

Focus:

* Live2D integration
* VRM/3D avatar support
* lip sync
* emotional expressions
* desktop companion mode
* animated interactions

---

# 📌 Current Status

## Current Development Stage

✅ Core desktop assistant functionality complete

✅ Voice-enabled popup assistant complete

✅ Modular backend architecture established

🔄 UI and identity polish in progress

---

# ⚠️ Important Notes

Project Hina is currently optimized for:

* Windows
* local/offline usage
* lightweight desktop workflows

The project is still under active development and major systems may evolve over time.

---

# 🌸 Final Vision

The long-term goal of Project Hina is to evolve from:

> “A popup desktop utility assistant”

into:

> “A fully interactive anime desktop companion with intelligence, memory, and embodiment.”

---

# 📜 License

This project is currently under personal development.

A formal license may be added in future releases.

---

# 💖 Project Hina

"A small assistant today.
A living desktop companion tomorrow." 🌸
