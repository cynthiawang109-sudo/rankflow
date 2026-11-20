import gzip
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from rankflow.data.fetch import extract_jsonl


class ExtractJsonlTests(unittest.TestCase):
    def test_extracts_kaggle_filenames(self):
        train = b'{"session": 1, "events": []}\n'
        test = b'{"session": 2, "events": []}\n'
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            archive = directory / "dataset.zip"
            with ZipFile(archive, "w") as package:
                package.writestr("otto-recsys-train.jsonl", train)
                package.writestr("otto-recsys-test.jsonl", test)

            self.assertEqual(extract_jsonl(archive, directory), {
                "train.jsonl": hashlib.sha256(train).hexdigest(),
                "test.jsonl": hashlib.sha256(test).hexdigest(),
            })
            self.assertEqual((directory / "train.jsonl").read_bytes(), train)
            self.assertEqual((directory / "test.jsonl").read_bytes(), test)

    def test_rejects_multiple_matches(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            archive = directory / "dataset.zip"
            with ZipFile(archive, "w") as package:
                package.writestr("train.jsonl", b"{}\n")
                package.writestr("nested/otto-recsys-train.jsonl.gz", gzip.compress(b"{}\n"))
                package.writestr("otto-recsys-test.jsonl", b"{}\n")

            with self.assertRaisesRegex(ValueError, r"Expected exactly one train\.jsonl"):
                extract_jsonl(archive, directory)
