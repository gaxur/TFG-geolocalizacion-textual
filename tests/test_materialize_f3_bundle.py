import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import tempfile
import unittest
from unittest.mock import patch

from scripts.materialize_f3_bundle import (
    ENTRYPOINT_PATH,
    F3ReportError,
    ROOT,
    _git_state,
    _link_fd_noreplace,
    _prepare_report_destination,
    _publish_report,
    _sha256,
    build_parser,
    materialize,
)
from src.tfg_phase0.catalog import build_catalog, write_manifest
from src.tfg_phase0.config import load_region_config
from src.tfg_phase0.f3_bundle import F3BundleConflictError
from src.tfg_phase0.f3_contracts import F3_BUNDLE_FILES
from src.tfg_phase0.f3_inputs import F3InputError
from src.tfg_phase0.osm_snapshot import (
    build_overpass_query,
    build_snapshot_provenance,
    publish_snapshot,
    validate_osm_xml,
)


class MaterializeF3BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "data")
        self.root = Path(self.temporary.name)
        self.config_path = ROOT / "config/madrid.yaml"
        self.rules_path = ROOT / "third_party/osm-polygon-features/v0.9.2/polygon-features.json"
        config = load_region_config(self.config_path)
        self.manifest = self.root / "manifest.json"
        write_manifest(build_catalog(config, spacing_m=50), self.manifest)
        raw = (ROOT / "tests/fixtures/f3/inputs/source.osm").read_bytes()
        counts = validate_osm_xml(raw, len(raw), config["region"]["bbox"])
        provenance = build_snapshot_provenance(
            config=config,
            query=build_overpass_query(config["region"]["bbox"], 60),
            raw=raw,
            counts=counts,
            acquired_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
            attempts=1,
            http_status=200,
            content_type="application/xml",
        )
        part = self.root / "source.part"
        part.write_bytes(raw)
        self.snapshot, _ = publish_snapshot(
            raw_part=part, snapshots_root=self.root / "snapshots", provenance=provenance
        )
        self.output = self.root / "processed"
        self.report_root = self.root / "reports"
        self.report_root_patcher = patch(
            "scripts.materialize_f3_bundle.REPORT_ROOT", self.report_root
        )
        self.report_root_patcher.start()
        self.report_root.mkdir(parents=True)
        self.report = self.report_root / "publish.json"

    def tearDown(self):
        self.report_root_patcher.stop()
        self.temporary.cleanup()

    def args(self, **changes):
        values = {
            "manifest": self.manifest,
            "snapshot_dir": self.snapshot,
            "config": self.config_path,
            "rules": self.rules_path,
            "processed_osm_root": self.output,
            "report_json": self.report,
        }
        values.update(changes)
        return argparse.Namespace(**values)

    def test_required_arguments_and_defaults(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])
        args = parser.parse_args(["--manifest", "m.json", "--snapshot-dir", "snapshot"])
        self.assertEqual(args.config, ROOT / "config/madrid.yaml")
        self.assertEqual(args.processed_osm_root, ROOT / "data/processed/osm")

    def test_full_pipeline_report_and_cache_hit_without_network_or_input_changes(self):
        inputs = (
            self.manifest,
            self.snapshot / "source.osm",
            self.snapshot / "provenance.json",
            self.snapshot / "sha256.txt",
            self.config_path,
            self.rules_path,
        )
        before = {path: (path.read_bytes(), path.stat()) for path in inputs}
        with patch.object(socket, "socket", side_effect=AssertionError("sin red")):
            first = materialize(self.args())
            destination = Path(first["bundle_path"])
            bundle_before = {
                path.name: (path.read_bytes(), path.stat().st_size, path.stat().st_mtime_ns)
                for path in destination.iterdir()
            }
            second_report = self.report_root / "cache-hit.json"
            second = materialize(self.args(report_json=second_report))
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(first["f3_dataset_id"], second["f3_dataset_id"])
        self.assertEqual({path.name for path in destination.iterdir()}, set(F3_BUNDLE_FILES))
        self.assertFalse(self.report.resolve().is_relative_to(destination.resolve()))
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual(report["validation_status"], "PASS")
        self.assertEqual(report["manifest"]["candidate_count"], 253)
        self.assertEqual(set(report["file_sha256"]), set(F3_BUNDLE_FILES))
        self.assertEqual(report["entrypoint"]["logical_path"], "scripts/materialize_f3_bundle.py")
        self.assertEqual(report["entrypoint"]["sha256"], _sha256(ENTRYPOINT_PATH))
        self.assertEqual(report["traceability_captured_at"], "start")
        self.assertIsInstance(report["git_dirty"], bool)
        self.assertEqual(
            bundle_before,
            {
                path.name: (path.read_bytes(), path.stat().st_size, path.stat().st_mtime_ns)
                for path in destination.iterdir()
            },
        )
        self.assertEqual(
            {path: (path.read_bytes(), path.stat()) for path in inputs}, before
        )
        self.assertFalse(any(path.name.startswith(".") for path in self.report_root.iterdir()))

    def test_missing_manifest_and_snapshot_are_errors(self):
        with self.assertRaises(F3InputError):
            materialize(self.args(manifest=self.root / "missing.json"))
        with self.assertRaises(F3InputError):
            materialize(self.args(snapshot_dir=self.root / "missing-snapshot"))

    def test_corrupt_snapshot_is_rejected(self):
        corrupt = self.root / "corrupt-snapshot"
        shutil.copytree(self.snapshot, corrupt)
        (corrupt / "source.osm").write_bytes(b"<osm version='0.6'>")
        with self.assertRaises(F3InputError):
            materialize(self.args(snapshot_dir=corrupt))

    def test_preexisting_lock_and_corrupt_destination_are_conflicts(self):
        first = materialize(self.args(report_json=None))
        destination = Path(first["bundle_path"])
        (destination / "sha256.txt").write_text("corrupt\n", encoding="ascii")
        with self.assertRaises(F3BundleConflictError):
            materialize(self.args(report_json=None))

        destination.rename(self.root / "corrupt-bundle")
        lock = destination.parent / f".{destination.name}.lock"
        lock.mkdir()
        with self.assertRaises(F3BundleConflictError):
            materialize(self.args(report_json=None))
        self.assertTrue(lock.is_dir())

    def assert_report_rejected_without_publication(self, path, error=(ValueError, OSError)):
        with self.assertRaises(error):
            materialize(self.args(report_json=path))
        self.assertFalse(self.output.exists())

    def test_report_rejects_inputs_outputs_aliases_and_equivalent_paths(self):
        second_manifest = self.root / "manifest-25m.json"
        second_manifest.write_bytes(self.manifest.read_bytes())
        protected = (
            (self.manifest, {}),
            (second_manifest, {"manifest": second_manifest}),
            (self.snapshot / "source.osm", {}),
            (self.snapshot / "provenance.json", {}),
            (self.snapshot / "sha256.txt", {}),
            (self.config_path, {}),
            (self.rules_path, {}),
            (self.snapshot / "nested-report.json", {}),
            (self.output / "report.json", {}),
            (self.report_root / "nested" / "report.json", {}),
            (self.report_root / ".." / "outside.json", {}),
        )
        input_paths = (
            self.manifest,
            second_manifest,
            self.snapshot / "source.osm",
            self.snapshot / "provenance.json",
            self.snapshot / "sha256.txt",
            self.config_path,
            self.rules_path,
        )
        before = {path: path.read_bytes() for path in input_paths}
        for path, changes in protected:
            with self.subTest(path=path):
                with self.assertRaises((ValueError, OSError)):
                    materialize(self.args(report_json=path, **changes))
                self.assertFalse(self.output.exists())

        alias = self.report_root / "input-alias.json"
        self.report_root.mkdir(parents=True, exist_ok=True)
        alias.symlink_to(self.manifest)
        self.assert_report_rejected_without_publication(alias)
        self.assertEqual(before, {path: path.read_bytes() for path in input_paths})

    def test_report_rejects_existing_directory_file_ancestor_and_permissions(self):
        self.report_root.mkdir(parents=True, exist_ok=True)
        existing = self.report_root / "existing.json"
        existing.write_text("keep", encoding="utf-8")
        self.assert_report_rejected_without_publication(existing, FileExistsError)
        self.assertEqual(existing.read_text(encoding="utf-8"), "keep")

        directory = self.report_root / "directory.json"
        directory.mkdir()
        self.assert_report_rejected_without_publication(directory, FileExistsError)

        with patch("scripts.materialize_f3_bundle.os.access", return_value=False):
            self.assert_report_rejected_without_publication(
                self.report_root / "denied.json", PermissionError
            )

    def test_report_failure_after_publication_is_explicit(self):
        with patch(
            "scripts.materialize_f3_bundle._publish_report",
            side_effect=OSError("report write failed"),
        ):
            with self.assertRaises(F3ReportError) as captured:
                materialize(self.args())
        self.assertTrue(captured.exception.bundle_path.is_dir())
        self.assertFalse(captured.exception.cache_hit)
        self.assertEqual(captured.exception.report_path, self.report)
        self.assertFalse(captured.exception.report_published)
        self.assertFalse(captured.exception.durability_unknown)
        self.assertIn("bundle publicado y validado", str(captured.exception))
        self.assertFalse(self.report.exists())

    def test_report_publication_is_no_replace_and_cleans_own_temporary(self):
        report = {"status": "PASS"}
        destination = _prepare_report_destination(self.args())
        try:
            _publish_report(destination, report)
            before = self.report.read_bytes()
        finally:
            destination.close()

        with self.assertRaises(FileExistsError):
            _prepare_report_destination(self.args())
        self.assertEqual(self.report.read_bytes(), before)
        self.assertFalse(any(path.name.startswith(".") for path in self.report_root.iterdir()))

        failed = self.report_root / "failed.json"
        destination = _prepare_report_destination(self.args(report_json=failed))
        with patch("scripts.materialize_f3_bundle._link_fd_noreplace", side_effect=OSError("link failed")):
            try:
                with self.assertRaisesRegex(Exception, "link failed") as captured:
                    _publish_report(destination, report)
                self.assertFalse(captured.exception.report_published)
            finally:
                destination.close()
        self.assertFalse(failed.exists())
        self.assertFalse(any(path.name.startswith(".") for path in self.report_root.iterdir()))

    def test_report_root_and_existing_ancestor_symlinks_are_rejected(self):
        target = self.root / "target"
        target.mkdir()
        self.report_root.rmdir()
        self.report_root.symlink_to(target, target_is_directory=True)
        self.assert_report_rejected_without_publication(self.report, OSError)

        self.report_root.unlink()
        real_parent = self.root / "real-parent"
        real_parent.mkdir()
        symlink_parent = self.root / "symlink-parent"
        symlink_parent.symlink_to(real_parent, target_is_directory=True)
        with patch(
            "scripts.materialize_f3_bundle.REPORT_ROOT", symlink_parent / "f3"
        ):
            self.assert_report_rejected_without_publication(
                symlink_parent / "f3" / "report.json", OSError
            )

    def test_directory_substitution_does_not_redirect_publication(self):
        destination = _prepare_report_destination(self.args())
        moved = self.root / "moved-reports"
        escape = self.root / "escape"
        escape.mkdir()
        self.report_root.rename(moved)
        self.report_root.symlink_to(escape, target_is_directory=True)
        try:
            _publish_report(destination, {"status": "PASS"})
        finally:
            destination.close()
        self.assertTrue((moved / self.report.name).is_file())
        self.assertFalse((escape / self.report.name).exists())

    def test_report_uses_anonymous_temporary_without_name_race(self):
        destination = _prepare_report_destination(self.args())
        try:
            _publish_report(destination, {"status": "PASS"})
            self.assertEqual(json.loads(self.report.read_text()), {"status": "PASS"})
            self.assertEqual(tuple(path.name for path in self.report_root.iterdir()), (self.report.name,))
        finally:
            destination.close()

    def test_fsync_failure_after_link_reports_visible_unknown_durability(self):
        destination = _prepare_report_destination(self.args())
        try:
            with patch(
                "scripts.materialize_f3_bundle._fsync_report_directory",
                side_effect=OSError("fsync failed"),
            ):
                with self.assertRaisesRegex(Exception, "durabilidad no confirmada") as captured:
                    _publish_report(destination, {"status": "PASS"})
            self.assertTrue(captured.exception.report_published)
            self.assertTrue(captured.exception.durability_unknown)
            self.assertTrue(self.report.is_file())
        finally:
            destination.close()

    def test_materialize_exposes_visible_report_with_unknown_durability(self):
        with patch(
            "scripts.materialize_f3_bundle._fsync_report_directory",
            side_effect=OSError("fsync failed"),
        ):
            with self.assertRaises(F3ReportError) as captured:
                materialize(self.args())
        self.assertTrue(captured.exception.bundle_path.is_dir())
        self.assertEqual(captured.exception.report_path, self.report)
        self.assertTrue(captured.exception.report_published)
        self.assertTrue(captured.exception.durability_unknown)
        self.assertTrue(self.report.is_file())
        self.assertIn("durabilidad no confirmada", str(captured.exception))

    def test_primary_report_error_survives_cleanup_failure(self):
        destination = _prepare_report_destination(self.args())
        try:
            with patch("scripts.materialize_f3_bundle._link_fd_noreplace", side_effect=OSError("primary")), patch(
                "scripts.materialize_f3_bundle._close_report_fd", side_effect=OSError("cleanup failed")
            ):
                with self.assertRaisesRegex(Exception, "primary") as captured:
                    _publish_report(destination, {"status": "PASS"})
            self.assertIn("cleanup", " ".join(captured.exception.__cause__.__notes__))
        finally:
            destination.close()

    def test_cleanup_only_failure_reports_visible_report(self):
        destination = _prepare_report_destination(self.args())
        try:
            calls = 0
            original_close = os.close

            def fail_once(descriptor):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("cleanup failed")
                return original_close(descriptor)

            with patch("scripts.materialize_f3_bundle._close_report_fd", side_effect=fail_once):
                with self.assertRaisesRegex(Exception, "cleanup failed") as captured:
                    _publish_report(destination, {"status": "PASS"})
            self.assertTrue(captured.exception.report_published)
            self.assertFalse(captured.exception.durability_unknown)
            self.assertTrue(self.report.is_file())
        finally:
            destination.close()

    def test_directory_close_failure_preserves_primary_or_reports_published_state(self):
        with patch(
            "scripts.materialize_f3_bundle._publish_report",
            side_effect=OSError("primary"),
        ), patch.object(
            __import__("scripts.materialize_f3_bundle", fromlist=["ReportDestination"]).ReportDestination,
            "close",
            side_effect=OSError("close failed"),
        ):
            with self.assertRaisesRegex(F3ReportError, "primary") as captured:
                materialize(self.args())
        self.assertIn("close failed", " ".join(captured.exception.__notes__))

        original_close = __import__(
            "scripts.materialize_f3_bundle", fromlist=["ReportDestination"]
        ).ReportDestination.close
        calls = 0

        def close_after_real(destination):
            nonlocal calls
            calls += 1
            original_close(destination)
            raise OSError("close failed")

        second_report = self.report_root / "close-failure.json"
        with patch.object(
            __import__("scripts.materialize_f3_bundle", fromlist=["ReportDestination"]).ReportDestination,
            "close",
            new=close_after_real,
        ):
            with self.assertRaises(F3ReportError) as captured:
                materialize(self.args(report_json=second_report))
        self.assertEqual(calls, 1)
        self.assertTrue(captured.exception.report_published)
        self.assertFalse(captured.exception.durability_unknown)
        self.assertTrue(second_report.is_file())

    def test_traceability_is_captured_before_pipeline(self):
        states = iter(({"commit": "start", "dirty": False}, {"commit": "end", "dirty": True}))
        hashes = iter(("start-hash", "end-hash"))
        with patch("scripts.materialize_f3_bundle._git_state", side_effect=lambda: next(states)), patch(
            "scripts.materialize_f3_bundle._sha256",
            side_effect=lambda path: next(hashes) if path == ENTRYPOINT_PATH else "file-hash",
        ):
            report = materialize(self.args())
        self.assertEqual(report["git_commit"], "start")
        self.assertFalse(report["git_dirty"])
        self.assertEqual(report["entrypoint"]["sha256"], "start-hash")

    def test_two_concurrent_report_writers_publish_exactly_once(self):
        first = _prepare_report_destination(self.args())
        second = _prepare_report_destination(self.args())
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(_publish_report, destination, {"writer": index})
                    for index, destination in enumerate((first, second))
                ]
            results = []
            for future in futures:
                try:
                    future.result()
                    results.append("ok")
                except Exception:
                    results.append("error")
            self.assertEqual(sorted(results), ["error", "ok"])
            self.assertIn(json.loads(self.report.read_text())["writer"], (0, 1))
            self.assertFalse(any(path.name.startswith(".") for path in self.report_root.iterdir()))
        finally:
            first.close()
            second.close()

    def test_git_state_reports_clean_and_dirty(self):
        with patch(
            "scripts.materialize_f3_bundle.subprocess.check_output",
            side_effect=["abc123\n", ""],
        ):
            self.assertEqual(_git_state(), {"commit": "abc123", "dirty": False})
        with patch(
            "scripts.materialize_f3_bundle.subprocess.check_output",
            side_effect=["abc123\n", " M file\n"],
        ):
            self.assertEqual(_git_state(), {"commit": "abc123", "dirty": True})


if __name__ == "__main__":
    unittest.main()
