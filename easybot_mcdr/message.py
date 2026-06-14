from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, List, Optional


class SegmentType(IntEnum):
    UNKNOWN = 1
    TEXT = 2
    IMAGE = 3
    AT = 4
    FILE = 5
    REPLY = 6
    FACE = 7


@dataclass
class Segment:
    type: int

    def to_dict(self) -> Dict[str, Any]:
        d = {"type": int(self.type)}
        d.update({k: v for k, v in self.__dict__.items() if k != "type"})
        return d

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Segment":
        seg_type = data.get("type", SegmentType.UNKNOWN)
        mapping = {
            SegmentType.TEXT: TextSegment,
            SegmentType.IMAGE: ImageSegment,
            SegmentType.FILE: FileSegment,
            SegmentType.AT: AtSegment,
            SegmentType.REPLY: ReplySegment,
            SegmentType.FACE: FaceSegment,
        }
        cls = mapping.get(seg_type, UnknownSegment)
        return cls(**{k: v for k, v in data.items() if k != "type"})


@dataclass
class TextSegment(Segment):
    text: str

    def __init__(self, text: str, **_kw):
        super().__init__(SegmentType.TEXT)
        self.text = text


@dataclass
class ImageSegment(Segment):
    url: str
    summary: Optional[str] = None

    def __init__(self, url: str, summary: Optional[str] = None, **_kw):
        super().__init__(SegmentType.IMAGE)
        self.url = url
        self.summary = summary


@dataclass
class FileSegment(Segment):
    file_url: str
    name: Optional[str] = None

    def __init__(self, file_url: str = "", url: str = "", name: Optional[str] = None, **_kw):
        super().__init__(SegmentType.FILE)
        self.file_url = file_url or url
        self.name = name


@dataclass
class AtSegment(Segment):
    at_user_name: str
    at_user_id: str
    at_player_names: List[str]

    def __init__(self, at_user_name: str = "", at_user_id: str = "",
                 at_player_names: Optional[List[str]] = None, target: str = "", **_kw):
        super().__init__(SegmentType.AT)
        self.at_user_name = at_user_name or target
        self.at_user_id = at_user_id
        self.at_player_names = at_player_names or []


@dataclass
class ReplySegment(Segment):
    message_id: str
    text: Optional[str] = None

    def __init__(self, message_id: str = "", text: Optional[str] = None, **_kw):
        super().__init__(SegmentType.REPLY)
        self.message_id = message_id
        self.text = text


@dataclass
class FaceSegment(Segment):
    id: Optional[int] = None
    display_name: Optional[str] = None

    def __init__(self, id: Optional[int] = None, display_name: Optional[str] = None, **_kw):
        super().__init__(SegmentType.FACE)
        self.id = id
        self.display_name = display_name


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
