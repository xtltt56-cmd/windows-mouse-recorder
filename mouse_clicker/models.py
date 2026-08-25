from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


EVENT_TYPES = {"move", "button", "scroll"}
BUTTONS = {"left", "right", "middle"}
BUTTON_ACTIONS = {"press", "release"}


@dataclass(frozen=True)
class ScreenGeometry:
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self):
        if not isinstance(self.left, int) or not isinstance(self.top, int):
            raise ValueError("screen origin must be integers")
        if not isinstance(self.width, int) or not isinstance(self.height, int):
            raise ValueError("screen size must be integers")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("screen width and height must be positive")

    def to_dict(self) -> Dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "ScreenGeometry":
        return cls(
            left=int(value["left"]),
            top=int(value["top"]),
            width=int(value["width"]),
            height=int(value["height"]),
        )


@dataclass(frozen=True)
class MouseEvent:
    type: str
    x: int
    y: int
    delay_ms: float
    action: Optional[str] = None
    button: Optional[str] = None
    dx: int = 0
    dy: int = 0

    def __post_init__(self):
        if self.type not in EVENT_TYPES:
            raise ValueError("unsupported event type: {}".format(self.type))
        if not isinstance(self.x, int) or not isinstance(self.y, int):
            raise ValueError("mouse coordinates must be integers")
        if self.delay_ms < 0:
            raise ValueError("delay_ms must not be negative")
        if self.type == "button":
            if self.action not in BUTTON_ACTIONS or self.button not in BUTTONS:
                raise ValueError("button event requires a valid action and button")
        elif self.type == "scroll":
            if self.dx == 0 and self.dy == 0:
                raise ValueError("scroll event must have a non-zero delta")
            if self.action is not None or self.button is not None:
                raise ValueError("scroll event cannot contain button fields")
        elif self.action is not None or self.button is not None:
            raise ValueError("move event cannot contain button fields")

    def to_dict(self) -> Dict[str, Any]:
        value = {
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "delay_ms": self.delay_ms,
        }
        if self.action is not None:
            value["action"] = self.action
        if self.button is not None:
            value["button"] = self.button
        if self.type == "scroll":
            value["dx"] = self.dx
            value["dy"] = self.dy
        return value

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "MouseEvent":
        return cls(
            type=str(value["type"]),
            x=int(value["x"]),
            y=int(value["y"]),
            delay_ms=float(value["delay_ms"]),
            action=value.get("action"),
            button=value.get("button"),
            dx=int(value.get("dx", 0)),
            dy=int(value.get("dy", 0)),
        )


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    screen: ScreenGeometry
    events: List[MouseEvent] = field(default_factory=list)
    version: int = 1

    def __post_init__(self):
        if not self.id.strip():
            raise ValueError("template id is required")
        if not self.name.strip():
            raise ValueError("template name is required")
        if self.version != 1:
            raise ValueError("unsupported template version: {}".format(self.version))

    @property
    def duration_ms(self) -> float:
        return sum(event.delay_ms for event in self.events)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "name": self.name,
            "screen": self.screen.to_dict(),
            "events": [event.to_dict() for event in self.events],
        }

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Template":
        return cls(
            version=int(value.get("version", 1)),
            id=str(value["id"]),
            name=str(value["name"]),
            screen=ScreenGeometry.from_dict(value["screen"]),
            events=[MouseEvent.from_dict(item) for item in value.get("events", [])],
        )


@dataclass(frozen=True)
class PlaybackConfig:
    loops: Optional[int]

    @property
    def is_infinite(self) -> bool:
        return self.loops is None

    @classmethod
    def fixed(cls, loops: int) -> "PlaybackConfig":
        if isinstance(loops, bool) or not isinstance(loops, int) or loops <= 0:
            raise ValueError("fixed loop count must be a positive integer")
        return cls(loops=loops)

    @classmethod
    def infinite(cls) -> "PlaybackConfig":
        return cls(loops=None)


def parse_playback_config(raw: str, infinite: bool) -> PlaybackConfig:
    if infinite:
        return PlaybackConfig.infinite()
    try:
        loops = int(raw.strip())
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("loop count must be a positive integer") from exc
    return PlaybackConfig.fixed(loops)
