"""
Profile Manager for VPadConnect.

Manages user-created settings profiles. Each profile is a snapshot of the
application's device, UI, and developer settings, stored as a JSON file
in the user-writable profiles directory.
"""

from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.utils.paths import config_path


class ProfileManager:
    """
    Manages named settings profiles.

    Each profile is a JSON file stored in ``profiles/user/`` containing a
    snapshot of all settings sections (device, ui, developer) plus metadata
    (name, created timestamp, description, image).
    """

    def __init__(self, settings_manager) -> None:
        """
        Initialize the ProfileManager.

        :param settings_manager: A ``SettingsManager`` instance used to
            read and apply settings.
        """
        self.settings = settings_manager
        self._profiles_dir = config_path("profiles", "user")
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        self._images_dir = self._profiles_dir / "_images"
        self._images_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_profiles(self) -> List[Dict[str, Any]]:
        """
        Return a list of all saved profiles with their metadata.

        Each entry contains:
            - ``name``: Profile display name
            - ``filename``: JSON filename on disk
            - ``description``: User-provided description (may be empty)
            - ``image``: Path to profile image, or empty string
            - ``created``: ISO-8601 creation timestamp
            - ``modified``: ISO-8601 last-modified timestamp
        """
        profiles: List[Dict[str, Any]] = []
        if not self._profiles_dir.exists():
            return profiles

        for f in sorted(self._profiles_dir.iterdir()):
            if f.suffix == ".json" and not f.name.startswith("_"):
                meta = self._read_profile_meta(f)
                if meta is not None:
                    profiles.append(meta)

        return profiles

    def get_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Load a profile by name and return its full data dictionary.

        Returns ``None`` if the profile does not exist.
        """
        path = self._profile_path(name)
        if path is None or not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, OSError):
            return None

    def save_profile(
        self,
        name: str,
        description: str = "",
        *,
        overwrite: bool = False,
    ) -> bool:
        """
        Save the current application settings as a named profile.

        :param name: Display name for the profile.
        :param description: Optional description.
        :param overwrite: If ``True``, an existing profile with the same
            name is replaced.  If ``False`` and the name already exists,
            ``False`` is returned.
        :return: ``True`` on success, ``False`` on failure.
        """
        name = name.strip()
        if not name:
            return False

        path = self._profile_path(name)
        if path is None:
            return False

        if path.exists() and not overwrite:
            return False

        snapshot = self._snapshot_settings()

        # Preserve existing image and timestamps when overwriting
        existing_meta = self._read_profile_meta(path) if path.exists() else None
        snapshot["_meta"] = {
            "name": name,
            "description": description,
            "image": existing_meta.get("image", "") if existing_meta else "",
            "created": (
                existing_meta.get("created", self._now_iso())
                if existing_meta
                else self._now_iso()
            ),
            "modified": self._now_iso(),
        }

        try:
            self._profiles_dir.mkdir(parents=True, exist_ok=True)
            self._write_json(path, snapshot)
            return True
        except OSError:
            return False

    def update_profile_description(self, name: str, description: str) -> bool:
        """
        Update only the description of an existing profile.

        :return: ``True`` on success.
        """
        data = self.get_profile(name)
        if data is None:
            return False

        if "_meta" not in data:
            data["_meta"] = {"name": name}
        data["_meta"]["description"] = description
        data["_meta"]["modified"] = self._now_iso()

        path = self._profile_path(name)
        if path is None:
            return False

        try:
            self._write_json(path, data)
            return True
        except OSError:
            return False

    def set_profile_image(self, name: str, image_path: str) -> bool:
        """
        Set or replace the image for a profile.

        The image is copied into the profiles/_images/ directory and
        the path is stored in the profile metadata.

        :param name: Profile name.
        :param image_path: Absolute path to the source image file.
        :return: ``True`` on success.
        """
        data = self.get_profile(name)
        if data is None:
            return False

        src = Path(image_path)
        if not src.is_file():
            return False

        # Build a stable destination filename from the profile name
        safe_name = self._safe_stem(name)
        ext = src.suffix.lower()
        if ext not in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
            ext = ".png"
        dest = self._images_dir / f"{safe_name}{ext}"

        # Remove old image if it exists
        old_image = data.get("_meta", {}).get("image", "")
        old_path = self._stored_image_path(old_image)
        if old_path and old_path.is_file() and old_path != dest:
                try:
                    old_path.unlink()
                except OSError:
                    pass

        try:
            shutil.copy2(src, dest)
        except OSError:
            return False

        if "_meta" not in data:
            data["_meta"] = {"name": name}
        data["_meta"]["image"] = dest.name
        data["_meta"]["modified"] = self._now_iso()

        path = self._profile_path(name)
        if path is None:
            return False

        try:
            self._write_json(path, data)
            return True
        except OSError:
            return False

    def remove_profile_image(self, name: str) -> bool:
        """
        Remove the image from a profile.

        :return: ``True`` on success.
        """
        data = self.get_profile(name)
        if data is None:
            return False

        old_image = data.get("_meta", {}).get("image", "")
        old_path = self._stored_image_path(old_image)
        if old_path and old_path.is_file():
            try:
                old_path.unlink()
            except OSError:
                pass

        if "_meta" not in data:
            data["_meta"] = {"name": name}
        data["_meta"]["image"] = ""
        data["_meta"]["modified"] = self._now_iso()

        path = self._profile_path(name)
        if path is None:
            return False

        try:
            self._write_json(path, data)
            return True
        except OSError:
            return False

    def get_profile_image_path(self, name: str) -> Optional[str]:
        """
        Return the filesystem path to a profile's image, or ``None``.
        """
        data = self.get_profile(name)
        if data is None:
            return None
        img = data.get("_meta", {}).get("image", "")
        image_path = self._stored_image_path(img)
        if image_path and image_path.is_file():
            return str(image_path)
        return None

    def delete_profile(self, name: str) -> bool:
        """
        Delete a profile by name.

        Also removes any associated image file.

        :return: ``True`` if the file was removed, ``False`` otherwise.
        """
        # Clean up image first
        data = self.get_profile(name)
        if data:
            img = data.get("_meta", {}).get("image", "")
            image_path = self._stored_image_path(img)
            if image_path:
                try:
                    image_path.unlink(missing_ok=True)
                except OSError:
                    pass

        path = self._profile_path(name)
        if path is None or not path.exists():
            return False
        try:
            path.unlink()
            return True
        except OSError:
            return False

    def export_profile(self, name: str, destination: str) -> bool:
        """Export a profile and its optional avatar as a portable .ibprofile."""
        data = self.get_profile(name)
        if data is None:
            return False

        destination_path = Path(destination)
        if destination_path.suffix.lower() != ".ibprofile":
            destination_path = destination_path.with_suffix(".ibprofile")

        image_name = data.get("_meta", {}).get("image", "")
        image_path = self._stored_image_path(image_name)
        try:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(
                destination_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr(
                    "profile.json",
                    json.dumps(data, indent=2, ensure_ascii=False),
                )
                if image_path and image_path.is_file():
                    archive.write(image_path, f"image{image_path.suffix.lower()}")
            return True
        except (OSError, zipfile.BadZipFile):
            return False

    def import_profile(
        self, source: str, *, overwrite: bool = False, name: str | None = None
    ) -> Optional[str]:
        """Import a .ibprofile archive (or legacy JSON) and return its name."""
        source_path = Path(source)
        try:
            if source_path.suffix.lower() == ".json":
                data = json.loads(source_path.read_text(encoding="utf-8"))
                image_member = None
            else:
                with zipfile.ZipFile(source_path, "r") as archive:
                    data = json.loads(archive.read("profile.json").decode("utf-8"))
                    image_member = next(
                        (
                            item
                            for item in archive.namelist()
                            if item.startswith("image.")
                        ),
                        None,
                    )
                    image_bytes = (
                        archive.read(image_member) if image_member else None
                    )
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            return None

        if not isinstance(data, dict):
            return None
        meta = data.get("_meta")
        if not isinstance(meta, dict):
            meta = {}
            data["_meta"] = meta

        imported_name = (name or meta.get("name") or source_path.stem).strip()
        if not imported_name:
            return None
        destination = self._profile_path(imported_name)
        if destination is None or (destination.exists() and not overwrite):
            return None

        old_meta = self._read_profile_meta(destination) if destination.exists() else None
        meta.update(
            {
                "name": imported_name,
                "created": (
                    old_meta.get("created", self._now_iso())
                    if old_meta
                    else meta.get("created", self._now_iso())
                ),
                "modified": self._now_iso(),
                "image": "",
            }
        )

        try:
            old_image = (
                old_meta.get("image", "") if old_meta else ""
            )
            old_image_path = self._stored_image_path(old_image)
            if old_image_path and old_image_path.is_file():
                old_image_path.unlink()
            self._write_json(destination, data)
            if image_member and image_bytes:
                suffix = Path(image_member).suffix.lower()
                if suffix not in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
                    suffix = ".png"
                image_destination = self._images_dir / f"{self._safe_stem(imported_name)}{suffix}"
                image_destination.write_bytes(image_bytes)
                meta["image"] = image_destination.name
                self._write_json(destination, data)
            return imported_name
        except OSError:
            return None

    def get_import_profile_name(self, source: str) -> Optional[str]:
        """Read the display name from an import file without writing it."""
        source_path = Path(source)
        try:
            if source_path.suffix.lower() == ".json":
                data = json.loads(source_path.read_text(encoding="utf-8"))
            else:
                with zipfile.ZipFile(source_path, "r") as archive:
                    data = json.loads(archive.read("profile.json").decode("utf-8"))
            name = data.get("_meta", {}).get("name") if isinstance(data, dict) else None
            return str(name or source_path.stem).strip() or None
        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            return None

    def activate_profile(self, name: str) -> bool:
        """
        Load a profile's settings into the SettingsManager and persist them.

        :return: ``True`` on success.
        """
        data = self.get_profile(name)
        if data is None:
            return False

        self._apply_settings(data)

        # Record the active profile name
        if not self.settings.config.has_section("profile"):
            self.settings.config.add_section("profile")
        self.settings.config.set("profile", "active", name)
        self.settings.save()
        return True

    def save_controller_layout(
        self,
        controller_id: str,
        layout: dict,
        profile_name: str | None = None,
    ) -> bool:
        """Update only one controller's layout inside a saved user profile."""
        name = (profile_name or self.get_active_profile_name()).strip()
        if not name:
            return False

        path = self._profile_path(name)
        data = self.get_profile(name)
        section_builder = getattr(self.settings, "_controller_layout_section", None)
        if path is None or data is None or section_builder is None:
            return False

        try:
            payload = json.dumps(
                layout, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            )
        except (TypeError, ValueError):
            return False
        if len(payload) > 65536:
            return False

        section = section_builder(controller_id)
        data[section] = {"layout": payload}
        metadata = data.get("_meta")
        if isinstance(metadata, dict):
            metadata["modified"] = self._now_iso()

        try:
            self._write_json(path, data)
        except OSError:
            return False
        return True

    def get_active_profile_name(self) -> str:
        """Return the name of the currently active profile, or ``""``."""
        try:
            return self.settings.config.get("profile", "active", fallback="")
        except Exception:
            return ""

    def create_default_profile(self) -> None:
        """
        Create a ``Default`` profile from the current settings if no
        profiles exist yet.  This is called on first launch.
        """
        if self.list_profiles():
            return
        self.save_profile("Default", description="Factory default settings", overwrite=True)
        self.activate_profile("Default")

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """
        Rename an existing profile.

        :return: ``True`` on success.
        """
        new_name = new_name.strip()
        if not new_name or not old_name:
            return False

        old_path = self._profile_path(old_name)
        new_path = self._profile_path(new_name)

        if old_path is None or new_path is None:
            return False
        if not old_path.exists() or new_path.exists():
            return False

        try:
            data = json.loads(old_path.read_text(encoding="utf-8"))
            if "_meta" in data:
                data["_meta"]["name"] = new_name
                data["_meta"]["modified"] = self._now_iso()
                # Rename image file if present
                old_img = data["_meta"].get("image", "")
                old_img_path = self._stored_image_path(old_img)
                if old_img_path and old_img_path.is_file():
                    ext = old_img_path.suffix
                    safe_new = self._safe_stem(new_name)
                    new_img = self._images_dir / f"{safe_new}{ext}"
                    try:
                        shutil.move(str(old_img_path), str(new_img))
                        data["_meta"]["image"] = new_img.name
                    except OSError:
                        pass
            self._write_json(new_path, data)
            old_path.unlink()

            # Update active profile reference if needed
            if self.get_active_profile_name() == old_name:
                if not self.settings.config.has_section("profile"):
                    self.settings.config.add_section("profile")
                self.settings.config.set("profile", "active", new_name)
                self.settings.save()

            return True
        except (OSError, json.JSONDecodeError):
            return False

    def duplicate_profile(
        self, source_name: str, new_name: str
    ) -> bool:
        """
        Create a copy of an existing profile under a new name.

        :return: ``True`` on success.
        """
        new_name = new_name.strip()
        if not new_name or not source_name:
            return False

        source_data = self.get_profile(source_name)
        if source_data is None:
            return False

        new_path = self._profile_path(new_name)
        if new_path is None or new_path.exists():
            return False

        source_data["_meta"] = {
            "name": new_name,
            "description": source_data.get("_meta", {}).get("description", ""),
            "image": "",  # Don't share images between profiles
            "created": self._now_iso(),
            "modified": self._now_iso(),
        }

        try:
            self._write_json(new_path, source_data)
            return True
        except OSError:
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _profile_path(self, name: str) -> Optional[Path]:
        """Build the filesystem path for a profile name."""
        safe = self._safe_stem(name)
        if not safe:
            return None
        return self._profiles_dir / f"{safe}.json"

    def _snapshot_settings(self) -> Dict[str, Any]:
        """Read every setting from the SettingsManager into a dict."""
        snap: Dict[str, Any] = {}
        cfg = self.settings.config

        for section in cfg.sections():
            if section == "profile":
                continue
            snap[section] = dict(cfg[section])

        return snap

    def _apply_settings(self, data: Dict[str, Any]) -> None:
        """
        Write a profile's data back into the SettingsManager's config.
        """
        cfg = self.settings.config

        # Controller layouts are profile-scoped. Remove layouts absent from
        # the selected profile so one game's mapping cannot leak into another.
        saved_layout_sections = {
            section
            for section in data
            if section.startswith("controller_layout_")
        }
        for section in cfg.sections():
            if (
                section.startswith("controller_layout_")
                and section not in saved_layout_sections
            ):
                cfg.remove_section(section)

        for section, values in data.items():
            if section.startswith("_") or section == "profile":
                continue
            if not isinstance(values, dict):
                continue
            if not cfg.has_section(section):
                cfg.add_section(section)
            for key, value in values.items():
                if section == "device" and key == "polling_rate":
                    if "poll_interval_ms" in values:
                        continue
                    key = "poll_interval_ms"
                cfg.set(section, key, str(value))
        self.settings.save()

    @staticmethod
    def _now_iso() -> str:
        """Return an ISO-8601 timestamp string."""
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

    @staticmethod
    def _safe_stem(name: str) -> str:
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name)
        return safe.strip().replace(" ", "_") or "profile"

    def _stored_image_path(self, value: Any) -> Optional[Path]:
        """Resolve image metadata while keeping cleanup inside the image dir."""
        if not value:
            return None
        candidate = Path(str(value))
        if not candidate.is_absolute():
            candidate = self._images_dir / candidate.name
        try:
            candidate = candidate.resolve()
            candidate.relative_to(self._images_dir.resolve())
        except (OSError, ValueError):
            return None
        return candidate

    @staticmethod
    def _write_json(path: Path, data: Dict[str, Any]) -> None:
        """Write JSON atomically to avoid leaving a truncated profile."""
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _read_profile_meta(
        self, path: Path, key: Optional[str] = None
    ) -> Optional[Any]:
        """Read _meta from a profile file. Returns the meta dict or a single key."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            meta = data.get("_meta")
            if not isinstance(meta, dict):
                # Build minimal meta from filename
                meta = {
                    "name": path.stem.replace("_", " ").title(),
                    "filename": path.name,
                    "description": "",
                    "image": "",
                    "created": "",
                    "modified": "",
                }
            if key:
                return meta.get(key)
            meta["filename"] = path.name
            return meta
        except (json.JSONDecodeError, OSError):
            return None
