"""Voice API — Voice Wake + Talk Mode control from the dashboard."""

import json
import logging
from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)

bp = Blueprint("voice", __name__)


def _get_daemon():
    from ghost_dashboard import get_daemon
    return get_daemon()


def _get_engine():
    """Get or create the VoiceEngine singleton."""
    try:
        from ghost_voice import _get_engine, _check_audio_deps
        daemon = _get_daemon()
        if not daemon:
            return None, "Ghost daemon not running"
        missing = _check_audio_deps()
        if missing:
            return None, f"Missing audio dependencies: {', '.join(missing)}. Install with: pip install {' '.join(missing)}"
        cfg = daemon.cfg if daemon else {}
        auth_store = getattr(daemon, "auth_store", None)
        return _get_engine(cfg, auth_store), None
    except ImportError:
        return None, "Voice module not available"


@bp.route("/api/voice/status")
def voice_status():
    engine, err = _get_engine()
    if err:
        return jsonify({
            "ok": False,
            "error": err,
            "state": "unavailable",
            "deps_missing": True,
        })
    return jsonify({"ok": True, **engine.get_status()})


@bp.route("/api/voice/wake/start", methods=["POST"])
def voice_wake_start():
    engine, err = _get_engine()
    if err:
        return jsonify({"ok": False, "error": err}), 503

    data = request.get_json(silent=True) or {}
    wake_words = data.get("wake_words")
    if wake_words:
        engine.set_wake_words(wake_words)
    result = engine.start_wake()
    ok = "started" in result.lower() or "already" in result.lower()
    return jsonify({"ok": ok, "message": result})


@bp.route("/api/voice/wake/stop", methods=["POST"])
def voice_wake_stop():
    engine, err = _get_engine()
    if err:
        return jsonify({"ok": False, "error": err}), 503
    result = engine.stop()
    return jsonify({"ok": True, "message": result})


@bp.route("/api/voice/talk/start", methods=["POST"])
def voice_talk_start():
    engine, err = _get_engine()
    if err:
        return jsonify({"ok": False, "error": err}), 503
    result = engine.start_talk()
    ok = "started" in result.lower() or "already" in result.lower()
    return jsonify({"ok": ok, "message": result})


@bp.route("/api/voice/talk/stop", methods=["POST"])
def voice_talk_stop():
    engine, err = _get_engine()
    if err:
        return jsonify({"ok": False, "error": err}), 503
    result = engine.stop()
    return jsonify({"ok": True, "message": result})


@bp.route("/api/voice/speak", methods=["POST"])
def voice_speak():
    """Speak text aloud via TTS + playback. Fire-and-forget."""
    engine, err = _get_engine()
    if err:
        return jsonify({"ok": False, "error": err}), 503
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "No text"})
    import threading
    threading.Thread(
        target=engine._speak, args=(text,), daemon=True, name="ghost-voice-speak",
    ).start()
    return jsonify({"ok": True})


@bp.route("/api/voice/ptt/start", methods=["POST"])
def voice_ptt_start():
    """Start push-to-talk: one-shot capture → transcribe → return text."""
    engine, err = _get_engine()
    if err:
        return jsonify({"ok": False, "error": err}), 503
    result = engine.start_ptt()
    return jsonify(result)


@bp.route("/api/voice/ptt/status")
def voice_ptt_status():
    """Poll PTT state. Returns {state, text, error}."""
    engine, err = _get_engine()
    if err:
        return jsonify({"ok": False, "error": err}), 503
    return jsonify({"ok": True, **engine.ptt_status()})


@bp.route("/api/voice/config", methods=["GET"])
def voice_config_get():
    daemon = _get_daemon()
    if not daemon:
        return jsonify({"ok": False, "error": "Daemon not running"}), 503
    cfg = daemon.cfg
    return jsonify({
        "ok": True,
        "enable_voice": cfg.get("enable_voice", True),
        "voice_wake_words": cfg.get("voice_wake_words", ["ghost", "hey ghost"]),
        "voice_stt_provider": cfg.get("voice_stt_provider", "auto"),
        "voice_silence_threshold": cfg.get("voice_silence_threshold", 0.02),
        "voice_silence_duration": cfg.get("voice_silence_duration", 2.0),
        "voice_chime": cfg.get("voice_chime", True),
    })


@bp.route("/api/voice/config", methods=["PUT"])
def voice_config_set():
    daemon = _get_daemon()
    if not daemon:
        return jsonify({"ok": False, "error": "Daemon not running"}), 503

    data = request.get_json(force=True)
    engine, _ = _get_engine()

    allowed = {
        "voice_wake_words", "voice_stt_provider",
        "voice_silence_threshold", "voice_silence_duration", "voice_chime",
    }

    updated = []
    for key, val in data.items():
        if key not in allowed:
            continue
        daemon.cfg[key] = val
        updated.append(key)

        if engine:
            if key == "voice_wake_words" and isinstance(val, list):
                engine.set_wake_words(val)
            elif key == "voice_silence_threshold":
                engine.silence_threshold = max(0.001, min(1.0, float(val)))
            elif key == "voice_silence_duration":
                engine.silence_duration = max(0.5, min(10.0, float(val)))
            elif key == "voice_stt_provider":
                engine.stt_provider = str(val)
            elif key == "voice_chime":
                engine.chime_enabled = bool(val)

    if updated:
        try:
            from pathlib import Path
            cfg_path = Path.home() / ".ghost" / "config.json"
            if cfg_path.exists():
                current = json.loads(cfg_path.read_text(encoding="utf-8"))
            else:
                current = {}
            for k in updated:
                current[k] = daemon.cfg[k]
            cfg_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        except Exception:
            log.warning("Failed to save voice config", exc_info=True)

    return jsonify({"ok": True, "updated": updated})
