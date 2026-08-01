"""Compatibilidad entre pypdf y PyPDF2."""

try:
    from pypdf import PdfReader, PdfWriter
except ModuleNotFoundError:
    from PyPDF2 import PdfReader, PdfWriter

__all__ = ["PdfReader", "PdfWriter"]
