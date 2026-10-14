import errno
import json
import os
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.tfg_phase0.f3_bundle import (
    F3BundleError,
    F3BundleConflictError,
    F3PublicationUnsupportedError,
    _fsync_directory,
    _revalidate_input_files,
    publish_f3_bundle,
)
from src.tfg_phase0.f3_identity import identity_from_provenance
from src.tfg_phase0.f3_serialization import (
    build_f3_bundle_bytes,
    canonical_json_bytes,
    checksum_bytes,
)
from src.tfg_phase0.f3_validation import F3BundleValidationError, validate_f3_bundle
from tests.test_phase3_bundle import fixture_inputs, materialize


ROOT = Path(__file__).resolve().parents[1]


class PartialWriter:
    def __init__(self, wrapped, failure=None):
        self.wrapped = wrapped
        self.failure = failure

    def __enter__(self):
        self.wrapped.__enter__()
        return self

    def __exit__(self, *args):
        return self.wrapped.__exit__(*args)

    def write(self, content):
        if self.failure == "write":
            raise OSError("write failed")
        size = max(1, len(content) // 2)
        return self.wrapped.write(content[:size])

    def flush(self):
        if self.failure == "flush":
            raise OSError("flush failed")
        return self.wrapped.flush()

    def __getattr__(self, name):
        return getattr(self.wrapped, name)


class Phase3BundleRobustnessTests(unittest.TestCase):
    def setUp(self):
        self.values = fixture_inputs()
        self.dataset_id, self.outputs, self.provenance = build_f3_bundle_bytes(
            *self.values, project_root=ROOT
        )

    def validate(self, bundle):
        return validate_f3_bundle(
            bundle, inputs=self.values[0], normalized=self.values[1],
            association_inventory=self.values[2], relation_inventory=self.values[3],
            expected_identity=identity_from_provenance(self.provenance),
        )

    def assert_clean_failure(self, output, error=Exception):
        with self.assertRaises(error):
            publish_f3_bundle(*self.values, project_root=ROOT, processed_osm_root=output)
        parent = output / self.values[0].snapshot.osm_snapshot_id
        if parent.exists():
            self.assertEqual(tuple(parent.iterdir()), ())

    def test_missing_truncated_and_appended_files_are_rejected(self):
        for filename in self.outputs:
            for mutation in ("missing", "truncated", "appended"):
                with self.subTest(filename=filename, mutation=mutation), tempfile.TemporaryDirectory() as directory:
                    bundle = Path(directory) / self.dataset_id
                    materialize(bundle, dict(self.outputs))
                    path = bundle / filename
                    if mutation == "missing":
                        path.unlink()
                    elif mutation == "truncated":
                        path.write_bytes(path.read_bytes()[:-1])
                    else:
                        path.write_bytes(path.read_bytes() + b"x")
                    with self.assertRaises(F3BundleValidationError):
                        self.validate(bundle)

    def test_extra_symlink_directory_and_fifo_are_rejected(self):
        for replacement in ("symlink", "directory", "fifo"):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                bundle = Path(directory) / self.dataset_id
                materialize(bundle, dict(self.outputs))
                target = bundle / "sha256.txt"
                target.unlink()
                if replacement == "symlink":
                    target.symlink_to(bundle / "provenance.json")
                elif replacement == "directory":
                    target.mkdir()
                else:
                    os.mkfifo(target)
                with self.assertRaises(F3BundleValidationError):
                    self.validate(bundle)
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / self.dataset_id
            materialize(bundle, dict(self.outputs))
            (bundle / "extra").write_text("x")
            with self.assertRaises(F3BundleValidationError):
                self.validate(bundle)

    def test_checksum_format_matrix_is_rejected(self):
        mutations = (
            lambda raw: raw.replace(b"  ", b" ", 1),
            lambda raw: b"\n".join(reversed(raw.splitlines())) + b"\n",
            lambda raw: raw.splitlines()[0] + b"\n" + raw,
            lambda raw: raw.rstrip(b"\n"),
            lambda raw: b"z" + raw[1:],
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as directory:
                bundle = Path(directory) / self.dataset_id
                materialize(bundle, dict(self.outputs))
                checksum = bundle / "sha256.txt"
                checksum.write_bytes(mutate(checksum.read_bytes()))
                with self.assertRaises(F3BundleValidationError):
                    self.validate(bundle)

    def test_jsonl_framing_and_noncanonical_json_are_rejected(self):
        mutations = (
            lambda raw: b"\xef\xbb\xbf" + raw,
            lambda raw: raw.replace(b"\n", b"\r\n"),
            lambda raw: raw + b"\n",
            lambda raw: raw.rstrip(b"\n"),
            lambda raw: b"{" + raw,
            lambda raw: raw.replace(b'"candidate_id"', b'"z":0, "candidate_id"'),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as directory:
                changed = dict(self.outputs)
                name = "candidate_osm_associations.jsonl"
                changed[name] = mutate(changed[name])
                changed["sha256.txt"] = checksum_bytes(changed)
                bundle = Path(directory) / self.dataset_id
                materialize(bundle, changed)
                with self.assertRaises(F3BundleValidationError):
                    self.validate(bundle)

    def test_deep_corruption_with_recalculated_checksums_is_rejected(self):
        def wrong_candidate(outputs):
            name = "candidate_osm_associations.jsonl"
            outputs[name] = outputs[name].replace(b"candidate-001", b"candidate-999")

        def wrong_reference(outputs):
            name = "osm_objects.jsonl"
            outputs[name] = outputs[name].replace(b'"node/1"', b'"node/999"')

        def duplicate_row(outputs):
            name = "osm_objects.jsonl"
            outputs[name] += outputs[name]

        def wrong_relation(outputs):
            name = "relation_context.jsonl"
            outputs[name] = outputs[name].replace(b'"relation_id":20', b'"relation_id":999')

        def wrong_counts(outputs):
            document = json.loads(outputs["provenance.json"])
            document["counts"]["associations"] += 1
            outputs["provenance.json"] = canonical_json_bytes(document, newline=True)

        def wrong_identity(outputs):
            document = json.loads(outputs["provenance.json"])
            document["f3_dataset_id"] = "f3-madrid-pilot-associations-sha256-" + "0" * 64
            outputs["provenance.json"] = canonical_json_bytes(document, newline=True)

        for mutate in (wrong_candidate, wrong_reference, duplicate_row, wrong_relation, wrong_counts, wrong_identity):
            with self.subTest(mutate=mutate.__name__), tempfile.TemporaryDirectory() as directory:
                changed = dict(self.outputs)
                mutate(changed)
                changed["sha256.txt"] = checksum_bytes(changed)
                bundle = Path(directory) / self.dataset_id
                materialize(bundle, changed)
                with self.assertRaises(F3BundleValidationError):
                    self.validate(bundle)

    def test_wrong_directory_name_and_corrupt_cache_hit_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "wrong-id"
            materialize(bundle, dict(self.outputs))
            with self.assertRaises(F3BundleValidationError):
                self.validate(bundle)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            destination, _ = publish_f3_bundle(*self.values, project_root=ROOT, processed_osm_root=output)
            (destination / "provenance.json").write_bytes(b"{}\n")
            with self.assertRaises(F3BundleConflictError):
                publish_f3_bundle(*self.values, project_root=ROOT, processed_osm_root=output)

    def test_partial_writes_are_completed(self):
        original_open = Path.open

        def partial(path, mode="r", *args, **kwargs):
            opened = original_open(path, mode, *args, **kwargs)
            return PartialWriter(opened) if mode == "xb" else opened

        with tempfile.TemporaryDirectory() as directory, patch("pathlib.Path.open", new=partial):
            destination, cache_hit = publish_f3_bundle(
                *self.values, project_root=ROOT, processed_osm_root=Path(directory)
            )
            self.assertFalse(cache_hit)
            self.validate(destination)

    def test_write_and_flush_failures_leave_no_destination(self):
        original_open = Path.open
        for operation in ("write", "flush"):
            def broken(path, mode="r", *args, **kwargs):
                opened = original_open(path, mode, *args, **kwargs)
                return PartialWriter(opened, operation) if mode == "xb" else opened

            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                with patch("pathlib.Path.open", new=broken):
                    self.assert_clean_failure(Path(directory), OSError)

    def test_each_file_and_temporary_directory_fsync_failure_is_clean(self):
        for failing_call in range(1, 7):
            calls = 0
            original = os.fsync

            def fail_nth(descriptor):
                nonlocal calls
                calls += 1
                if calls == failing_call:
                    raise OSError("fsync failed")
                return original(descriptor)

            with self.subTest(call=failing_call), tempfile.TemporaryDirectory() as directory:
                with patch("src.tfg_phase0.f3_bundle.os.fsync", side_effect=fail_nth):
                    self.assert_clean_failure(Path(directory), OSError)

    def test_validation_input_code_and_rename_failures_are_clean(self):
        cases = (
            ("src.tfg_phase0.f3_bundle.validate_f3_bundle", {"side_effect": F3BundleValidationError("bad")}, F3BundleConflictError),
            ("src.tfg_phase0.f3_bundle._revalidate_input_files", {"side_effect": F3BundleConflictError("changed")}, F3BundleConflictError),
            ("src.tfg_phase0.f3_bundle.generator_source_sha256", {"return_value": "0" * 64}, F3BundleConflictError),
            ("src.tfg_phase0.f3_bundle._rename_noreplace", {"side_effect": OSError("rename failed")}, OSError),
        )
        for target, kwargs, expected in cases:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                with patch(target, **kwargs):
                    self.assert_clean_failure(Path(directory), expected)

    def test_input_change_at_second_revalidation_is_rejected(self):
        import src.tfg_phase0.f3_bundle as bundle_module

        original = bundle_module._revalidate_input_files
        calls = 0

        def change_on_second(inputs, *, require_exact_config):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise F3BundleConflictError("input changed before publication")
            return original(inputs, require_exact_config=require_exact_config)

        with tempfile.TemporaryDirectory() as directory, patch(
            "src.tfg_phase0.f3_bundle._revalidate_input_files",
            side_effect=change_on_second,
        ):
            self.assert_clean_failure(Path(directory), F3BundleConflictError)
        self.assertEqual(calls, 2)

    def temporary_inputs(self, directory):
        inputs = self.values[0]
        root = Path(directory)
        catalog_path = root / "catalog.json"
        source_path = root / "source.osm"
        rules_path = root / "rules.json"
        config_path = root / "config.json"
        for source, destination in (
            (inputs.catalog.path, catalog_path),
            (inputs.snapshot.source_path, source_path),
            (inputs.rules.path, rules_path),
            (inputs.config_path, config_path),
        ):
            destination.write_bytes(source.read_bytes())
        return replace(
            inputs,
            catalog=replace(inputs.catalog, path=catalog_path),
            snapshot=replace(inputs.snapshot, source_path=source_path),
            rules=replace(inputs.rules, path=rules_path),
            config_path=config_path,
        )

    def test_real_input_mutations_are_rejected_without_blocking(self):
        for mutation in ("content", "symlink", "incompatible", "fifo"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                inputs = self.temporary_inputs(directory)
                target = inputs.catalog.path
                if mutation == "content":
                    target.write_bytes(target.read_bytes() + b"x")
                else:
                    target.unlink()
                    if mutation == "symlink":
                        target.symlink_to(inputs.config_path)
                    elif mutation == "incompatible":
                        target.mkdir()
                    else:
                        os.mkfifo(target)
                with self.assertRaises(F3BundleConflictError):
                    _revalidate_input_files(inputs, require_exact_config=True)

    def test_real_input_change_before_second_revalidation_prevents_publication(self):
        import src.tfg_phase0.f3_bundle as bundle_module

        with tempfile.TemporaryDirectory(dir=ROOT / "data") as directory:
            inputs = self.temporary_inputs(directory)
            values = (inputs, *self.values[1:])
            output = Path(directory) / "output"
            original = bundle_module._revalidate_input_files
            calls = 0

            def mutate_before_second(current, *, require_exact_config):
                nonlocal calls
                calls += 1
                if calls == 2:
                    current.catalog.path.write_bytes(current.catalog.path.read_bytes() + b"x")
                return original(current, require_exact_config=require_exact_config)

            with patch(
                "src.tfg_phase0.f3_bundle._revalidate_input_files",
                side_effect=mutate_before_second,
            ):
                with self.assertRaises(F3BundleConflictError):
                    publish_f3_bundle(*values, project_root=ROOT, processed_osm_root=output)
            self.assertEqual(calls, 2)
            parent = output / inputs.snapshot.osm_snapshot_id
            self.assertEqual(tuple(parent.iterdir()), ())

    def test_preexisting_lock_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            parent = output / self.values[0].snapshot.osm_snapshot_id
            parent.mkdir(parents=True)
            lock = parent / f".{self.dataset_id}.lock"
            lock.mkdir()
            with self.assertRaises(F3BundleConflictError):
                publish_f3_bundle(*self.values, project_root=ROOT, processed_osm_root=output)
            self.assertTrue(lock.is_dir())
            self.assertEqual(tuple(path for path in parent.iterdir() if path != lock), ())

    def test_valid_and_corrupt_destination_races_at_rename(self):
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)

                def race(source, destination):
                    materialize(destination, dict(self.outputs))
                    if corrupt:
                        (destination / "sha256.txt").write_text("corrupt\n")
                    raise FileExistsError(destination)

                with patch("src.tfg_phase0.f3_bundle._rename_noreplace", side_effect=race):
                    if corrupt:
                        with self.assertRaises(F3BundleConflictError):
                            publish_f3_bundle(*self.values, project_root=ROOT, processed_osm_root=output)
                    else:
                        destination, hit = publish_f3_bundle(
                            *self.values, project_root=ROOT, processed_osm_root=output
                        )
                        self.assertTrue(hit)
                        self.validate(destination)

    def test_parent_fsync_failure_keeps_visible_valid_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            calls = 0
            original = _fsync_directory

            def fail_second(path):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("parent fsync failed")
                return original(path)

            with patch("src.tfg_phase0.f3_bundle._fsync_directory", side_effect=fail_second):
                with self.assertRaises(OSError):
                    publish_f3_bundle(*self.values, project_root=ROOT, processed_osm_root=output)
            parent = output / self.values[0].snapshot.osm_snapshot_id
            destinations = tuple(path for path in parent.iterdir() if not path.name.startswith("."))
            self.assertEqual(len(destinations), 1)
            self.validate(destinations[0])
            same, hit = publish_f3_bundle(*self.values, project_root=ROOT, processed_osm_root=output)
            self.assertTrue(hit)
            self.assertEqual(same, destinations[0])

    def test_primary_error_survives_lock_cleanup_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            original_rmdir = Path.rmdir

            def fail_lock(path):
                if path.name.endswith(".lock"):
                    raise OSError("cleanup failed")
                return original_rmdir(path)

            with patch("src.tfg_phase0.f3_bundle._rename_noreplace", side_effect=OSError("primary")), patch(
                "pathlib.Path.rmdir", new=fail_lock
            ):
                with self.assertRaisesRegex(OSError, "primary"):
                    publish_f3_bundle(*self.values, project_root=ROOT, processed_osm_root=Path(directory))

    def test_temporary_cleanup_failure_is_observable_and_preserves_primary_error(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "src.tfg_phase0.f3_bundle._rename_noreplace",
            side_effect=OSError("primary"),
        ), patch(
            "src.tfg_phase0.f3_bundle.shutil.rmtree",
            side_effect=OSError("cleanup"),
        ):
            with self.assertRaisesRegex(OSError, "primary") as captured:
                publish_f3_bundle(*self.values, project_root=ROOT, processed_osm_root=Path(directory))
            self.assertTrue(any("cleanup" in note for note in captured.exception.__notes__))

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)

            def concurrent_destination(source, destination):
                materialize(destination, dict(self.outputs))
                raise FileExistsError(destination)

            with patch(
                "src.tfg_phase0.f3_bundle._rename_noreplace",
                side_effect=concurrent_destination,
            ), patch(
                "src.tfg_phase0.f3_bundle.shutil.rmtree",
                side_effect=OSError("cleanup"),
            ):
                with self.assertRaises(F3BundleError):
                    publish_f3_bundle(*self.values, project_root=ROOT, processed_osm_root=output)

    def test_capturable_interruptions_before_rename_are_clean(self):
        for interruption in (KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(kind=type(interruption).__name__), tempfile.TemporaryDirectory() as directory:
                with patch("src.tfg_phase0.f3_bundle._rename_noreplace", side_effect=interruption):
                    with self.assertRaises(type(interruption)):
                        publish_f3_bundle(*self.values, project_root=ROOT, processed_osm_root=Path(directory))
                parent = Path(directory) / self.values[0].snapshot.osm_snapshot_id
                self.assertEqual(tuple(parent.iterdir()), ())

    def test_unsupported_directory_fsync_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "src.tfg_phase0.f3_bundle.os.fsync", side_effect=OSError(errno.EINVAL, "unsupported")
        ):
            with self.assertRaises(F3PublicationUnsupportedError):
                _fsync_directory(Path(directory))

    def test_descriptor_read_is_stable_but_visible_bundle_mutation_is_residual(self):
        import src.tfg_phase0.f3_validation as validation_module

        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / self.dataset_id
            materialize(bundle, dict(self.outputs))
            original_open = os.open
            replaced = False

            def replace_after_open(path, flags, *args, **kwargs):
                nonlocal replaced
                descriptor = original_open(path, flags, *args, **kwargs)
                path = Path(path)
                if path.name == "osm_objects.jsonl" and not replaced:
                    replaced = True
                    path.unlink()
                    path.symlink_to(bundle / "provenance.json")
                return descriptor

            original = self.outputs["osm_objects.jsonl"]
            with patch.object(validation_module.os, "open", side_effect=replace_after_open):
                self.assertEqual(validation_module._read_regular(bundle / "osm_objects.jsonl"), original)
            self.assertTrue(replaced)
            with self.assertRaises(F3BundleValidationError):
                self.validate(bundle)


if __name__ == "__main__":
    unittest.main()
