"""Voice registry: register voices, versions, search and filter.

A voice is one entry in the catalog a customer can find, clone or
design: an id, a name, a language/locale, style tags, a clone source
(recording, text prompt, or reference voice), a status, and immutable
versions (v1, v2, ...) so a re-trained voice never overwrites the one
customers already use.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

# BCP 47-ish locale: "en", "en-US", "es-ES", "ja-JP", ...
_LOCALE_RE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
_CLONE_SOURCES = ("recording", "text-prompt", "reference-voice")


class VoiceStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    QUARANTINED = "quarantined"


@dataclass
class VoiceVersion:
    version: str
    note: str = ""
    created_by: str = ""


@dataclass
class Voice:
    id: int
    name: str
    language: str  # locale, e.g. "en-US"
    style_tags: list[str] = field(default_factory=list)
    clone_source: str = "recording"
    status: VoiceStatus = VoiceStatus.DRAFT
    versions: list[VoiceVersion] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "language": self.language,
            "style_tags": list(self.style_tags),
            "clone_source": self.clone_source,
            "status": self.status.value,
            "versions": [
                {"version": v.version, "note": v.note, "created_by": v.created_by}
                for v in self.versions
            ],
        }


class Store:
    """In-memory voice registry with validation and dedup."""

    def __init__(self) -> None:
        self._voices: dict[int, Voice] = {}
        self._next_id = 1

    # -- registration -------------------------------------------------
    def register_voice(
        self,
        name: str,
        language: str,
        style_tags: list[str] | None = None,
        clone_source: str = "recording",
        status: VoiceStatus | str = VoiceStatus.DRAFT,
    ) -> Voice:
        name = (name or "").strip()
        if not name:
            raise ValueError("name is required")
        language = (language or "").strip()
        if not _LOCALE_RE.match(language):
            raise ValueError(f"invalid language/locale: {language!r} (expected e.g. 'en-US')")
        if clone_source not in _CLONE_SOURCES:
            raise ValueError(f"invalid clone_source: {clone_source!r} (expected one of {_CLONE_SOURCES})")
        tags = sorted({t.strip().lower() for t in (style_tags or []) if t.strip()})
        if isinstance(status, str):
            status = VoiceStatus(status)
        # Dedup: same name + language + clone source is the same voice.
        for existing in self._voices.values():
            if (
                existing.name.lower() == name.lower()
                and existing.language == language
                and existing.clone_source == clone_source
            ):
                raise ValueError(
                    f"duplicate voice: {name!r} ({language}, {clone_source}) already registered as id {existing.id}"
                )
        voice = Voice(
            id=self._next_id,
            name=name,
            language=language,
            style_tags=tags,
            clone_source=clone_source,
            status=status,
        )
        self._voices[voice.id] = voice
        self._next_id += 1
        return voice

    def get_voice(self, voice_id: int) -> Voice:
        try:
            return self._voices[voice_id]
        except KeyError:
            raise KeyError(f"no voice with id {voice_id}") from None

    def set_status(self, voice_id: int, status: VoiceStatus | str) -> Voice:
        voice = self.get_voice(voice_id)
        if isinstance(status, str):
            status = VoiceStatus(status)
        voice.status = status
        return voice

    def add_version(self, voice_id: int, version: str, note: str = "", created_by: str = "") -> VoiceVersion:
        voice = self.get_voice(voice_id)
        version = version.strip()
        if not version:
            raise ValueError("version is required")
        if any(v.version == version for v in voice.versions):
            raise ValueError(f"voice {voice_id} already has version {version!r}")
        entry = VoiceVersion(version=version, note=note, created_by=created_by)
        voice.versions.append(entry)
        return entry

    # -- search -------------------------------------------------------
    def list_voices(
        self,
        query: str | None = None,
        language: str | None = None,
        style: str | None = None,
        status: VoiceStatus | str | None = None,
    ) -> list[Voice]:
        results = list(self._voices.values())
        if query:
            q = query.strip().lower()
            results = [v for v in results if q in v.name.lower()]
        if language:
            results = [v for v in results if v.language == language]
        if style:
            results = [v for v in results if style.strip().lower() in v.style_tags]
        if status is not None:
            if isinstance(status, str):
                status = VoiceStatus(status)
            results = [v for v in results if v.status == status]
        return sorted(results, key=lambda v: v.id)
