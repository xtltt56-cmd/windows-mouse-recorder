import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import List

from .models import Template


class TemplateStoreError(Exception):
    """Base error for template persistence failures."""


class TemplateNotFoundError(TemplateStoreError):
    """Raised when a requested template file does not exist."""


class TemplateStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def list_templates(self) -> List[Template]:
        templates = []
        for path in self.root.glob("*.json"):
            templates.append(self.load(path.stem))
        return sorted(templates, key=lambda item: item.name.casefold())

    def load(self, template_id: str) -> Template:
        path = self._path_for(template_id)
        if not path.exists():
            raise TemplateNotFoundError("template not found: {}".format(template_id))
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return Template.from_dict(data)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise TemplateStoreError(
                "could not load template {}: {}".format(template_id, exc)
            ) from exc

    def save(self, template: Template) -> None:
        path = self._path_for(template.id)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.root),
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(template.to_dict(), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(str(temporary_path), str(path))
            temporary_path = None
        except (OSError, TypeError, ValueError) as exc:
            raise TemplateStoreError(
                "could not save template {}: {}".format(template.id, exc)
            ) from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    def rename(self, template_id: str, name: str) -> Template:
        template = self.load(template_id)
        renamed = replace(template, name=name)
        self.save(renamed)
        return renamed

    def delete(self, template_id: str) -> None:
        path = self._path_for(template_id)
        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise TemplateNotFoundError(
                "template not found: {}".format(template_id)
            ) from exc
        except OSError as exc:
            raise TemplateStoreError(
                "could not delete template {}: {}".format(template_id, exc)
            ) from exc

    def _path_for(self, template_id: str) -> Path:
        if not template_id or Path(template_id).name != template_id:
            raise TemplateStoreError("invalid template id")
        return self.root / (template_id + ".json")
