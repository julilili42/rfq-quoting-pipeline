"""Input handling: file-type detection and mail parsing."""
from .file_types import detect_file_type
from .mail import MailData, parse_mail

__all__ = ["detect_file_type", "parse_mail", "MailData"]
