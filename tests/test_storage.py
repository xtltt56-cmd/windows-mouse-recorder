import json
import tempfile
import unittest
from pathlib import Path

from mouse_clicker.models import MouseEvent, ScreenGeometry, Template
from mouse_clicker.storage import (
    TemplateNotFoundError,
    TemplateStore,
    TemplateStoreError,
)


def make_template(template_id="t1", name="demo"):
    return Template(
        id=template_id,
        name=name,
        screen=ScreenGeometry(left=0, top=0, width=1920, height=1080),
        events=[MouseEvent(type="move", x=10, y=20, delay_ms=0)],
    )


class TemplateStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = TemplateStore(self.root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_load_round_trip(self):
        template = make_template()

        self.store.save(template)

        self.assertEqual(self.store.load(template.id), template)

    def test_list_templates_is_sorted_by_name(self):
        self.store.save(make_template("b", "Zulu"))
        self.store.save(make_template("a", "alpha"))

        self.assertEqual(
            [item.name for item in self.store.list_templates()],
            ["alpha", "Zulu"],
        )

    def test_rename_returns_and_persists_updated_template(self):
        self.store.save(make_template())

        renamed = self.store.rename("t1", "new name")

        self.assertEqual(renamed.name, "new name")
        self.assertEqual(self.store.load("t1").name, "new name")

    def test_delete_removes_template(self):
        self.store.save(make_template())

        self.store.delete("t1")

        with self.assertRaises(TemplateNotFoundError):
            self.store.load("t1")

    def test_corrupt_json_raises_store_error(self):
        (self.root / "broken.json").write_text("not json", encoding="utf-8")

        with self.assertRaises(TemplateStoreError):
            self.store.load("broken")

    def test_save_does_not_leave_temp_files(self):
        self.store.save(make_template())

        self.assertEqual(list(self.root.glob("*.tmp")), [])
        self.assertEqual(list(self.root.glob("*.json")), [self.root / "t1.json"])


if __name__ == "__main__":
    unittest.main()
