from pathlib import Path

import pysubs2
from pydantic import BaseModel


class SubtitleEntry(BaseModel):
    index: int
    start_s: float
    end_s: float
    text: str
    plaintext: str


class SubtitleDoc(BaseModel):
    entries: list[SubtitleEntry] = []
    language: str | None = None
    title: str | None = None
    forced: bool = False


def load(path: Path) -> SubtitleDoc:
    subs = pysubs2.load(str(path))
    entries = [
        SubtitleEntry(
            index=i,
            start_s=line.start / 1000.0,
            end_s=line.end / 1000.0,
            text=line.text,
            plaintext=line.plaintext,
        )
        for i, line in enumerate(subs)
    ]
    return SubtitleDoc(entries=entries)


def save(doc: SubtitleDoc, path: Path) -> None:
    subs = pysubs2.SSAFile()
    for entry in doc.entries:
        subs.append(
            pysubs2.SSAEvent(
                start=round(entry.start_s * 1000),
                end=round(entry.end_s * 1000),
                text=entry.text,
            )
        )
    subs.save(str(path))
