from backend.pipeline.scientific.detector import detect_document_profile
from backend.pipeline.scientific.models import DocumentProfile, RequestedDocumentProfile

__all__ = [
    "DocumentProfile",
    "RequestedDocumentProfile",
    "detect_document_profile",
]