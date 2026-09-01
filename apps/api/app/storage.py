"""Where evidence files live on disk.

Files go under `settings.data_dir`, partitioned by tenant and application:

    data/<tenant_id>/<application_id>/<sha256>.png

The **relative** path is what gets stored in the database, so moving the data
folder between machines does not invalidate every row. The sha256 filename means
the same image uploaded twice occupies one file, and that a file whose bytes
changed on disk no longer matches its own name.

Deliberately not an abstraction over storage backends. There is one backend and
one deployment (docs/DESIGN_POLICY.md §7); if a second is ever needed, two
functions are easy to change.
"""

from pathlib import Path
from uuid import UUID

from app.config import settings


def write(tenant_id: UUID, application_id: UUID, filename: str, data: bytes) -> str:
    """Save bytes and return the path to store in the database."""
    relative = Path(str(tenant_id)) / str(application_id) / filename
    absolute = settings.data_dir / relative

    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_bytes(data)

    # Forward slashes so a path written on Windows still resolves on Linux.
    return relative.as_posix()


def read(storage_path: str) -> bytes:
    return resolve(storage_path).read_bytes()


def resolve(storage_path: str) -> Path:
    """Absolute path for a stored file.

    Rejects anything that escapes the data directory. The paths we write are
    safe by construction, but this function also takes values read back out of
    the database, and a stored `../../` would otherwise serve any file on the
    machine.
    """
    absolute = (settings.data_dir / storage_path).resolve()
    root = settings.data_dir.resolve()

    if not absolute.is_relative_to(root):
        raise ValueError(f"Refusing to read outside the data directory: {storage_path}")

    return absolute
