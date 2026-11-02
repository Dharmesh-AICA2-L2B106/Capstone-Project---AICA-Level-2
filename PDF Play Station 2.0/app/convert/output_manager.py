"""Output paths, filename conflicts, safe saving and output validation.

Files are first written to a temporary file in the destination folder and
moved into place only after they have been generated and re-opened
successfully, so a failed conversion never leaves a half-written file or
damages an existing one.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Callable, Optional

from .settings import ConversionSettings
from .validators import safe_filename

log = logging.getLogger(__name__)

# Decision returned by a conflict resolver: ("overwrite" | "increment" | "skip", apply_to_all)
ConflictResolver = Callable[[Path], tuple[str, bool]]


class OutputError(Exception):
    """Output problem with a user-readable message."""


def planned_path(source: Path, settings: ConversionSettings, extension: str) -> Path:
    stem = safe_filename(source.stem, "Document")
    if settings.naming == "suffix":
        stem = safe_filename(stem + settings.output_suffix)
    folder = settings.output_folder
    if settings.subfolder_per_pdf:
        folder = folder / stem
    return folder / f"{stem}{extension}"


def incremented_path(path: Path, reserved: frozenset[Path] | set[Path] = frozenset()) -> Path:
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists() and candidate not in reserved:
            return candidate
        n += 1


class ConflictHandler:
    """Applies the existing-file policy, remembering "apply to all" answers."""

    def __init__(self, policy: str, resolver: Optional[ConflictResolver] = None):
        self.policy = policy
        self.resolver = resolver
        self._remembered: Optional[str] = None

    def resolve(self, path: Path, reserved: set[Path]) -> Optional[Path]:
        """Return the path to write to, or None to skip.

        ``reserved`` holds outputs already produced in this batch; those are
        never overwritten (two PDFs with the same name get "name (2)")."""
        if path in reserved:
            return incremented_path(path, reserved)
        if not path.exists():
            return path
        decision = self._remembered or self.policy
        if decision == "ask":
            if self.resolver is None:
                decision = "increment"
            else:
                decision, apply_all = self.resolver(path)
                if apply_all:
                    self._remembered = decision
        if decision == "skip":
            return None
        if decision == "overwrite":
            return path
        return incremented_path(path, reserved)


def ensure_folder(folder: Path) -> None:
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputError(f"Could not create the folder {folder} ({exc.strerror or exc}).") from exc


def temp_path_for(target: Path) -> Path:
    return target.with_name(f"~pcp_{uuid.uuid4().hex[:8]}{target.suffix}")


def validate_output(path: Path) -> None:
    """Confirm the generated file exists, is non-empty and can be opened again."""
    if not path.exists() or path.stat().st_size == 0:
        raise OutputError("The output file was not created or is empty.")
    suffix = path.suffix.lower()
    try:
        if suffix == ".xlsx":
            from openpyxl import load_workbook
            wb = load_workbook(str(path), read_only=True)
            if not wb.sheetnames:
                raise OutputError("The workbook has no worksheets.")
            wb.close()
        elif suffix == ".docx":
            from docx import Document
            Document(str(path))
    except OutputError:
        raise
    except Exception as exc:
        raise OutputError(f"The generated file could not be re-opened for validation ({type(exc).__name__}).") from exc


def save_atomically(target: Path, write: Callable[[Path], list[str]]) -> list[str]:
    """Call ``write(temp_path)``, validate the result, then move it to ``target``."""
    ensure_folder(target.parent)
    tmp = temp_path_for(target)
    try:
        warnings = write(tmp)
        validate_output(tmp)
        try:
            os.replace(tmp, target)
        except PermissionError as exc:
            raise OutputError(f"{target.name} could not be saved because it is open in another program "
                              "(close it in Excel/Word and try again) or the folder is read-only.") from exc
        return warnings
    except PermissionError as exc:
        raise OutputError(f"Permission denied while writing {target.name}. Check that the output folder "
                          "is writable.") from exc
    except OSError as exc:
        if getattr(exc, "errno", None) == 28 or getattr(exc, "winerror", None) == 112:
            raise OutputError("There is not enough free disk space to save the output.") from exc
        raise OutputError(f"Could not save {target.name} ({exc.strerror or exc}).") from exc
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                log.warning("Could not remove temporary file %s", tmp)
