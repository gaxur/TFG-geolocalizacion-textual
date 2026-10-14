import multiprocessing
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.tfg_phase0.f3_bundle import (
    F3BundleConflictError,
    _rename_noreplace,
    publish_f3_bundle,
)
from src.tfg_phase0.f3_serialization import build_f3_bundle_bytes
from src.tfg_phase0.f3_validation import validate_f3_bundle
from tests.test_phase3_bundle import fixture_inputs


ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 10


def publish_worker(output, start, result, variant=0):
    try:
        values = list(fixture_inputs())
        if variant:
            inputs = values[0]
            values[0] = type(inputs)(
                catalog=type(inputs.catalog)(
                    **{**inputs.catalog.__dict__, "manifest_id": f"madrid-pilot-grid-v1-s{25 + variant}-l25"}
                ),
                snapshot=inputs.snapshot,
                inventory=inputs.inventory,
                rules=inputs.rules,
                config_sha256=inputs.config_sha256,
                config_canonical_sha256=inputs.config_canonical_sha256,
                config_path=inputs.config_path,
                config_effective_sha256=inputs.config_effective_sha256,
            )
        start.wait(TIMEOUT)
        destination, hit = publish_f3_bundle(
            *values, project_root=ROOT, processed_osm_root=Path(output)
        )
        result.put(("ok", destination.name, hit))
    except BaseException as error:
        result.put(("error", type(error).__name__, str(error)))


def locked_worker(output, locked, release, result=None, after_rename=False):
    values = fixture_inputs()
    import src.tfg_phase0.f3_bundle as bundle_module

    original_rename = bundle_module._rename_noreplace
    original_fsync = bundle_module._fsync_directory

    def pause_before(source, destination):
        locked.set()
        if not release.wait(TIMEOUT):
            raise TimeoutError("release not received")
        return original_rename(source, destination)

    def pause_after(path):
        if path.name.startswith("osm-"):
            locked.set()
            if not release.wait(TIMEOUT):
                raise TimeoutError("release not received")
        return original_fsync(path)

    target = "src.tfg_phase0.f3_bundle._fsync_directory" if after_rename else "src.tfg_phase0.f3_bundle._rename_noreplace"
    replacement = pause_after if after_rename else pause_before
    try:
        with patch(target, side_effect=replacement):
            destination, hit = publish_f3_bundle(
                *values, project_root=ROOT, processed_osm_root=Path(output)
            )
        if result is not None:
            result.put(("ok", destination.name, hit))
    except BaseException as error:
        if result is not None:
            result.put(("error", type(error).__name__, str(error)))


@unittest.skipUnless(sys.platform.startswith("linux"), "publicación F3 exclusiva de Linux")
class Phase3BundleConcurrencyTests(unittest.TestCase):
    def context(self):
        return multiprocessing.get_context("fork")

    def assert_finished(self, process):
        process.join(TIMEOUT)
        if process.is_alive():
            process.kill()
            process.join(TIMEOUT)
            self.fail("el proceso F3 no terminó dentro del timeout")

    def cleanup_workers(self, processes, result, *release_events):
        if any(process.is_alive() for process in processes):
            for event in release_events:
                event.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(TIMEOUT)
            if process.is_alive():
                process.kill()
                process.join(TIMEOUT)
            process.close()
        if result is not None:
            result.close()
            result.join_thread()

    def validate_destination(self, output, values=None):
        values = values or fixture_inputs()
        dataset_id = build_f3_bundle_bytes(*values, project_root=ROOT)[0]
        destination = Path(output) / values[0].snapshot.osm_snapshot_id / dataset_id
        validate_f3_bundle(
            destination, inputs=values[0], normalized=values[1],
            association_inventory=values[2], relation_inventory=values[3],
        )
        return destination

    def test_two_processes_same_id_publish_at_most_once(self):
        context = self.context()
        with tempfile.TemporaryDirectory() as directory:
            start = context.Event()
            result = context.Queue()
            processes = [
                context.Process(target=publish_worker, args=(directory, start, result))
                for _ in range(2)
            ]
            try:
                for process in processes:
                    process.start()
                start.set()
                for process in processes:
                    self.assert_finished(process)
                outcomes = [result.get(timeout=TIMEOUT) for _ in processes]
                successes = [row for row in outcomes if row[0] == "ok"]
                self.assertGreaterEqual(len(successes), 1, outcomes)
                self.assertLessEqual(sum(not row[2] for row in successes), 1, outcomes)
                self.assertTrue(all(row[0] == "ok" or row[1] == "F3BundleConflictError" for row in outcomes))
                self.validate_destination(directory)
            finally:
                self.cleanup_workers(processes, result, start)

    def test_process_holding_lock_causes_explicit_conflict(self):
        context = self.context()
        with tempfile.TemporaryDirectory() as directory:
            locked = context.Event()
            release = context.Event()
            result = context.Queue()
            owner = context.Process(target=locked_worker, args=(directory, locked, release, result))
            try:
                owner.start()
                self.assertTrue(locked.wait(TIMEOUT))
                with self.assertRaises(F3BundleConflictError):
                    publish_f3_bundle(
                        *fixture_inputs(), project_root=ROOT, processed_osm_root=Path(directory)
                    )
                release.set()
                self.assert_finished(owner)
                self.assertEqual(result.get(timeout=TIMEOUT)[0], "ok")
                self.validate_destination(directory)
            finally:
                self.cleanup_workers([owner], result, release)

    def test_distinct_ids_publish_without_lock_interference(self):
        context = self.context()
        with tempfile.TemporaryDirectory() as directory:
            start = context.Event()
            result = context.Queue()
            processes = [
                context.Process(target=publish_worker, args=(directory, start, result, variant))
                for variant in (1, 2)
            ]
            try:
                for process in processes:
                    process.start()
                start.set()
                for process in processes:
                    self.assert_finished(process)
                outcomes = [result.get(timeout=TIMEOUT) for _ in processes]
                self.assertTrue(all(row[0] == "ok" and row[2] is False for row in outcomes), outcomes)
                self.assertEqual(len({row[1] for row in outcomes}), 2)
                parent = Path(directory) / fixture_inputs()[0].snapshot.osm_snapshot_id
                self.assertEqual(len(tuple(path for path in parent.iterdir() if not path.name.startswith("."))), 2)
            finally:
                self.cleanup_workers(processes, result, start)

    def test_killed_before_rename_leaves_no_destination_and_abandoned_lock(self):
        context = self.context()
        with tempfile.TemporaryDirectory() as directory:
            locked = context.Event()
            release = context.Event()
            process = context.Process(target=locked_worker, args=(directory, locked, release))
            try:
                process.start()
                self.assertTrue(locked.wait(TIMEOUT))
                process.kill()
                self.assert_finished(process)
                values = fixture_inputs()
                dataset_id = build_f3_bundle_bytes(*values, project_root=ROOT)[0]
                parent = Path(directory) / values[0].snapshot.osm_snapshot_id
                self.assertFalse((parent / dataset_id).exists())
                self.assertTrue((parent / f".{dataset_id}.lock").is_dir())
                with self.assertRaises(F3BundleConflictError):
                    publish_f3_bundle(*values, project_root=ROOT, processed_osm_root=Path(directory))
            finally:
                self.cleanup_workers([process], None, release)

    def test_killed_after_rename_leaves_valid_bundle_and_abandoned_lock(self):
        context = self.context()
        with tempfile.TemporaryDirectory() as directory:
            visible = context.Event()
            release = context.Event()
            process = context.Process(
                target=locked_worker, args=(directory, visible, release, None, True)
            )
            try:
                process.start()
                self.assertTrue(visible.wait(TIMEOUT))
                destination = self.validate_destination(directory)
                process.kill()
                self.assert_finished(process)
                lock = destination.parent / f".{destination.name}.lock"
                self.assertTrue(lock.is_dir())
                same, hit = publish_f3_bundle(
                    *fixture_inputs(), project_root=ROOT, processed_osm_root=Path(directory)
                )
                self.assertEqual(same, destination)
                self.assertTrue(hit)
                self.assertTrue(lock.is_dir())
            finally:
                self.cleanup_workers([process], None, release)

    def test_real_linux_rename_noreplace_preserves_source_and_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            (source / "payload").write_bytes(b"source-bytes")
            (destination / "payload").write_bytes(b"destination-bytes")

            with self.assertRaises(FileExistsError):
                _rename_noreplace(source, destination)

            self.assertEqual((source / "payload").read_bytes(), b"source-bytes")
            self.assertEqual((destination / "payload").read_bytes(), b"destination-bytes")

    def test_real_linux_publish_no_replace_cache_hit_and_clean_state(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            values = fixture_inputs()
            destination, hit = publish_f3_bundle(
                *values, project_root=ROOT, processed_osm_root=output
            )
            self.assertFalse(hit)
            before = {path.name: path.read_bytes() for path in destination.iterdir()}
            same, hit = publish_f3_bundle(
                *values, project_root=ROOT, processed_osm_root=output
            )
            self.assertTrue(hit)
            self.assertEqual(same, destination)
            self.assertEqual(before, {path.name: path.read_bytes() for path in destination.iterdir()})
            residual = tuple(path for path in destination.parent.iterdir() if path.name.startswith("."))
            self.assertEqual(residual, ())


if __name__ == "__main__":
    unittest.main()
