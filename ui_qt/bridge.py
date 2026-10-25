"""
Controller between the Qt window and Hina's assistant logic.

Commands and voice capture run on worker threads, exactly like gui.py's
_run_command / _run_listen; results come back as Qt signals, which Qt queues
onto the GUI thread. Only the public entry points route_command and
dispatch_command are used, so the router/dispatcher can change underneath.
"""

import itertools
import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from core import conversation, permissions, timers
from core.command_router import route_command
from core.dispatcher import DispatchResult, dispatch_command
from utils.logger import get_logger

logger = get_logger(__name__)

FAILED_REPLY = "Something went wrong executing that command. Details are in the log."


class Heard:
    """Worker -> GUI: what the microphone made of the user's speech."""

    def __init__(self, text="", error=None, cancelled=False, origin="mic"):
        self.text, self.error, self.cancelled = text, error, cancelled
        self.origin = origin  # "mic" (button / hotkey), "wake" (after "Hey Hina") or "follow_up"


# ---- shims for code written against the Tk window (voiced countdown) --------
class _VarShim:
    def __init__(self, bridge):
        self._bridge = bridge

    def set(self, text):
        self._bridge.side_text.emit(str(text))

    def get(self):
        return ""


class _LabelShim:
    def configure(self, **kwargs):
        pass


class _AppShim:
    """`app.after(ms, fn, *args)` from any thread -> QTimer on the GUI thread."""

    def __init__(self, bridge):
        self._bridge = bridge
        self._ids = itertools.count(1)

    def after(self, ms, fn=None, *args):
        if fn is not None:
            self._bridge.call_soon.emit(int(ms), lambda: fn(*args))
        return next(self._ids)

    def after_cancel(self, _id):
        pass


def _hina_speaking():
    try:
        import voice
        return voice.is_speaking()
    except Exception:
        return False


def _barge_in():
    try:
        import voice
        voice.stop()
    except Exception:
        logger.exception("Couldn't stop speech")


class HinaBridge(QObject):
    # Public signals fire on the GUI thread *after* busy/listening are updated,
    # so a receiver always sees a consistent state.
    result_ready = Signal(object)        # DispatchResult
    heard = Signal(object)               # Heard
    _result_raw = Signal(object)         # worker -> GUI thread
    _heard_raw = Signal(object)
    voice_state = Signal(str)            # waiting / listening / transcribing
    mic_level = Signal(float)            # 0..1 while recording
    side_text = Signal(str)              # countdown ticks etc.
    speech_chunk = Signal(str)           # a finished sentence of a chat reply that is still streaming
    notice = Signal(str)                 # a timer went off: show it and say it
    call_soon = Signal(int, object)      # (delay ms, callable) to run on the GUI thread
    busy_changed = Signal(bool)
    listening_changed = Signal(bool)
    mode_changed = Signal(str)
    wake_heard = Signal(str)             # the wake phrase was said; the text is any command that followed it
    wake_error = Signal(str)             # the wake listener hit a problem the user should know about

    def __init__(self, settings=None, speech=None, parent=None):
        super().__init__(parent)
        self.settings = settings or {}
        self.busy = False
        self.listening = False
        self._speech = speech
        self._pending_mode = None
        self._wake = None                # core.wake.WakeListener while the wake word is on
        self._wake_quiet_until = 0.0
        self.var_shim, self.label_shim, self.app_shim = _VarShim(self), _LabelShim(), _AppShim(self)
        self.call_soon.connect(self._on_call_soon)
        conversation.set_stream_sink(self.speech_chunk.emit)  # sentences, as the model writes them
        timers.set_notifier(self.notice.emit)  # fires on the timer's thread; Qt queues it to the GUI thread
        self._result_raw.connect(self._on_result)
        self._heard_raw.connect(self._on_heard)

    # ---- commands ---------------------------------------------------
    def submit(self, raw_command):
        """Start a command on a worker thread. False if busy or empty."""
        raw_command = (raw_command or "").strip()
        if not raw_command or self.busy or self.listening:
            return False
        _barge_in()  # a new command makes the old reply moot
        self._set_busy(True)
        threading.Thread(target=self._run_command, args=(raw_command,), daemon=True).start()
        return True

    def answer(self, yes):
        return self.submit("yes" if yes else "no")

    def _run_command(self, raw_command):
        command = None
        try:
            command = route_command(raw_command)
            if command.startswith("mode "):
                self._pending_mode = command[len("mode "):].strip()
            result = dispatch_command(
                command, output_var=self.var_shim, output_label=self.label_shim, app=self.app_shim)
        except Exception:
            logger.exception("Command failed: %s", raw_command)
            result = DispatchResult(reply=FAILED_REPLY)
        conversation.record(raw_command, command, result.reply)  # history (skipped in private mode)
        self._result_raw.emit(result)

    @Slot(object)
    def _on_result(self, result):
        self._set_busy(False)
        mode, self._pending_mode = self._pending_mode, None
        if mode and result.reply and "ouldn't" not in result.reply and "not found" not in result.reply.lower():
            self.mode_changed.emit(mode)
        self.result_ready.emit(result)

    def has_pending_confirmation(self):
        return permissions.has_pending()

    # ---- voice ------------------------------------------------------
    def speech(self):
        if self._speech is None:
            from core.stt import SpeechInput, WhisperTranscriber
            from ui_qt.settings import whisper_model_name
            import voice
            model = whisper_model_name(self.settings)
            self._speech = SpeechInput(
                recorder=self._metered_recorder,
                transcriber=WhisperTranscriber(model_name=model) if model else None,
                is_speaking=voice.is_speaking,
                on_state=self.voice_state.emit,
            )
        return self._speech

    def toggle_listening(self):
        """Mic button / push-to-talk: start listening, or stop if already listening."""
        if self.listening:
            self.speech().cancel.set()
            return False
        return self.start_listening()

    def start_listening(self, no_speech_timeout=None, origin="mic"):
        """Open the mic for one command. False if already listening or busy."""
        if self.listening or self.busy:
            return False
        if origin != "follow_up":
            _barge_in()  # talking over Hina: she stops so the mic can open at once
        self._set_listening(True)
        threading.Thread(target=self._run_listen, args=(no_speech_timeout, origin), daemon=True).start()
        return True

    def _run_listen(self, no_speech_timeout=None, origin="mic"):
        from core.stt import SttError
        try:
            speech = self.speech()
            text = speech.listen(no_speech_timeout=no_speech_timeout)
            self._heard_raw.emit(Heard(text=text, cancelled=speech.cancel.is_set(), origin=origin))
        except SttError as exc:
            self._heard_raw.emit(Heard(error=str(exc), origin=origin))
        except Exception:
            logger.exception("Voice input failed")
            self._heard_raw.emit(Heard(error="Voice input failed. Details are in the log.", origin=origin))
        finally:
            self.mic_level.emit(0.0)

    @Slot(object)
    def _on_heard(self, heard):
        self._set_listening(False)
        self.heard.emit(heard)

    def _metered_recorder(self, cancel=None, no_speech_timeout=None):
        """core.stt.record_until_silence, but reporting the live level for the HUD core."""
        from core import stt
        try:
            import numpy as np
            import sounddevice as sd
        except Exception as exc:
            raise stt.SttError("Voice input needs the 'sounddevice' package") from exc

        block = int(stt.SAMPLE_RATE * stt.BLOCK_SECONDS)
        device = stt._resolve_device(sd)

        def rms(b):
            level = float(np.sqrt(np.mean(b ** 2)))
            self.mic_level.emit(min(1.0, level * 12.0))
            return level

        try:
            with sd.InputStream(device=device, samplerate=stt.SAMPLE_RATE, channels=1,
                                dtype="float32", blocksize=block) as stream:
                kept = stt.collect_phrase(lambda: stream.read(block)[0][:, 0].copy(), cancel, rms=rms,
                                          speech_prob=stt.load_vad(), no_speech_timeout=no_speech_timeout)
        except stt.SttError:
            raise
        except Exception as exc:
            logger.warning("Microphone failed: %s", exc)
            raise stt.SttError("I can't reach a microphone. Check it's plugged in and allowed.") from exc
        if not kept:
            return None
        return stt.normalise(np.concatenate(kept))

    # ---- wake word (core/wake.py) -----------------------------------
    @property
    def wake_running(self):
        return self._wake is not None and self._wake.running

    def start_wake(self, listener=None):
        """Listen for the wake phrase in the background. `listener` replaces the real one in tests."""
        if self.wake_running:
            return True
        if listener is None:
            from core.wake import WakeListener
            listener = WakeListener(on_wake=self._wake_fired, transcriber=self.speech().transcriber,
                                    is_paused=self._wake_paused, phrase=self.settings.get("wake_phrase"),
                                    on_error=self.wake_error.emit)
        self._wake = listener
        self._wake.start()
        return True

    def stop_wake(self):
        if self._wake is not None:
            self._wake.stop()
        self._wake = None

    def _wake_paused(self):
        """Close the wake mic while the command mic is open or a command runs.

        While Hina talks it stays open when "voice_barge_in" is on (the default), so the wake
        phrase interrupts her. It hears her own voice too, but she'd have to start a sentence
        with the wake phrase to trigger it. With the setting off it closes while she talks.
        """
        if self.listening or self.busy or time.time() < self._wake_quiet_until:
            return True
        if self.settings.get("voice_barge_in", True):
            return False
        return _hina_speaking()

    def _wake_fired(self, command):
        self._wake_quiet_until = time.time() + 1.5  # let the window open the command mic first
        if _hina_speaking():
            _barge_in()  # "Jarvis, ..." while she talks: she stops at once
        self.wake_heard.emit(command)

    # ---- helpers ----------------------------------------------------
    def _set_busy(self, busy):
        self.busy = busy
        self.busy_changed.emit(busy)

    def _set_listening(self, listening):
        self.listening = listening
        self.listening_changed.emit(listening)

    @Slot(int, object)
    def _on_call_soon(self, ms, fn):
        QTimer.singleShot(max(0, ms), fn)
