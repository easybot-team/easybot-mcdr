from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class SegmentType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    AT = "at"
    REPLY = "reply"
    UNKNOWN = "unknown"


@dataclass
class Segment:
    type: SegmentType

    def to_dict(self) -> Dict[str, Any]:
        d = {"type": self.type}
        d.update({k: v for k, v in self.__dict__.items() if k != "type"})
        return d

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Segment":
        seg_type = SegmentType(data.get("type", SegmentType.UNKNOWN))
        mapping = {
            SegmentType.TEXT: TextSegment,
            SegmentType.IMAGE: ImageSegment,
            SegmentType.FILE: FileSegment,
            SegmentType.AT: AtSegment,
            SegmentType.REPLY: ReplySegment,
        }
        cls = mapping.get(seg_type, UnknownSegment)
        return cls(**{k: v for k, v in data.items() if k != "type"})


@dataclass
class TextSegment(Segment):
    text: str

    def __init__(self, text: str):
        super().__init__(SegmentType.TEXT)
        self.text = text


@dataclass
class ImageSegment(Segment):
    url: str

    def __init__(self, url: str):
        super().__init__(SegmentType.IMAGE)
        self.url = url


@dataclass
class FileSegment(Segment):
    url: str
    name: Optional[str] = None

    def __init__(self, url: str, name: Optional[str] = None):
        super().__init__(SegmentType.FILE)
        self.url = url
        self.name = name


@dataclass
class AtSegment(Segment):
    target: str

    def __init__(self, target: str):
        super().__init__(SegmentType.AT)
        self.target = target


@dataclass
class ReplySegment(Segment):
    message_id: str
    text: Optional[str] = None

    def __init__(self, message_id: str, text: Optional[str] = None):
        super().__init__(SegmentType.REPLY)
        self.message_id = message_id
        self.text = text


@dataclass
class UnknownSegment(Segment):
    raw: Dict[str, Any]

    def __init__(self, **raw: Any):
        super().__init__(SegmentType.UNKNOWN)
        self.raw = raw


def segments_from_list(data: List[Dict[str, Any]]) -> List[Segment]:
    return [Segment.from_dict(item) for item in data or []]


def segments_to_list(segments: List[Segment]) -> List[Dict[str, Any]]:
    return [seg.to_dict() for seg in segments]
