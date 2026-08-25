import unittest


class ProjectSmokeTest(unittest.TestCase):
    def test_package_imports(self):
        import mouse_clicker

        self.assertEqual(mouse_clicker.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
