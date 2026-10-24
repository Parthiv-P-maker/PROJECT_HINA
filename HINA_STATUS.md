# Project Hina: Where Things Stand

*Snapshot taken 24 Oct 2026, from a full read of `PROJECT_HINA` (every `.py`, `.json`, `.spec`, the README and the git metadata).*

---

## 1. One-paragraph summary

Hina is a working **Windows desktop companion** written in Python. It has a borderless floating window with a sakura theme (CustomTkinter), spoken replies (Edge-TTS with a pyttsx3 fallback), a JSON memory file, two personality presets, workspace "modes" that launch sets of apps, and about 25 typed commands (open/close apps, find files, time, battery, timers, web search...). The newest work, on branch **`feature/ollama-tool-calling`**, connects a local LLM (**Ollama, `qwen2.5:3b`**) so natural sentences that the rule-based parser doesn't recognise get turned into real actions through tool-calling. **What it is not yet:** it can't hear you (no speech input), it can't hold a conversation, the AI path freezes the window while it thinks, and a few of the actions are unsafe to hand to an LLM. The foundations are good. The next step is to make what already exists safe and responsive, and *then* add the "Jarvis" features.

**Maturity:** solid prototype / early alpha. About 1,900 lines of your own code across 35 files, no tests.

---

## 2. Repository facts

| Item | Value |
|---|---|
| Remote | `github.com/Parthiv-P-maker/PROJECT_HINA` |
| Checked-out branch | `feature/ollama-tool-calling` (not merged into `main`) |
| Most recently edited | `core/ai_engine.py` (18:44), `core/command_router.py` + `core/dispatcher.py` (18:30) today, so the tool-calling work looks active and probably uncommitted |
| Language / runtime | Python 3.13 (from `__pycache__`), Windows only |
| Entry points | `gui.py` (main app), `main.py` (old CLI loop) |
| Packaging | PyInstaller `gui.spec` → `dist/gui/gui.exe` (~18 MB) |
| Tests | None |

---

## 3. Architecture (how a command flows)

```
 User types in entry box  (gui.py)
          │
          ▼
 core/command_router.route_command()
   1. parser.normalize_command()        ← rule-based, regex-free string matching
   2. known prefix? ── yes ─────────────────────────────────┐
   3. no → AI (lazy-loaded via core/ai_loader)              │
        a. ai_engine.resolve_tool_call()  → Ollama /api/chat │
           with 15 tools → runs action → returns "ai_reply::…"
        b. ai_engine.fallback_parse_command() → Ollama       │
           /api/generate maps text onto a known command      │
          │                                                  │
          ▼                                                  ▼
 core/dispatcher.dispatch_command()  → actions.py / memory.py / mode_manager.py
          │
          ▼
 core/personality_engine.generate_reply()  (template per personality)
   + ai_engine.rewrite_action_reply()      (LLM restyles the reply)
          │
          ▼
 core/assistant.hina_reply()  → updates label, gold pulse, voice.speak()
```

### File map

| Area | Files | Role |
|---|---|---|
| **App shell** | `gui.py`, `ui/window.py`, `ui/theme.py`, `ui/animations.py`, `ui/effects.py`, `ui/widgets.py` | Window, drag, Ctrl+H toggle, petals, status-dot blink, reply pulse |
| **Brain (rules)** | `parser.py`, `core/command_router.py`, `core/dispatcher.py` | Normalise text, route, run handlers |
| **Brain (AI)** | `core/ai_engine.py`, `core/ai_loader.py`, `core/context_manager.py` | Ollama calls, tool schema, session context (recent commands, time-of-day tone) |
| **Actions** | `actions.py`, `core/mode_manager.py`, `core/countdown.py`, `modes.json` | OS actions, workspace modes, voiced countdown |
| **Persona** | `core/personality_engine.py`, `core/startup.py`, `core/ambient.py`, `utils/constants.py` | Reply templates, greetings, idle "thoughts" |
| **Memory** | `memory.py`, `memory/user_profile.json` | Name, recent apps/files, favourite apps |
| **Voice out** | `voice.py` | Edge-TTS → mp3 → pygame; pyttsx3 fallback |
| **Utilities** | `utils/helpers.py`, `utils/logger.py` | `clean_text`, `try_parse_int`, console logger |
| **Legacy** | `main.py`, `personality.py` | Old CLI loop and old personality module, superseded by `gui.py` and `core/` |

---

## 4. Features: what actually works

| Feature | Status | Notes |
|---|---|---|
| Floating sakura window, drag, always-on-top, petals, blink, pulse | ✅ Works | Hides itself 2.5 s after start; Ctrl+H brings it back |
| Startup greeting (spoken, uses saved name) | ✅ Works | |
| Open / close / restart apps | ⚠️ Partly | Open works for known apps. Close uses `taskkill /IM <name>.exe`, so "close vscode" fails (the process is `Code.exe`). Unknown names fall through to a **full scan of C:\\** |
| Favourite apps (`favorite app chrome as browser` → `open browser`) | ✅ Works | |
| Remember name (`my name is …`) | ✅ Works | |
| Recent apps / files tracking | ✅ Works | Recorded, but only used as AI context |
| Workspace modes (`coding mode`, `study mode`, `research mode`) | ✅ Works | Driven by `modes.json`; ChatGPT/Claude desktop paths resolved |
| Time, date, battery, disk | ✅ Works | |
| Calculator | ⚠️ Works, unsafe | Uses `eval()` |
| Google / ChatGPT search | ✅ Works | Opens browser |
| Find folder | ⚠️ Slow | Walks all of C:\\ on the UI thread, so the window freezes |
| **Find file** | ❌ Broken in GUI | Parser emits `find file X`, but the dispatcher has no handler for it, so you get "I don't know that one" |
| Timer | ⚠️ Half | Starts, but when it finishes it only `print`s to the console. The GUI never shows or says it |
| Voiced countdown | ✅ Works | Runs in a thread |
| Personality presets (calm / tsundere) | ⚠️ Half | Switching means editing `CURRENT_PERSONALITY` in code; there's no command for it |
| Ambient idle thoughts | ✅ Works | Only noticeable if the window is visible |
| Small talk (hello, how are you, I'm tired…) | ✅ Works | Canned random replies |
| **AI tool-calling (Ollama)** | ⚠️ Works, with caveats | Real actions from free text, but blocks the UI and has the safety gaps listed in §6 |
| AI command fallback and reply restyling | ❌ Silently not working | See bug B1 below |
| Voice input / wake word | ❌ Not started | `faster-whisper` is installed but no code uses it |
| Packaged `.exe` | ⚠️ Stale | Built before the AI work; `modes.json` isn't bundled, and the memory path is relative |

---

## 5. Known bugs (verified by reading the code)

| # | Severity | Where | Problem |
|---|---|---|---|
| **B1** | High | `core/ai_engine.py` `_send_ollama_request` for `/api/generate` | `stream` isn't set to `False`, so Ollama streams NDJSON and `response.json()` throws. **`fallback_parse_command` and `rewrite_action_reply` always return `None`**, so every "AI-styled" reply is really the plain template |
| **B2** | High | same file | `temperature`, `num_predict` and `max_length` sit at the top level of the payload. Ollama only reads them inside `"options": {...}`, so they're ignored (and `max_length` isn't an Ollama option at all) |
| **B3** | High | `gui.py` → `app.after(300, _handle_command)` | Routing, Ollama calls (up to 45 s each, and up to 3 per command), C:\\ scans and `restart_app`'s `sleep(1)` all run **on the Tk main thread**, so the window freezes |
| **B4** | Medium | `core/dispatcher.py` | No `find file` branch, and `find_file` isn't imported |
| **B5** | Medium | `parser.py` | `.replace("my", "")` removes "my" *inside* words: "open mysql" becomes "open sql", "close myapp" becomes "close app" |
| **B6** | Medium | `parser.py` | `"find" in command` matches any sentence containing "find" |
| **B7** | Medium | `actions.py` timers | A finished timer only `print`s. Also `timer_cancelled` is one global, so starting a new timer "un-cancels" the old one |
| **B8** | Medium | `actions.open_app` | Unknown app name → `search_and_open_file` scans C:\\ and **opens the first file whose name contains the text** (for example "open a" opens some random file) |
| **B9** | Medium | `utils/constants.py` | `MEMORY_PROFILE_PATH = "memory/user_profile.json"` is relative to the current folder, so launching from elsewhere or from the exe makes a blank new profile |
| **B10** | Low | `voice.py` | Every utterance writes the same `hina_voice.mp3`. Overlapping speech (countdown, quick replies) collides on that file and on pygame's single music channel |
| **B11** | Low | `voice.py` / `helpers.clean_text` | Strips all non-ASCII, so non-English names or words disappear from speech |
| **B12** | Low | `gui.py` | `entry.bind("<FocusIn>", …)` is called twice without `add="+"`, so the second replaces the first. `_on_entry_focus(widget)` also receives a Tk *event*, not the widget. The pink focus border never shows |
| **B13** | Low | `dispatcher` open/close/restart | Reply is generated whether or not the action succeeded, so Hina says "Opening X 🌸" even on failure |
| **B14** | Low | AI tool path | Bypasses favourites and recent-app memory, so "could you launch my browser" doesn't resolve the `browser` favourite |
| **B15** | Low | `main.py` | `int()` on timer/countdown input crashes on bad input; the CLI also lacks modes, names and favourites |

---

## 6. Security risks (these matter now that an LLM can call tools)

1. **`calculate()` uses `eval()`.** The LLM can call `calculate` with any string, and so can anything typed. `__import__('os').system('…')` would run. This is arbitrary code execution.
2. **Shell injection.** `open_app`, `close_app` and `mode_manager` build `shell=True` command strings from user or LLM text (`taskkill /IM {name}.exe`). A name like `x & del …` gets executed.
3. **No confirmation step.** The model can close apps or open files with nobody approving it.
4. **Global keyboard hook.** The `keyboard` library hooks all keystrokes and may need admin rights. Ctrl+H also collides with "History"/"Replace" in other apps.

---

## 7. Code health and hygiene

* **The command list is duplicated four times:** `parser.py`, `command_router.KNOWN_COMMAND_PREFIXES`, `ai_engine.KNOWN_NORMALIZED_COMMANDS` (already out of sync: it lacks search and mode) and the dispatcher `if` chain. `FILE_EXTENSIONS` is duplicated too.
* **Legacy files** `main.py` and `personality.py` duplicate newer code.
* **`requirements.txt` is a raw `pip freeze`** of a large environment: torch+CUDA, open3d, gsplat, dash, Flask, matplotlib, Jupyter, PyMuPDF and the `ollama` package (unused, since `requests` is used instead). A fresh install downloads several GB that Hina doesn't need. `pyinstaller` isn't listed.
* **`build/` and `dist/` (~18 MB exe each) aren't in `.gitignore`** and look like they're committed.
* **README is behind the code.** It omits Ollama, tool-calling, modes and web search, lists an `assets/` folder that doesn't exist, and has a placeholder clone URL.
* **No tests, no log file, no settings file.** The model name, voice, hotkey and personality are all hard-coded.
* `context_manager.get_context()` re-reads the JSON profile from disk on every call.

---

## 8. Strengths to keep building on

* A clean modular split (`core/`, `ui/`, `utils/`) and a `DispatchResult` object, which makes this easy to extend.
* **Hybrid brain:** fast rules first and the LLM only as a fallback. That's the right design for a laptop.
* Lazy AI loading, so the app starts instantly even with no Ollama.
* Tool schema already written for 15 actions, which is most of the work towards a real agent.
* Strong visual identity and personality system.
* Graceful fallbacks everywhere (no psutil, no Edge-TTS, no Ollama).

---

## 9. Bottom line

You have **"Hina V1: a pretty command launcher with an AI fallback."** To reach **"Jarvis"** you need three missing pillars: **ears** (speech input + wake word), **real conversation** (chat memory and streaming LLM replies) and **safe agency** (sandboxed tools, confirmations, more capabilities). Fix bugs B1–B4 and the §6 security items first, because each later upgrade builds on them. See **`HINA_ROADMAP.md`** for the plan.
