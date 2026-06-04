from __future__ import annotations

import logging
import zipfile
from pathlib import Path

# Use defusedxml for safe XML parsing (prevents XML bombs / Billion Laughs
# attacks when processing untrusted Office documents). Falls back to the
# standard library parser if defusedxml is unavailable.
try:
    from defusedxml.ElementTree import fromstring as _safe_fromstring
except ImportError:
    from xml.etree.ElementTree import fromstring as _safe_fromstring


MAX_EXTRACT_SIZE = 50 * 1024 * 1024
MAX_EXTRACT_PAGES = 10
# Hard cap on the number of characters the extractor returns, regardless
# of the source file size. This bounds memory and prevents the FTS index
# from being poisoned by a 50 MB text file or a pathologically large
# Office document. 1 MB is well above anything the LLM provider will
# read anyway (the user_prompt uses text_excerpt(..., 300)).
_MAX_EXTRACT_CHARS = 1_000_000


def _check_size(path: Path) -> bool:
    try:
        return path.stat().st_size <= MAX_EXTRACT_SIZE
    except OSError:
        return False


def _read_txt(path: Path) -> str:
    if not _check_size(path):
        logging.warning("File too large for text extraction: %s", path)
        return ""
    for encoding in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            if len(text) > _MAX_EXTRACT_CHARS:
                logging.info("Truncating %s at %d chars for extraction", path, _MAX_EXTRACT_CHARS)
                return text[:_MAX_EXTRACT_CHARS]
            return text
        except Exception:
            continue
    logging.warning("TXT extraction failed for %s: no encoding worked", path)
    return ""


def _extract_docx(path: Path) -> str:
    if not _check_size(path):
        logging.warning("File too large for DOCX extraction: %s", path)
        return ""
    try:
        import docx

        document = docx.Document(str(path))
        parts: list[str] = []
        for paragraph in document.paragraphs:
            if not paragraph.text:
                continue
            parts.append(paragraph.text)
            if sum(len(p) for p in parts) > _MAX_EXTRACT_CHARS:
                logging.info("Truncating DOCX %s at %d chars", path, _MAX_EXTRACT_CHARS)
                return "\n".join(parts)[:_MAX_EXTRACT_CHARS]
        return "\n".join(parts)
    except Exception:
        pass

    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
        root = _safe_fromstring(xml)
        texts: list[str] = []
        running = 0
        for node in root.iter():
            if node.tag.endswith("}t") and node.text:
                texts.append(node.text)
                running += len(node.text)
                if running > _MAX_EXTRACT_CHARS:
                    logging.info("Truncating DOCX XML for %s at %d chars", path, _MAX_EXTRACT_CHARS)
                    return " ".join(texts)[:_MAX_EXTRACT_CHARS]
        return " ".join(texts)
    except Exception as exc:
        logging.warning("DOCX zip/XML fallback failed for %s: %s", path, exc)
        return ""


def _extract_xlsx(path: Path) -> str:
    if not _check_size(path):
        logging.warning("File too large for XLSX extraction: %s", path)
        return ""
    try:
        import openpyxl

        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        parts: list[str] = []
        running = 0
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                values = [str(cell) for cell in row if cell is not None]
                if values:
                    joined = " ".join(values)
                    parts.append(joined)
                    running += len(joined)
                    if running > _MAX_EXTRACT_CHARS:
                        logging.info("Truncating XLSX %s at %d chars", path, _MAX_EXTRACT_CHARS)
                        workbook.close()
                        return "\n".join(parts)[:_MAX_EXTRACT_CHARS]
        workbook.close()
        return "\n".join(parts)
    except Exception:
        pass

    try:
        with zipfile.ZipFile(path) as zf:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                root = _safe_fromstring(zf.read("xl/sharedStrings.xml"))
                for node in root.iter():
                    if node.tag.endswith("}t") and node.text:
                        shared.append(node.text)
            sheet_parts: list[str] = []
            running = sum(len(s) for s in shared)
            for name in zf.namelist():
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                    root = _safe_fromstring(zf.read(name))
                    for node in root.iter():
                        if node.tag.endswith("}v") and node.text:
                            sheet_parts.append(node.text)
                            running += len(node.text)
                            if running > _MAX_EXTRACT_CHARS:
                                logging.info("Truncating XLSX XML for %s at %d chars", path, _MAX_EXTRACT_CHARS)
                                return " ".join(shared + sheet_parts)[:_MAX_EXTRACT_CHARS]
            return " ".join(shared + sheet_parts)
    except Exception as exc:
        logging.warning("XLSX zip/XML fallback failed for %s: %s", path, exc)
        return ""


def _extract_pdf(path: Path) -> str:
    if not _check_size(path):
        logging.warning("File too large for PDF extraction: %s", path)
        return ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages[:MAX_EXTRACT_PAGES]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(part for part in parts if part)
    except Exception as exc:
        logging.warning("PDF extraction failed for %s: %s", path, exc)
        return ""


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return _read_txt(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".xlsx":
        return _extract_xlsx(path)
    if suffix == ".pdf":
        return _extract_pdf(path)
    return ""


def is_readable_text(path: Path) -> bool:
    return bool(extract_text(path).strip())

