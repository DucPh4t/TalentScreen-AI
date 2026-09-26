"""Private blob storage manager with strict path traversal guards and MIME signature checks."""
from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Optional
import uuid

from fastapi import HTTPException, status

from app.config import get_settings

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit for MVP CV uploads
PDF_MAGIC = b"%PDF-"
DOCX_MAGIC = b"PK\x03\x04"

SAFE_FILENAME_RE = re.compile(r"[^a-zA-Z0-9_.-]")


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal, null byte injections, and shell meta-characters."""
    # Strip null bytes and directory paths
    clean = os.path.basename(filename.replace("\x00", "").replace("\\", "/"))
    clean = SAFE_FILENAME_RE.sub("_", clean)
    if not clean or clean.startswith("."):
        clean = f"document_{uuid.uuid4().hex[:8]}.bin"
    return clean[:200]


def get_storage_base_dir() -> Path:
    """Get absolute path to private storage directory, ensuring it exists."""
    settings = get_settings()
    base_dir = Path(settings.PRIVATE_STORAGE_ROOT).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def resolve_blob_path(blob_key: str) -> Path:
    """Resolve blob path and guarantee it does not escape the private storage root."""
    base_dir = get_storage_base_dir()
    # Normalize blob_key by removing leading slashes
    clean_key = blob_key.lstrip("/\\")
    target_path = (base_dir / clean_key).resolve()

    # Path traversal guard: target_path must be inside base_dir
    try:
        target_path.relative_to(base_dir)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PATH_TRAVERSAL_DETECTED: Blob key resolves outside private storage root.",
        )
    return target_path


def detect_and_validate_file_type(content: bytes, filename: str) -> str:
    """Validate magic bytes and file extension. Returns verified MIME type.
    Allowed: application/pdf and application/vnd.openxmlformats-officedocument.wordprocessingml.document
    """
    if not content or len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="EMPTY_FILE: Tập tin tải lên rỗng (0 bytes).",
        )

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"FILE_TOO_LARGE: Tập tin vượt quá giới hạn tối đa {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB.",
        )

    lower_name = filename.lower()

    if content.startswith(PDF_MAGIC):
        if not lower_name.endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="UNSUPPORTED_FILE_TYPE: Nội dung PDF nhưng phần mở rộng tập tin không phải .pdf.",
            )
        return "application/pdf"

    if content.startswith(DOCX_MAGIC):
        if not lower_name.endswith(".docx"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="UNSUPPORTED_FILE_TYPE: Nội dung DOCX nhưng phần mở rộng tập tin không phải .docx.",
            )
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="UNSUPPORTED_FILE_TYPE: Hệ thống chỉ hỗ trợ định dạng PDF (%PDF-) hoặc DOCX (PK..) hợp lệ.",
    )


def save_private_blob(blob_key: str, data: bytes) -> int:
    """Atomically write binary data to the private storage location."""
    target_path = resolve_blob_path(blob_key)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = target_path.with_suffix(f".tmp_{uuid.uuid4().hex[:8]}")
    with open(temp_path, "wb") as f:
        bytes_written = f.write(data)
    temp_path.replace(target_path)
    return bytes_written


def read_private_blob(blob_key: str) -> bytes:
    """Read binary data from private storage."""
    target_path = resolve_blob_path(blob_key)
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BLOB_NOT_FOUND: Không tìm thấy tài liệu trong kho lưu trữ riêng tư.",
        )
    with open(target_path, "rb") as f:
        return f.read()


def delete_private_blob(blob_key: str) -> bool:
    """Delete a blob from private storage."""
    try:
        target_path = resolve_blob_path(blob_key)
        if target_path.exists():
            target_path.unlink()
            return True
        return False
    except Exception:
        return False
