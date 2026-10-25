# Project Hina: Upgrade Roadmap

*Companion to `HINA_STATUS.md`. Written 24 Oct 2026.*

**Goal:** turn Hina from *a pretty command launcher with an AI fallback* into a **Jarvis-style assistant**. That means one that hears you, talks back naturally, remembers, sees your screen, and acts safely on your laptop, while staying local-first and keeping its sakura personality.

**Priority key:** 🔴 P0 must do next · 🟠 P1 high value · 🟡 P2 important · 🔵 P3 later / stretch
**Status key:** ✅ done · 🚧 in progress · ⏸ planned, waiting on another item
**Size:** S = an evening · M = a weekend · L = a week or more

---

## The map at a glance

```
PHASE 0  Stabilise ─────────────► PHASE 1  Real brain ─────────► PHASE 2  Ears & voice
 (safety, threading,               (one command registry,         (wake word, Whisper STT,
  Ollama fixes, cleanup)            chat LLM, streaming,           streaming TTS, barge-in)
        │                           long-term memory)                     │
        │                                   │                             │
        └──────────────► PHASE 3  Hands (more tools + safe agent loop) ◄──┘
                                            │
                       PHASE 4  Eyes (screen/OCR/vision) & proactivity
                                            │
                       PHASE 5  Body & polish (avatar, settings UI, installer, plugins)
```

**Critical path:** 0.1 → 0.2 → 0.3 → 1.1 → 1.2 → 2.1 → 2.2 → 3.1. Everything else can be done in parallel or picked up when you're in the mood.

---

## PHASE 0: Stabilise the foundation 🔴

*Why first:* every later feature relies on non-blocking AI calls and on tools that are safe to hand an LLM. Right now the AI freezes the window, two of the three AI features silently fail, and `eval`/`shell=True` are open doors.

| ID | Task | Pri | Size | Fixes |
|---|---|---|---|---|
| **0.1** | ✅ **Make tools safe:** replace `eval` with a tiny AST math evaluator (or `simpleeval`); swap every `shell=True` string for `subprocess.Popen([...])` / `os.startfile`; allow-list app names in `close_app`; map friendly names to process names (`vscode` → `Code.exe`) | 🔴 | S | Security §6.1–6.2, B-close |
| **0.2** | ✅ **Move work off the UI thread:** run `route_command` + `dispatch_command` in a worker thread (or `concurrent.futures`), post results back with `app.after(0, …)`; show a "thinking…" state on the status dot | 🔴 | S | B3 |
| **0.3** | ✅ **Fix Ollama calls:** add `"stream": False` to `/api/generate`; move `temperature`/`num_predict` into `"options"`; drop `max_length`; add a 1-second health check so a missing Ollama is skipped instantly | 🔴 | S | B1, B2 |
| 0.4 | ✅ Add the missing `find file` handler; make file and folder search **scoped** (Desktop, Documents, Downloads, project folders) with a result cap, and stop `open_app` from falling back to opening random files | 🔴 | S | B4, B8 |
| 0.5 | ✅ Fix the parser: whole-word removal of "my" (`re.sub(r"\bmy\b", …)`), and tighter `find` matching | 🔴 | S | B5, B6 |
| 0.6 | ✅ Make timers report through the GUI and voice; give each timer an ID with its own cancel event (`threading.Event`) *(done: `core/timers.py`; a finished timer shows in the HUD/window and is spoken; "cancel timer" cancels all running timers)* | 🟠 | S | B7 |
| 0.7 | ✅ Absolute paths: build `MEMORY_PROFILE_PATH` from `Path(__file__)`, or better, store user data under `%APPDATA%\Hina\` *(done: profile, history and facts live in `%APPDATA%\ProjectHina\` (or `HINA_DATA_DIR`); the old `memory/user_profile.json` is copied there once; saves are atomic and a corrupt file is kept as `*.corrupt`)* | 🟠 | S | B9 |
| 0.8 | ✅ Voice: unique temp file per utterance plus a speech **queue** (one speaker thread) *(done: `voice.speak` queues to one `hina-speaker` thread; temp files come from `tempfile`)* | 🟠 | S | B10 |
| 0.9 | ✅ Housekeeping: delete `main.py`/`personality.py` (or move them to `legacy/`); add `build/`, `dist/` and `*.mp3` to `.gitignore`; rewrite `requirements.txt` to the ~10 packages Hina actually uses; fix the focus-border binding; only say "Opening X" when the action succeeded *(done: `main.py`/`personality.py` deleted; `build/`, `dist/`, `*.mp3` untracked and ignored; `requirements.txt` is now the 11 packages Hina imports; the classic window's focus border works)* | 🟡 | S | B12, B13, §7 |
| 0.10 | ✅ **Tests:** `pytest` for `parser.normalize_command`, the dispatcher and the calculator; a mock Ollama for `ai_engine` | 🟡 | M | |
| 0.11 | ✅ Finish and merge `feature/ollama-tool-calling` into `main` once 0.1–0.3 are in *(done: Phases 0 and 1 merged into `main`)* | 🔴 | S | |

**Exit criteria:** the window never freezes, the LLM can't run arbitrary code, all 25 commands work from the GUI, and tests are green.

---

## PHASE 1: A real brain 🟠

*Depends on Phase 0.*

| ID | Task | Pri | Size | Depends on |
|---|---|---|---|---|
| **1.1** | ✅ **Single command/tool registry.** One `@tool(name, description, params)` decorator in a `tools/` package. The parser patterns, the Ollama `TOOLS` schema, the known-command list and the dispatcher are all *generated* from it, replacing the four hand-synced lists *(done: `tools/` package, see `tools/README.md`)* | 🔴 | M | 0.1 |
| **1.2** | ✅ **Conversational mode.** Anything that isn't a command goes to the LLM as a chat with rolling history (last ~10 turns), the personality in the system prompt, and the user's name, time and recent apps from `context_manager`. Replaces the canned small-talk lists *(done: `core/conversation.py`, Jarvis-style prompt, rolling summary of older turns, canned replies when Ollama is down; the matched small-talk tools in `tools/chat.py` are still canned)* | 🔴 | M | 0.2, 0.3 |
| 1.3 | ✅ **Streaming replies.** Use Ollama `stream: True`, show tokens as they arrive, and start speaking at the first sentence (cuts perceived latency from about 5 s to about 1 s) *(done for chat replies: `ai_engine.chat_reply(on_sentence=...)` streams, and the HUD speaks each sentence as it finishes; the text still appears once the reply is complete, and the classic Tk window doesn't stream)* | 🟠 | M | 1.2 |
| 1.4 | ✅ **Multi-step tool loop.** Feed the tool result back to the model so it can chain calls ("open spotify and set a 25-minute timer") with a max of about 5 steps *(done: `resolve_tool_call` runs every tool the model asks for, and for requests that read as several steps ("and", "then", a comma) shows the model each result and asks for the next call; repeats are skipped and a confirmation question stops the loop)* | 🟠 | M | 1.1 |
| 1.5 | ✅ **Long-term memory v2.** Move from JSON to SQLite: facts ("I study at…", "my sister is…"), preferences and conversation summaries. Add "remember that…" / "what do you know about me?" / "forget…" *(done: `core/memory_store.py` (`hina_memory.db`: turns, summary, facts); the profile stays JSON; private mode and a Memory section in HUD settings)* | 🟠 | M | 1.2 |
| 1.6 | ✅ **Semantic recall.** Embeddings (Ollama `nomic-embed-text`) over memories so relevant facts get pulled into the prompt automatically *(done for facts: `core/semantic.py`; needs `ollama pull nomic-embed-text`, otherwise it uses keyword matching; with 6 or fewer facts all of them are sent)* | 🟡 | M | 1.5 |
| 1.7 | ✅ **Model tiering.** Keep `qwen2.5:3b` for fast routing and an optional bigger local model (7–8B) or a cloud API for hard questions, with a setting to toggle "local only" *(done locally: `smart_model` in `settings.json` picks a bigger model for conversation, used only if installed. No cloud API was added, so everything stays local)* | 🟡 | S | 1.2 |
| 1.8 | ✅ **Personality switching by voice/text** ("be tsundere"), saved to the profile; personality also drives the LLM system prompt *(done: "be tsundere" / "be calm", saved in the profile; `calm` and `tsundere` exist)* | 🟡 | S | 1.2 |

---

## PHASE 2: Ears and voice (the "Jarvis moment") 🟠

*Depends on 0.2 and 0.8. It's much better with 1.2 + 1.3 in place.*

| ID | Task | Pri | Size | Depends on |
|---|---|---|---|---|
| **2.1** | ✅ **Push-to-talk speech input.** Hold a hotkey or click a mic button → record with `sounddevice` → transcribe with **`faster-whisper`** (already installed, `base.en` or `small.en` on your CUDA GPU) → same pipeline as typed text | 🔴 | M | 0.2 |
| **2.2** | ✅ **Wake word "Hey Hina".** `openWakeWord` (free, local; can train a custom "Hina" model) or Porcupine. Always-on, low CPU, pops the window and starts listening *(done without a trained model: Silero VAD listens continuously and only stretches of speech go to Whisper, which `core/wake.py` checks for "Hey Hina" (also "Hina, ..." at the start). "Hey Hina, open Chrome" runs the command directly. Off by default: turn on in settings or say "turn on wake word". A trained openWakeWord model could later replace the Whisper check)* | 🟠 | M | 2.1 |
| 2.3 | ✅ **Voice activity detection** (Silero VAD) so it stops recording when you stop talking *(done: uses the Silero model bundled with faster-whisper, so there's no new package; loudness is the fallback. Now also used by the Qt HUD's own recorder)* | 🟠 | S | 2.1 |
| 2.4 | ✅ **Barge-in:** speaking or pressing the hotkey stops Hina mid-sentence *(done for the hotkey, mic button, a new command and "stop"/"be quiet". Talking over her is not done: an open mic would hear her own voice without echo cancellation)* | 🟡 | S | 0.8, 2.1 |
| 2.5 | **Better TTS:** play Edge-TTS audio from memory (no temp file), sentence-by-sentence for streaming, and add an offline voice (Piper / Kokoro) for when there's no internet; let the user choose the voice | 🟡 | M | 0.8, 1.3 |
| 2.6 | ✅ **Conversation mode:** after a reply, keep listening for about 8 s for a follow-up without the wake word *(done: after a spoken exchange the HUD reopens the mic for 8 s (`follow_up_seconds`) once Hina stops talking, so you can answer a "Should I?" or keep going. Silence just ends it. Typed commands don't trigger it; toggle in settings)* | 🟡 | S | 2.2 |
| 2.7 | Visual feedback: listening / thinking / speaking states on the status dot and petals | 🟡 | S | 2.1 |

---

## PHASE 3: Hands (more capabilities, safely) 🟡

*Depends on 1.1 (registry) and 1.4 (tool loop).* Each tool is one file in `tools/`.

| ID | Capability | Pri | Size | Notes |
|---|---|---|---|---|
| **3.1** | ✅ **Permission tiers:** each tool is tagged `safe` / `confirm` / `blocked`. Destructive actions (close app, delete, send, shutdown) ask "Should I?" by voice or button first. Everything gets an action log | 🔴 | S | Must land before the risky tools below |
| 3.2 | ✅ System controls: volume, mute, brightness, Wi-Fi/Bluetooth toggle, lock, sleep, shutdown (confirm) *(done: volume (Windows Core Audio through comtypes; no pycaw needed), mute, brightness (WMI, laptop screens), lock, and sleep/shutdown/restart, which ask first; shutdown waits 10 s and "cancel shutdown" stops it. Wi-Fi/Bluetooth toggles not done)* | 🟠 | S | `pycaw`, `screen-brightness-control` |
| 3.3 | ✅ Media control: play/pause/next, "what's playing", Spotify search *(done: play/pause, next and previous through media keys; "what's playing" reads Spotify's window title; "play X on Spotify" opens Spotify's search)* | 🟠 | S | Media keys or Spotify Web API |
| 3.4 | ✅ Reminders and alarms at times ("remind me at 6 to call mom"), persisted across restarts, plus Windows toast notifications *(done: `core/reminders.py` with SQLite and a 5-second checker thread, and times like "at 6", "in 20 minutes" or "tomorrow at 9:30am"; reminders missed while Hina was closed are announced at start. They show in the HUD and are spoken; Windows toast notifications are not done yet)* | 🟠 | M | APScheduler + SQLite (1.5) |
| 3.5 | ✅ Clipboard: "summarise what I copied", "translate this", "fix the grammar" *(done: "summarise / translate / fix the grammar of what I copied" and "read my clipboard" (`tools/assist.py`). Translations and fixes are copied back to the clipboard, and a copied link is summarised as a web page)* | 🟠 | S | Great showcase for the LLM |
| 3.6 | ✅ Window management: snap, switch to, minimise all, "focus mode" closes distractions *(done with pywin32 instead of pygetwindow: switch to, minimise, maximise, snap left/right, minimise all, "what windows are open". "Focus mode" asks, then closes the distraction apps listed in settings, with an optional focus timer)* | 🟡 | S | `pygetwindow` |
| 3.7 | ✅ Web: weather, news headlines, quick factual answers with a search API, and summarising an open URL *(done without API keys: weather from Open-Meteo (home city via "my city is ..."; same-name towns prefer `news_region`), Google News headlines (top or by topic), Wikipedia for "who is / tell me about" (falls back to chat when offline), and "summarise this page" from a link)* | 🟡 | M | |
| 3.8 | ✅ Files: index chosen folders (fast search), "open the PDF I downloaded yesterday", **ask questions about a PDF/doc** (RAG, PyMuPDF is already installed) *(done: `utils/file_index.py` (SQLite index of the search folders, refreshed in the background at start) for "open the PDF I downloaded yesterday" and "what did I download today". `utils/documents.py` loads PDF, Word, PowerPoint and text, and answers questions from the best-matching excerpts with page citations (by meaning with nomic-embed-text, otherwise by keywords), plus "summarise the document". Scanned PDFs need OCR (4.2))* | 🟡 | L | 1.6 |
| 3.9 | ✅ Notes and to-dos: "add milk to my list", "what's on my list" *(done: named lists, defaulting to to-do: add, show, remove items, clear (asks first), "what lists do I have")* | 🟡 | S | 1.5 |
| 3.10 | ✅ Smarter modes: create or edit modes by voice ("add Discord to coding mode"), auto-suggest a mode by time of day *(done: "add discord to coding mode", "remove ... from ...", "create a mode called gaming with ...", "delete ... mode" (asks first), "what's in ... mode". Edits are saved to the user data folder. "Which mode should I use" learns from when modes are started, otherwise guesses by time of day)* | 🔵 | S | |
| 3.11 | Integrations: Gmail/Calendar (read agenda, draft replies, always confirm before sending), GitHub notifications | 🔵 | L | OAuth, 3.1 |
| 3.12 | ✅ Code helper: "explain this error" from the clipboard or terminal *(done for the clipboard: "explain this error / this code". Reading the terminal directly is not done)* | 🔵 | M | |

---

## PHASE 4: Eyes and proactivity 🔵

*Depends on 1.2, 1.4, 3.1.*

| ID | Task | Pri | Size | Notes |
|---|---|---|---|---|
| 4.1 | "What's on my screen?" Screenshot (`mss`) → local vision model (`llava`, `qwen2.5-vl`, `moondream` via Ollama) | 🟡 | M | |
| 4.2 | OCR a region: "read this", "copy the text from this image" | 🟡 | S | Windows OCR API or `rapidocr` |
| 4.3 | Context awareness: knows the active app/window title so "summarise this" means the current page or doc | 🟡 | M | |
| 4.4 | **Proactive nudges** (opt-in): battery low, long session → break reminder, meeting in 10 min, calm-mode check-ins (evolves `ambient.py`) | 🟡 | M | 3.4 |
| 4.5 | Habit learning: notices "you open VS Code + Spotify every evening" → offers to make a mode / auto-launch | 🔵 | M | 1.5 |
| 4.6 | Daily briefing on startup: weather, agenda, reminders, unfinished to-dos | 🔵 | S | 3.4, 3.7, 3.9 |

---

## PHASE 5: Body and polish 🔵

| ID | Task | Pri | Size | Notes |
|---|---|---|---|---|
| 5.1 | **Settings panel** (and a `settings.json`): model, voice, hotkey, personality, wake word, permission level, folders to index, local-only toggle | 🟠 | M | Do it early in Phase 1 if hard-coding starts to hurt |
| 5.2 | Chat history view (expandable panel with scrollback) instead of a single output line | 🟠 | M | Pairs with 1.2 |
| 5.3 | System-tray icon (pystray), start with Windows, single-instance lock | 🟡 | S | |
| 5.4 | Avatar: animated 2D sprite with idle/talk/think states, then Live2D, with lip-sync from TTS volume | 🔵 | L | |
| 5.5 | Mood/emotion engine that affects voice style, avatar expression and wording | 🔵 | M | 1.8, 5.4 |
| 5.6 | Proper installer (PyInstaller + Inno Setup), bundling `modes.json`, assets and first-run Ollama check/model pull | 🟡 | M | 0.7 |
| 5.7 | Plugin system: drop a `.py` into `plugins/` and its `@tool`s auto-register | 🔵 | M | 1.1 |
| 5.8 | Phone companion / remote control (small local web UI) | 🔵 | L | |
| 5.9 | Logging to a rotating file plus crash reports; GitHub Actions CI running tests | 🟡 | S | 0.10 |

---

## Dependency cheat-sheet

| Upgrade | Needs first |
|---|---|
| Any new tool | 0.1 safe execution, 1.1 registry, 3.1 permissions (for risky ones) |
| Natural conversation | 0.2 threading, 0.3 Ollama fixes |
| Streaming voice replies | 1.3 streaming, 0.8 speech queue |
| Wake word | 2.1 speech-to-text |
| Reminders, briefing, nudges | 1.5 SQLite memory, 3.4 scheduler |
| Ask questions about your files | 1.6 embeddings, 3.8 indexing |
| Screen understanding | 1.4 tool loop, a vision model in Ollama |
| Installer | 0.7 absolute/AppData paths, 5.1 settings |
| Avatar emotions | 1.8 personality, 5.4 avatar |

---


## Progress log (updated 25 Oct 2026)

- **Done:** 0.2 (worker thread with a "thinking..." state), 0.5 (parser fixes), 0.10 (pytest suite), 2.1 (push-to-talk speech input with `faster-whisper`), and the safety sprint 0.1, 0.3, 0.4, 3.1 (branch `claude/beautiful-chandrasekhar-6f7ad8`, commit `53e16b2`, 348 tests pass, not yet merged). That covers the AST math evaluator, no `shell=True`, the Ollama fixes, file search scoped to Desktop/Documents/Downloads plus `search_folders.txt`, the `find file` parser bug, permission tiers (`core/permissions.py`), yes/no confirmation for close/restart and an action log (`action_log.jsonl`). Also fixed: `bye`/`exit` routing and Chinese replies.
- **Not verified yet:** the Yes/No buttons in the GUI, a run against a real Ollama, and live mic use. Delete and shutdown tools don't exist yet, so only close and restart are gated.
- **Planned, paused until the safety sprint lands:** 1.5 memory v2 in three stages: a safe store (atomic writes, lock, data under `%APPDATA%\Hina\`, which also covers 0.7), conversation history with rolling summaries, then SQLite facts with "remember / what do you know about me / forget". Best designed together with 1.2 and after 1.1, so the new commands are registered in one place.
- **Decided for 4.1 (vision):** start with `qwen2.5vl:3b` via Ollama (fits 8GB VRAM next to the text model), `mss` screenshots downscaled to ~1280px, a new `core/vision.py` on a worker thread, explicit trigger only at first, short `keep_alive`. Start after the current sprints, since it touches `gui.py` and the router.
- **Suggested order now:** merge the safety branch → 0.11 merge `feature/ollama-tool-calling` → 1.1 tool registry → 1.2 chat mode and memory v2 → 4.1 vision.

---

## Suggested next 3 sprints

1. **Sprint A ("Make it solid"):** 0.1, 0.2, 0.3, 0.4, 0.5 → merge the tool-calling branch (0.11). *About one weekend.*
2. **Sprint B ("Make it talk"):** 1.1 registry, 1.2 chat mode, 2.1 push-to-talk with faster-whisper. *By the end you can hold a hotkey, speak, and have Hina answer or act.*
3. **Sprint C ("Make it Jarvis"):** 2.2 wake word, 1.3 streaming, 3.1 permissions, 3.2 + 3.3 system/media controls, 5.2 chat history panel.

After Sprint C, Hina is a genuine always-listening, local, personality-driven assistant. Phases 3–5 are then about adding capabilities one tool at a time.

---

## Recommended stack additions

| Need | Pick | Why |
|---|---|---|
| Speech-to-text | `faster-whisper` (already installed) | Fast on your CUDA GPU, offline |
| Wake word | `openWakeWord` | Free, local, custom "Hina" model possible |
| VAD | Silero VAD | Tiny and accurate |
| Mic capture | `sounddevice` | Simple, low latency |
| Offline TTS | Piper or Kokoro | Natural, runs on CPU |
| Memory DB | SQLite (built in) | Zero setup |
| Embeddings | Ollama `nomic-embed-text` | Same runtime you already use |
| Vision | Ollama `qwen2.5-vl` / `moondream` | Local |
| Scheduler | APScheduler | Reminders and alarms |
| Safe math | `simpleeval` or an AST walker | Replaces `eval` |
| Tray | `pystray` | Background presence |
