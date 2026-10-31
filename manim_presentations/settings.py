"""talk.toml: the one loader. Every default below says where it came from; a talk that overrides a key in a table
must give that table an `origin` string stating where its numbers came from (origins are data, so this is enforced).
The result is one frozen Settings value, passed downstream (to scene subprocesses as JSON on argv)."""

import tomllib
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

FRAME_HEIGHT_UNITS = 8.0  # Manim's frame height; frame_width follows the pixels' shape so a unit stays square
SCALE_FACTOR_PER_FONT_POINT = 1 / 960  # manim/constants.py: scene units per font_size point

EXAMPLE = """[render]
pixel_width = 3456
pixel_height = 2168
origin = "native Audience window, 1728×1084 pt at 2×"
"""


class SettingsError(Exception):
    pass


class _Table(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    origin: str = ""

    @model_validator(mode="after")
    def _origin_required(self) -> Self:
        overridden = sorted(self.model_fields_set - {"origin"})
        if overridden and not self.origin.strip():
            raise ValueError(
                f"overrides {', '.join(overridden)} without an `origin` saying where the numbers came "
                f"from, for example:\n{EXAMPLE}"
            )
        return self


class _Render(_Table):
    pixel_width: int = 1920  # 16:9: the shape of browsers, projectors and screen shares
    pixel_height: int = 1080
    frame_width: float | None = None  # None: FRAME_HEIGHT_UNITS · W / H
    frame_rate: int = 30  # Manim's default, and what Mixing Deluxe uses
    background: str = "#000000"  # black chapter cards (D11) and a true-black stage


class _Checks(_Table):
    # Declared font_size as a fraction of frame height. Provisional until P6: Explainers' minimums 32 (Pango text)
    # and 40 (LaTeX), Minh's picks from its size ladder at frame height 8 (explainers/geometry.py MIN_TEXT,
    # MIN_LATEX), converted by SCALE_FACTOR_PER_FONT_POINT / 8. Text and TeX set differently at equal font_size.
    min_text: float = 32 * SCALE_FACTOR_PER_FONT_POINT / FRAME_HEIGHT_UNITS
    min_tex: float = 40 * SCALE_FACTOR_PER_FONT_POINT / FRAME_HEIGHT_UNITS


class _TalkToml(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    render: _Render = _Render()
    checks: _Checks = _Checks()


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    pixel_width: int
    pixel_height: int
    frame_width: float
    frame_rate: int
    background: str
    min_text: float
    min_tex: float

    @property
    def frame_height(self) -> float:
        return FRAME_HEIGHT_UNITS

    @model_validator(mode="after")
    def _even(self) -> Self:
        if self.pixel_width % 2 or self.pixel_height % 2:  # H.264 yuv420p needs even dimensions
            raise ValueError(f"pixel size {self.pixel_width}×{self.pixel_height} must be even in both dimensions")
        return self

    def to_argv(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_argv(cls, text: str) -> "Settings":
        return cls.model_validate_json(text)


def load(talk_root: Path) -> Settings:
    path = talk_root / "talk.toml"
    try:
        toml = _TalkToml.model_validate(tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {})
        r, c = toml.render, toml.checks
        frame_width = FRAME_HEIGHT_UNITS * r.pixel_width / r.pixel_height if r.frame_width is None else r.frame_width
        return Settings(
            pixel_width=r.pixel_width,
            pixel_height=r.pixel_height,
            frame_width=frame_width,
            frame_rate=r.frame_rate,
            background=r.background,
            min_text=c.min_text,
            min_tex=c.min_tex,
        )
    except (ValidationError, tomllib.TOMLDecodeError) as e:
        raise SettingsError(f"{path}: {e}") from e
