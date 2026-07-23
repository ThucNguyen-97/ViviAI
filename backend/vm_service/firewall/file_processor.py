import hashlib
import re
import shutil
import uuid
from pathlib import Path
from typing import Sequence

from fastapi import HTTPException, UploadFile, status
from openpyxl import load_workbook, Workbook

from core.config import settings
from ek_client import ek_client
from firewall import ai_firewall
from firewall.schemas import FirewallDecision, ProcessedFile, UserContext


FILE_REJECT_MESSAGE = "Tệp tin bạn gửi không phù hợp với chính sách hệ thống"
ALLOWED_EXTENSIONS = {".xlsx", ".png", ".md"}
PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s+prompt",
    r"developer\s+message",
    r"jailbreak",
    r"bypass",
]


def upload_root() -> Path:
    root = Path(settings.UPLOAD_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _max_size(extension: str) -> int:
    return {
        ".md": settings.MAX_MD_BYTES,
        ".png": settings.MAX_PNG_BYTES,
        ".xlsx": settings.MAX_XLSX_BYTES,
    }[extension]


def _safe_name(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name or len(name) > 255 or any(ord(ch) < 32 for ch in name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FILE_REJECT_MESSAGE)
    return name


def _flags_for_markdown(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    flags: list[str] = []
    if re.search(r"<\s*script\b|<\s*iframe\b|javascript:", text, re.IGNORECASE):
        flags.append("html_or_script")
    if "file://" in text.lower():
        flags.append("local_file_link")
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in PROMPT_INJECTION_PATTERNS):
        flags.append("prompt_injection_phrase")
    return flags


def _sanitize_xlsx(raw_path: Path, target_path: Path) -> None:
    workbook = load_workbook(
        raw_path,
        read_only=False,
        keep_vba=False,
        data_only=True,
        keep_links=False,
    )
    clean = Workbook()
    default = clean.active
    clean.remove(default)

    for source in workbook.worksheets:
        target = clean.create_sheet(title=source.title[:31] or "Sheet")
        for row in source.iter_rows():
            for cell in row:
                target[cell.coordinate].value = cell.value

    clean.save(target_path)


async def _store_in_ek(
    processed: ProcessedFile,
    *,
    user: UserContext,
    decision: FirewallDecision,
    metadata: dict,
) -> ProcessedFile:
    response = await ek_client.upload_clean_file(
        path=Path(processed.clean_path),
        original_file_name=processed.original_file_name,
        uploaded_by=user.user_id,
        file_type=processed.file_type,
        mime_type=processed.mime_type,
        raw_vm_path=processed.raw_path,
        sanitized=processed.sanitized,
        firewall_result=decision.model_dump(),
        metadata=metadata,
    )
    processed.ek_file_id = response["id"]
    return processed


async def process_uploads(files: Sequence[UploadFile], user: UserContext) -> list[ProcessedFile]:
    if len(files) > settings.MAX_FILES_PER_REQUEST:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FILE_REJECT_MESSAGE)

    processed_files: list[ProcessedFile] = []
    for upload in files:
        original_name = _safe_name(upload.filename or "")
        extension = Path(original_name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FILE_REJECT_MESSAGE)

        data = await upload.read()
        if len(data) > _max_size(extension):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FILE_REJECT_MESSAGE)

        raw_path = upload_root() / f"{uuid.uuid4()}{extension}"
        raw_path.write_bytes(data)

        clean_path = upload_root() / f"{uuid.uuid4()}{extension}"
        flags: list[str] = []
        decision = FirewallDecision(allowed=True, recommended_intent="task_execution")
        sanitized = False

        try:
            if extension == ".xlsx":
                _sanitize_xlsx(raw_path, clean_path)
                sanitized = True
            elif extension == ".md":
                flags = _flags_for_markdown(raw_path)
                decision = await ai_firewall.check_markdown_file(raw_path, user, flags)
                if not decision.allowed:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FILE_REJECT_MESSAGE)
                shutil.copyfile(raw_path, clean_path)
            elif extension == ".png":
                decision = await ai_firewall.check_png_file(raw_path, user)
                if not decision.allowed:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FILE_REJECT_MESSAGE)
                if data[:8] != b"\x89PNG\r\n\x1a\n":
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FILE_REJECT_MESSAGE)
                shutil.copyfile(raw_path, clean_path)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FILE_REJECT_MESSAGE) from exc

        checksum = hashlib.sha256(clean_path.read_bytes()).hexdigest()
        processed = ProcessedFile(
            original_file_name=original_name,
            file_type=extension.lstrip("."),
            raw_path=str(raw_path),
            clean_path=str(clean_path),
            mime_type=upload.content_type,
            sanitized=sanitized,
            flags=flags,
        )
        processed = await _store_in_ek(
            processed,
            user=user,
            decision=decision,
            metadata={"flags": flags, "checksum_sha256": checksum, "content_type_seen": upload.content_type},
        )
        processed_files.append(processed)

    return processed_files
