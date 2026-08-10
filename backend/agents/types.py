"""Tipos e classes de dados compartilhados."""
from backend.tools.region_extractor import Region

class RegionTask:
    __slots__ = ("agent_target", "classification", "text", "image_bytes", "region", "page_num", "scientific_context")
    def __init__(self, agent_target: str, classification: str, text: str = "", image_bytes: bytes | None = None, region: Region | None = None, page_num: int = 0, scientific_context: str | None = None):
        self.agent_target = agent_target
        self.classification = classification
        self.text = text
        self.image_bytes = image_bytes
        self.region = region
        self.page_num = page_num
        self.scientific_context = scientific_context
