"""Seed a demo voice catalog (all synthetic) and print the eval summary.

Usage: python run_demo.py
"""
from voice_catalog.service import EvalHistory, analytics_summary, run_eval
from voice_catalog.store import Store, VoiceStatus


def seed(store: Store, history: EvalHistory):
    # Four demo voices across three languages and several styles.
    voices = [
        store.register_voice("Mara — Warm Narrator", "en-US",
                             ["warm", "narrative", "audiobook"], "recording", VoiceStatus.ACTIVE),
        store.register_voice("Theo — Energetic Host", "en-US",
                             ["energetic", "conversational", "podcast"], "text-prompt", VoiceStatus.ACTIVE),
        store.register_voice("Lucía — Calm Guide", "es-ES",
                             ["calm", "educational"], "reference-voice", VoiceStatus.ACTIVE),
        store.register_voice("Aiko — Bright Assistant", "ja-JP",
                             ["bright", "assistant"], "recording", VoiceStatus.DRAFT),
    ]
    for voice in voices:
        store.add_version(voice.id, "v1", "initial trained version")
    store.add_version(voices[0].id, "v2", "re-trained on cleaner recordings")

    # Eval runs: three pass, one fails the similarity gate, one is so
    # poor its composite score quarantines the voice.
    runs = [
        run_eval(store, history, voices[0].id, "v2", 0.92, 0.88, 420, 0.95),
        run_eval(store, history, voices[1].id, "v1", 0.85, 0.81, 610, 0.90),
        run_eval(store, history, voices[2].id, "v1", 0.88, 0.79, 530, 0.86),
        run_eval(store, history, voices[1].id, "v1", 0.90, 0.58, 480, 0.92),  # similarity gate fails
        run_eval(store, history, voices[3].id, "v1", 0.52, 0.48, 1400, 0.55),  # quarantined
    ]
    return voices, runs


if __name__ == "__main__":
    store = Store()
    history = EvalHistory()
    voices, runs = seed(store, history)
    for voice in voices:
        print(f"voice {voice.id}: {voice.name} [{voice.language}] "
              f"styles={voice.style_tags} status={voice.status.value}")
    print()
    for run in runs:
        print(f"eval voice {run.voice_id} {run.version}: composite={run.composite} "
              f"passed={run.passed} quarantine={run.quarantine} "
              f"failed_gates={run.failed_gates}")
    print()
    summary = analytics_summary(store, history)
    print("analytics:", summary)
    print()
    print("search en-US:", [v.name for v in store.list_voices(language="en-US")])
    print("search style=calm:", [v.name for v in store.list_voices(style="calm")])
    print("search quarantined:", [v.name for v in store.list_voices(status="quarantined")])
