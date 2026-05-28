# 🌸 Project Hina

<div align="center">

### *An Anime-Inspired Ambient Desktop Assistant*

A modular desktop companion built with Python, featuring voice interaction, persistent memory, animated UI systems, personality-driven responses, and future-ready AI architecture.

---

![Python](https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge\&logo=python)
![CustomTkinter](https://img.shields.io/badge/CustomTkinter-UI-pink?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Active%20Development-purple?style=for-the-badge)
![Architecture](https://img.shields.io/badge/Architecture-Modular-success?style=for-the-badge)

</div>

---

# ✨ Overview

Project Hina is a floating desktop assistant designed to provide a more immersive and personality-driven interaction experience compared to traditional utility assistants.

The project combines:

* Modern modular architecture
* Anime-inspired desktop aesthetics
* Voice interaction
* Persistent memory systems
* Personality-based responses
* Ambient animations
* Future AI integration capabilities

Rather than functioning solely as a command executor, Hina is designed as an evolving desktop companion framework focused on presence, responsiveness, and extensibility.

---

# 🌸 Current Features

## 🪟 Ambient Desktop Interface

* Floating borderless assistant window
* Sakura-inspired visual theme
* Animated falling petal effects
* Smooth draggable interface
* Pulsing visual response effects
* Always-on-top assistant mode
* Global hotkey toggle (`Ctrl + H`)

---

## 🎤 Voice Interaction

* Edge-TTS powered voice output
* Spoken assistant responses
* Countdown voice announcements
* Startup greeting interaction

---

## 🧠 Persistent Memory System

Hina currently remembers:

* User name
* Favorite applications
* Recently opened applications
* Recently accessed files

Example:

```bash
favorite app chrome as browser
open browser
```

---

## ⚡ Command System

### Application Management

```bash
open chrome
close spotify
restart vscode
```

### File & Folder Operations

```bash
open file notes.txt
find folder downloads
```

### Utility Commands

```bash
tell time
tell date
battery
disk usage
calculate 25*12
```

### Timers & Countdown

```bash
timer 60
countdown 10
cancel timer
```

---

## 🎭 Personality Engine

Hina includes a modular personality framework capable of dynamically altering assistant responses.

Current personality presets:

* Calm 🌸
* Tsundere 💢

The architecture is designed to support:

* AI-generated responses
* Emotional state systems
* Mood adaptation
* Context-aware dialogue generation

---

# 🏗 Project Architecture

The project has been fully refactored into a scalable modular architecture.

```text
project_hina/
│
├── gui.py
├── main.py
├── parser.py
├── actions.py
├── memory.py
├── voice.py
│
├── core/
│   ├── assistant.py
│   ├── dispatcher.py
│   ├── command_router.py
│   ├── startup.py
│   ├── countdown.py
│   └── personality_engine.py
│
├── ui/
│   ├── theme.py
│   ├── animations.py
│   ├── effects.py
│   ├── widgets.py
│   └── window.py
│
├── utils/
│   ├── constants.py
│   ├── helpers.py
│   └── logger.py
│
├── memory/
│   └── user_profile.json
│
└── assets/
    ├── avatars/
    ├── icons/
    └── sounds/
```

---

# ⚙️ Technologies Used

| Technology    | Purpose                   |
| ------------- | ------------------------- |
| Python 3.11+  | Core application          |
| CustomTkinter | UI framework              |
| Edge-TTS      | Voice synthesis           |
| Pygame        | Audio playback            |
| Keyboard      | Global hotkeys            |
| JSON          | Persistent memory storage |
| Threading     | Background task execution |

---

# 🚀 Installation

## 1. Clone the Repository

```bash
git clone https://github.com/your-username/project_hina.git
cd project_hina
```

---

## 2. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 3. Launch Hina

### GUI Mode

```bash
python gui.py
```

### CLI Mode

```bash
python main.py
```

---

# 🎮 Controls

| Action                  | Shortcut   |
| ----------------------- | ---------- |
| Toggle Assistant Window | `Ctrl + H` |

---

# 🧪 Stability Status

### Current Build Status

* ✅ Modular architecture completed
* ✅ Voice system stabilized
* ✅ Memory system operational
* ✅ Personality engine operational
* ✅ Animation systems modularized
* ✅ Command dispatcher implemented
* ✅ Parser routing stabilized

---

# 🧠 Future Roadmap

## Planned Features

### 🤖 AI Integration

* Local LLM integration
* AI-generated personality responses
* Context-aware dialogue generation

### 🎤 Voice Input

* Speech recognition
* Wake word activation
* Continuous listening mode

### 👀 Vision Systems

* Screenshot understanding
* OCR support
* Desktop context awareness

### 🎭 Character Systems

* Dynamic mood engine
* Adaptive personality shifting
* Emotion-aware interactions

### 🪄 Avatar Systems

* Live2D integration
* Animated assistant avatars
* Future 3D avatar support

### 📚 Behavioral Learning

* Usage habit analysis
* Workflow prediction
* Personalized suggestions

---

# 🎯 Design Philosophy

Project Hina is designed around the concept of:

> *“An assistant that feels present, not just functional.”*

The project prioritizes:

* Modular scalability
* Ambient interaction design
* Personality-driven responses
* Clean software architecture
* Future AI experimentation

The long-term goal is to evolve Hina into a lightweight intelligent desktop companion framework capable of integrating advanced AI systems while maintaining a calm and aesthetically pleasing user experience.

---

# ⚠️ Disclaimer

Project Hina is currently under active development.

Some systems are experimental and may evolve significantly as future AI, voice, and interaction systems are integrated.

---

# 🌸 Project Status

### **Hina V1 — Stable Architecture Build**

The project has successfully transitioned from an experimental prototype into a structured, modular desktop assistant framework prepared for long-term expansion and AI integration.
