#!/usr/bin/env python3
"""Prepara artefactos CPU; no autoriza/lanza workers ni inicia contenedores."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from research.dq_pilot_gb10_runtime_v1 import load_and_validate_request
from research.dq_pilot_real_adapters_v1 import MetadataOnlyMapillaryPanelAdapter
from research.dq_pilot_supervised_visual_v1 import (
    PANEL_CONTRACT, PanelEnvelope, check_image, digest, file_digest, from_visual_postflight, native_bytes, panel_rows, require,
)
from research.dq_pilot_supervised_v1 import OperationId
from pydantic import TypeAdapter


def read(path):
    return json.loads(path.read_bytes())


def publish(path, payload):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent) as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
        try:
            os.link(stream.name, path, follow_symlinks=False)
        except FileExistsError:
            require(not path.is_symlink() and path.read_bytes() == payload, 'artefacto ya publicado divergente')
        fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def prepare_panel(context, *, catalog, inventory, cache, expectation, inbox):
    require(context['mode'] == 'real' and context['stage'] in ('E0','E1','E2') and digest(context['ranking']) == context['ranking_sha256']
            and digest(context['reserve']) == context['reserve_sha256']
            and re.fullmatch(r'dq-iterative-[0-9a-f-]{36}', context['session_id']), 'contexto de preparación inválido')
    cache = cache.resolve(strict=True)
    panel = dict(MetadataOnlyMapillaryPanelAdapter(catalog=catalog, inventory=inventory, cache_root=cache,
        original_description=context['original_description'], session_id=context['session_id']).build(
        round_index=int(context['stage'][1:]), ranking=context['ranking'], reserve=context['reserve']['results']))
    require(panel['status'] == 'prepared_pending_review', 'cobertura Mapillary insuficiente; no se crea operación')
    images = sorted(panel['images'], key=lambda row: row['candidate_ref'])
    panel['images'] = [{**row, 'image_ref':f'I{index}'} for index, row in enumerate(images, 1)]
    envelope = PanelEnvelope.model_validate(dict(contract_version=PANEL_CONTRACT, panel=panel, panel_sha256=digest(panel),
        processor_expectation=expectation, **{k:context[k] for k in ('mode','session_id','stage','ranking_sha256',
            'reserve_sha256','ct2l_terminal_sha256','accumulated_description_sha256')})).model_dump()
    rows = panel_rows(envelope, context)
    for image, row in zip(panel['images'], rows):
        source = (cache / image['logical_path']).resolve(strict=True)
        require(source.is_relative_to(cache) and source.is_file() and source.stat().st_size == row['size_bytes'], 'archivo Mapillary inválido')
        publish(inbox/'visual-media'/f"{row['sha256']}.jpg", check_image(source.read_bytes(), row))
    publish(inbox/'panels'/f"{context['session_id']}-{context['stage']}.json", native_bytes(envelope))
    return envelope


def materialize_native(expected, *, media, output):
    require(expected['component'] == 'dq_pilot' and expected['stage'] in ('E0','E1','E2') and expected['ground_truth_used'] is False,
            'operación no visual')
    inp, request = expected['input'], expected['input']['request']
    payload = native_bytes(request)
    require(expected['input_sha256'] == digest(inp) and file_digest(payload) == inp['request_sha256']
            and request['session_id'] == expected['session_id'] and request['round_index'] == int(expected['stage'][1:]), 'entrada nativa divergente')
    for index, row in enumerate(request['images'], 1):
        require(row['logical_path'] == f'media/I{index}.jpg' and len(row['sha256']) == 64
                and all(c in '0123456789abcdef' for c in row['sha256']), 'ruta de medio divergente')
        source = media/f"{row['sha256']}.jpg"
        require(source.is_file() and not source.is_symlink() and source.stat().st_size == row['size_bytes'], 'medio no disponible')
        publish(output/row['logical_path'], check_image(source.read_bytes(), row))
    path = output/'request.json'
    publish(path, payload)
    _, observed = load_and_validate_request(path)
    require(observed == inp['request_sha256'], 'worker oficial rechaza identidad nativa')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    panel = sub.add_parser('panel')
    for field in ('context','catalog','inventory','cache','expectation','inbox'):
        panel.add_argument('--'+field, type=Path, required=True)
    native = sub.add_parser('native-request')
    for field in ('expected','media','output'):
        native.add_argument('--'+field, type=Path, required=True)
    terminal = sub.add_parser('terminal')
    for field in ('expected','commit','postflight','inbox'):
        terminal.add_argument('--'+field, type=Path, required=True)
    for field in ('projection','native-commit','worker-release'):
        terminal.add_argument('--'+field, type=Path)
    args = parser.parse_args()
    if args.command == 'panel':
        document = prepare_panel(read(args.context), catalog=read(args.catalog), inventory=read(args.inventory),
                                 cache=args.cache, expectation=read(args.expectation), inbox=args.inbox)
        print(document['panel_sha256'])
    elif args.command == 'native-request':
        print(materialize_native(read(args.expected), media=args.media, output=args.output))
    else:
        expected = read(args.expected)
        identifier = TypeAdapter(OperationId).validate_python(expected['operation_id'])
        document = from_visual_postflight(expected, commit=read(args.commit), postflight=read(args.postflight),
            output_bytes=args.projection.read_bytes() if args.projection else None,
            native_commit_bytes=args.native_commit.read_bytes() if args.native_commit else None,
            worker_release_bytes=args.worker_release.read_bytes() if args.worker_release else None)
        path = args.inbox/'terminals'/f'{identifier}.json'
        publish(path, native_bytes(document))
        print(path)


if __name__ == '__main__':
    main()
