from __future__ import annotations

import base64
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def _read_txt(path: Path) -> str:
    for encoding in ("utf-8", "utf-16", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return ""


def _extract_docx(path: Path) -> str:
    try:
        import docx  # type: ignore

        document = docx.Document(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text)
    except Exception:
        pass

    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
        root = ET.fromstring(xml)
        texts: list[str] = []
        for node in root.iter():
            if node.tag.endswith("}t") and node.text:
                texts.append(node.text)
        return " ".join(texts)
    except Exception:
        return ""


def _extract_xlsx(path: Path) -> str:
    try:
        import openpyxl  # type: ignore

        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        parts: list[str] = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                values = [str(cell) for cell in row if cell is not None]
                if values:
                    parts.append(" ".join(values))
        workbook.close()
        return "\n".join(parts)
    except Exception:
        pass

    try:
        with zipfile.ZipFile(path) as zf:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                for node in root.iter():
                    if node.tag.endswith("}t") and node.text:
                        shared.append(node.text)
            sheet_parts: list[str] = []
            for name in zf.namelist():
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                    root = ET.fromstring(zf.read(name))
                    for node in root.iter():
                        if node.tag.endswith("}v") and node.text:
                            sheet_parts.append(node.text)
            return " ".join(shared + sheet_parts)
    except Exception:
        return ""


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages[:10]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(part for part in parts if part)
    except Exception:
        pass

    try:
        data = path.read_bytes().decode("latin-1", errors="ignore")
        matches = re.findall(r"\(([^()]{3,200})\)", data)
        return " ".join(matches[:200])
    except Exception:
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

