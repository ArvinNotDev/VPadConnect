"""Application paths and safe migration from pre-AppData installations."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path


APP_NAME = "VPadConnect"

# User-facing preferences belong in Roaming AppData. Machine-local state and
# security material belong in Local AppData. These are the paths used by
# releases before the split; the settings template itself is never migrated
# when it is byte-for-byte identical to the packaged default.
_CONFIG_MIGRATION_PATHS = (
    (Path("config/settings.conf"), Path("settings.conf")),
    (Path("settings.conf"), Path("settings.conf")),
    (Path("hotkeys.json"), Path("hotkeys.json")),
    (Path("profiles/user"), Path("profiles/user")),
    (Path("profiles/GenericGamepads.json"), Path("profiles/GenericGamepads.json")),
)

_LOCAL_MIGRATION_PATHS = (
    Path("trusted_clients.json"),
    Path("remote_permissions.json"),
    Path("remote_device_permissions.json"),
    Path("remote_security"),
    Path("logs"),
)


def _source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resource_root() -> Path:
    """Return the read-only root containing bundled application resources."""
    if getattr(sys, "frozen", False):
        # _MEIPASS is only a resource location. Writable paths never use it.
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return _source_root()


def _known_folder(env_name: str, windows_folder: str, xdg_name: str, unix_folder: str) -> Path:
    configured = os.environ.get(env_name)
    if configured:
        return Path(configured).expanduser()

    home = Path.home()
    if os.name == "nt":
        return home / "AppData" / windows_folder

    xdg_base = os.environ.get(xdg_name)
    return Path(xdg_base).expanduser() if xdg_base else home / unix_folder


def config_root() -> Path:
    """Return ``%APPDATA%\\VPadConnect`` (or a development fallback)."""
    return _known_folder("APPDATA", "Roaming", "XDG_CONFIG_HOME", ".config") / APP_NAME


def local_root() -> Path:
    """Return ``%LOCALAPPDATA%\\VPadConnect`` (or a development fallback)."""
    return _known_folder("LOCALAPPDATA", "Local", "XDG_DATA_HOME", ".local/share") / APP_NAME


def config_path(*parts: str) -> Path:
    """Build a path for roaming preferences and user-created profiles."""
    return config_root().joinpath(*parts)


def local_path(*parts: str) -> Path:
    """Build a path for machine-local runtime data and security state."""
    return local_root().joinpath(*parts)


def data_root() -> Path:
    """Compatibility alias for the Local AppData root."""
    return local_root()


def data_path(*parts: str) -> Path:
    """Compatibility alias for machine-local data paths."""
    return local_path(*parts)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def resolve_data_path(path: str | Path) -> Path:
    """Resolve log/runtime paths locally and keep writes out of app resources."""
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        return local_path(*candidate.parts)

    roots = [resource_root()]
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    for root in roots:
        if _is_within(candidate, root):
            return local_path(*candidate.resolve().relative_to(root.resolve()).parts)
    return candidate


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_file_if_missing(source: Path, destination: Path) -> bool:
    """Atomically copy and verify a file without replacing existing data."""
    if destination.exists() or not source.is_file() or source.is_symlink():
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".migrating", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        if _file_hash(source) != _file_hash(temporary):
            raise OSError(f"Migration verification failed for {source}")

        try:
            # Same-directory hard-link publication is atomic and will not
            # replace a destination created by another application instance.
            os.link(temporary, destination)
        except OSError:
            if os.name != "nt":
                raise
            # On Windows os.rename is atomic and fails when the target exists.
            os.rename(temporary, destination)

        if _file_hash(source) != _file_hash(destination):
            raise OSError(f"Published migration did not verify for {source}")
        return True
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _copy_legacy_item(source: Path, destination: Path) -> None:
    """Copy a legacy file or directory tree while retaining its source."""
    try:
        if source.resolve() == destination.resolve():
            return
    except OSError:
        pass

    if source.is_symlink() or not source.exists():
        return
    if source.is_file():
        _copy_file_if_missing(source, destination)
        return
    if not source.is_dir():
        return

    if destination.exists() and not destination.is_dir():
        return
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        _copy_legacy_item(item, destination / item.name)


def _is_bundled_default_settings(path: Path) -> bool:
    """Identify the shipped settings template so it is not imported as data."""
    if not path.is_file():
        return False
    bundled_default = resource_path("config", "settings.conf")
    try:
        if path.resolve() == bundled_default.resolve():
            return True
        return bundled_default.is_file() and _file_hash(path) == _file_hash(bundled_default)
    except OSError:
        return False


def _legacy_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    # Previous installed versions either wrote beside the executable or had
    # already moved their shared data tree to Local AppData.
    roots.append(local_root())
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    else:
        roots.append(_source_root())

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = os.path.normcase(str(root.resolve()))
        if key not in seen:
            unique.append(root)
            seen.add(key)
    return tuple(unique)


def migrate_legacy_data(legacy_root: Path, *, config_destination: Path | None = None,
                        local_destination: Path | None = None) -> None:
    """Migrate one old data root without deleting or overwriting user files.

    Existing Roaming and Local AppData files always win. A colliding legacy
    profile or security file remains in its old location, where it can still
    be recovered; unrelated files in the same directory are copied normally.
    """
    config_destination = config_destination or config_root()
    local_destination = local_destination or local_root()

    for old_relative, new_relative in _CONFIG_MIGRATION_PATHS:
        source = legacy_root / old_relative
        target = config_destination / new_relative
        if old_relative == Path("config/settings.conf") and _is_bundled_default_settings(source):
            continue
        try:
            _copy_legacy_item(source, target)
        except OSError:
            # Do not let SettingsManager seed defaults over a custom legacy
            # settings file that could not be safely migrated.
            if (
                old_relative in (Path("config/settings.conf"), Path("settings.conf"))
                and source.is_file()
                and not target.exists()
            ):
                raise
            # Retain the source and continue migrating independent user data.
            continue

    for relative_path in _LOCAL_MIGRATION_PATHS:
        try:
            _copy_legacy_item(legacy_root / relative_path, local_destination / relative_path)
        except OSError:
            if relative_path != Path("logs") and (legacy_root / relative_path).exists():
                # In particular, never start with a newly generated TLS key if
                # the existing identity could not be copied into Local AppData.
                raise
            # A locked diagnostic log can remain at its old path without
            # preventing normal application startup.
            continue


def initialize_storage() -> None:
    """Create AppData roots and perform the idempotent first-launch migration."""
    config_root().mkdir(parents=True, exist_ok=True)
    local_root().mkdir(parents=True, exist_ok=True)
    for legacy_root in _legacy_roots():
        migrate_legacy_data(legacy_root)


def resource_path(*parts: str) -> Path:
    """Build a path to a bundled/read-only application resource."""
    return resource_root().joinpath(*parts)


def ensure_user_file(relative_path: str, default_resource: str | None = None) -> Path:
    """Initialize a roaming user file from a bundled default when absent."""
    target = config_path(*Path(relative_path).parts)
    if not target.exists() and default_resource:
        source = resource_path(*Path(default_resource).parts)
        if source.is_file():
            _copy_file_if_missing(source, target)
    return target
