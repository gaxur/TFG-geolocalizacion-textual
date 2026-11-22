"""Incorporación CPU de commits de un supervisor; no ejecuta ni reintenta modelos."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import stat
from uuid import uuid4

from research.dq_pilot_iterative_controller_v1 import digest, digest_text, retrieval_evidence
from research.dq_pilot_supervised_v1 import (
    ContractError, OP_ID_PATTERN, POLICY_B_SHA256, Registration, Terminal,
    operation, project_ct2l, project_qwen, validate_terminal,
)
from research.dq_pilot_supervised_visual_v1 import MAX_IMAGE_BYTES, check_image, project_question, project_translation, visual_operation
from .dq_iterative_sessions import DQIterativeConflict, DQIterativeUnavailable, utcnow
from .dq_supervised_visual import SupervisedVisual

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


def _read_document(directory, filename, limit=MAX_DOCUMENT_BYTES):
    """Solo archivos regulares, subdirectorios fijos y sin seguir enlaces."""
    flags = os.O_DIRECTORY | os.O_NOFOLLOW | os.O_RDONLY
    parent = os.open(directory.parent, flags)
    try:
        folder = os.open(directory.name, flags, dir_fd=parent)
        try:
            with os.fdopen(os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder), "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                    raise ContractError("archivo de supervisor inválido")
                payload = stream.read(limit + 1)
        finally:
            os.close(folder)
    finally:
        os.close(parent)
    if len(payload) > limit:
        raise ContractError("archivo de supervisor demasiado grande")
    return payload


class SupervisedSessions(SupervisedVisual):
    def __init__(self, service, inbox: Path, *, fixture=False, host_lease_receipts: Path | None = None,
                 final_visual_depth=50, cells_geojson: Path | None = None):
        self.service = service
        self.inbox = inbox.absolute()
        self.mode = "cpu_fixture" if fixture else "real"
        self.host_lease_receipts = host_lease_receipts
        from src.tfg_phase0.final_visual_ranking import DEPTHS
        if final_visual_depth not in DEPTHS:
            raise ValueError('profundidad visual esperada: 10, 50 o 100')
        self.final_visual_depth = final_visual_depth
        self.cells_geojson = cells_geojson
        storage = service.session_root.resolve()
        trusted = inbox.resolve()
        if storage == trusted or storage in trusted.parents or trusted in storage.parents:
            raise ValueError("el buzón de confianza debe estar separado de las sesiones")
        if host_lease_receipts is not None:
            lease_root = host_lease_receipts.resolve()
            if any(lease_root == path or lease_root.is_relative_to(path) or path.is_relative_to(lease_root)
                   for path in (storage, trusted)):
                raise ValueError("el lease de host debe estar separado del buzón y las sesiones")

    def _check_host_release(self, expected, terminal):
        if self.mode != 'real' or terminal['status'] != 'SUCCEEDED':
            return
        root = self.host_lease_receipts
        if root is None:
            raise ContractError('faltan recibos del lease de host')
        operation_sha = digest(expected)
        try:
            receipt = json.loads(_read_document(root, f'{operation_sha}.release.json'))
        except OSError as exc:
            raise ContractError('falta el recibo de postflight del host') from exc
        lease = receipt['lease']
        if (lease['contract_version'] != 'atlas-dq-exclusive-stage-lease-v1'
                or lease['operation_sha256'] != operation_sha
                or any(lease[key] != expected[key] for key in ('session_id', 'operation_id', 'component', 'mode'))
                or receipt['postflight_sha256'] != terminal['evidence']['postflight_sha256']
                or receipt['terminal_sha256'] != digest(terminal)
                or receipt['execution_id'] != terminal['process']['execution_id']
                or receipt['cgroup_state'] not in ('empty', 'removed')):
            raise ContractError('recibo de lease/postflight divergente')

    def _file(self, folder, filename, schema, *, allow_missing=False):
        try:
            model = schema.model_validate_json(_read_document(self.inbox / folder, filename))
            document = model.model_dump(exclude_none=schema is Registration, exclude_unset=schema is Terminal,
                                        exclude={'visual_safety'} if schema is Terminal and model.visual_safety is None else None)
            digest(document)  # Rechaza no finitos también dentro del JSON nativo.
            return document
        except FileNotFoundError as exc:
            if allow_missing:
                return None
            raise DQIterativeUnavailable("documento terminal/registro aún no publicado") from exc
        except (OSError, ValueError) as exc:
            raise DQIterativeConflict("documento supervisado inválido") from exc

    def _read_visual_blob(self, row):
        try:
            return check_image(_read_document(self.inbox / 'visual-media', f"{row['sha256']}.jpg", MAX_IMAGE_BYTES), row)
        except (OSError, ValueError) as exc:
            raise DQIterativeConflict('medio Mapillary ausente o divergente') from exc

    @staticmethod
    def _event(bridge, stage, status, message, code=None):
        rows = bridge["events"]
        rows.append(dict(event_id=str(len(rows) + 1), stage=stage, state=status, message=message,
                         error_code=code, created_at_utc=utcnow()))

    def register_e0(self, session_id):
        service = self.service
        service.load(session_id)  # No crear un directorio a partir de un identificador inexistente.
        with (service._path(session_id) / ".transition.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            meta = service.load(session_id)
            if meta.get("execution_mode") == "historical_replay":
                raise DQIterativeConflict("una reproducción histórica no admite registro real")
            bridge = meta.get("supervised")
            registration = self._file("registrations", f"{session_id}.json", Registration, allow_missing=bridge is not None)
            if bridge is not None:
                if bridge["registration"]["mode"] != self.mode or (registration is not None and registration != bridge["registration"]):
                    raise DQIterativeConflict("el registro supervisado ya está congelado")
                return meta, False
            if (meta["status"] != "waiting_authorization" or meta.get("current_stage") != "QWEN_E0"
                    or meta["controller_root"] is not None or meta.get("gpu_used") is not False
                    or meta.get("search_executed") is not False or meta.get("rankings_available") is not False):
                raise DQIterativeConflict("sesión no elegible para E0 supervisada")
            if ((registration["session_id"], registration["session_sha256"], registration["description_sha256"], registration["mode"])
                    != (session_id, meta["session_sha256"], digest_text(meta["description_es"]), self.mode)
                    or registration["qwen"]["policy_sha256"] != POLICY_B_SHA256):
                raise DQIterativeConflict("registro no ligado a la sesión, modo o política B exacta")
            state = dict(original_description=meta["description_es"], accumulated_description=meta["description_es"],
                         turns=[], rounds=[], round_index=0, controller_state="LLM_INTERPRETATION")
            bridge = dict(registration=registration, state=state, artifacts={}, receipts={}, events=service.events(session_id),
                          expected=operation(registration, state, "qwen", registration["operation_id"]))
            self._event(bridge, "supervised_registration", "pending", "Esperando el terminal de Qwen E0 del supervisor.")
            meta.update(supervised=bridge, status="pending", execution_mode=self.mode)
            return service._persist_meta(meta), True

    def expected(self, session_id):
        bridge = self.service.load(session_id).get("supervised")
        if bridge is None or bridge["registration"]["mode"] != self.mode or bridge["expected"] is None:
            raise DQIterativeConflict("sin operación supervisada pendiente")
        expected = bridge["expected"]
        if self.mode == 'real' and expected['component'] == 'crosstext2loc':
            try:
                require_current = operation(bridge['registration'], bridge['state'], 'crosstext2loc',
                    expected['operation_id'], **self._ct2l_antecedent(bridge, expected['stage']))
                if require_current != expected:
                    raise ContractError('operación CT2L no vigente')
            except (KeyError, TypeError, ValueError) as exc:
                raise DQIterativeConflict('CT2L sin interpretación Qwen vigente y acreditada') from exc
        return expected

    def _ct2l_antecedent(self, bridge, stage):
        index = bridge['state']['round_index']
        qwen = [row for row in bridge['receipts'].values() if row['terminal']['component'] == 'qwen'
                and row['terminal']['stage'] == stage and row['terminal']['status'] == 'SUCCEEDED']
        if stage != f'E{index}' or len(qwen) != 1:
            raise ContractError('no hay un único antecedente Qwen aceptado')
        self._check_host_release(qwen[0]['operation'], qwen[0]['terminal'])
        return dict(interpretation=bridge['artifacts'][f'rounds/round-{index}/llm-interpretation.json'],
                    qwen_commit=qwen[0]['terminal_sha256'])

    def consume(self, session_id, operation_id):
        if not re.fullmatch(OP_ID_PATTERN, operation_id):
            raise DQIterativeConflict("ID de operación supervisada inválido")
        service = self.service
        service.load(session_id)
        with (service._path(session_id) / ".transition.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            meta = service.load(session_id)
            bridge = meta.get("supervised")
            if bridge is None or bridge["registration"]["mode"] != self.mode:
                raise DQIterativeConflict("sesión no registrada para resultados supervisados")
            state, expected = bridge["state"], bridge["expected"]
            receipt = bridge["receipts"].get(operation_id)
            if receipt is not None:
                if receipt["terminal"]["stage"] != f"E{state['round_index']}":
                    raise DQIterativeConflict("resultado de una etapa anterior")
                duplicate = self._file("terminals", f"{operation_id}.json", Terminal, allow_missing=True)
                if duplicate is not None and digest(duplicate) != receipt["terminal_sha256"]:
                    raise DQIterativeConflict("resultado divergente para una operación consumida")
                return meta, False
            if expected is None or expected["operation_id"] != operation_id:
                raise DQIterativeConflict("resultado no esperado para esta sesión y etapa")
            terminal = self._file("terminals", f"{operation_id}.json", Terminal)
            artifacts = bridge["artifacts"]
            stage, component = expected["stage"], expected["component"]
            prefix = f"rounds/round-{state['round_index']}"
            try:
                antecedent = {}
                if component == "crosstext2loc":
                    antecedent = self._ct2l_antecedent(bridge, stage)
                if component in {'dq_pilot', 'qwen_translation'}:
                    context = self._visual_context(bridge)
                    visual = bridge['visual'][stage]
                    if component == 'dq_pilot':
                        for row in visual['rows']:
                            self._read_visual_blob(row)
                    current = visual_operation(bridge['registration'], state, component, operation_id, context=context, visual=visual)
                else:
                    current = operation(bridge["registration"], state, component, operation_id, **antecedent)
                if (current != expected or digest_text(meta["description_es"]) != current["input"]["description_sha256"]
                        or state["original_description"] != meta["description_es"]):
                    raise ContractError("entrada del controlador cambió")
                validate_terminal(expected, terminal)
                self._check_host_release(expected, terminal)
                terminal_sha = digest(terminal)
                if terminal["status"] == "SUCCEEDED" and component == "qwen":
                    projected = project_qwen(expected, state, terminal["result"])
                elif terminal["status"] == "SUCCEEDED" and component == "crosstext2loc":
                    interpretation = artifacts[f"{prefix}/llm-interpretation.json"]
                    ranking = project_ct2l(expected, state, terminal["result"])
                    reserve, record = retrieval_evidence(state, interpretation, ranking, top_n=20)
                elif terminal['status'] == 'SUCCEEDED' and component == 'dq_pilot':
                    projected = project_question(expected, terminal['result'])
                    if projected['release_sha256'] != terminal['evidence']['worker_release_sha256']:
                        raise ContractError('release DQ no corresponde al resultado')
                elif terminal['status'] == 'SUCCEEDED' and component == 'qwen_translation':
                    projected = project_translation(expected, terminal['result'])
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise DQIterativeConflict("terminal supervisado rechazado; contrato, entrada o evidencias no verificadas") from exc

            bridge["receipts"][operation_id] = dict(operation=expected, terminal_sha256=terminal_sha, terminal=terminal)
            bridge["expected"] = None
            if terminal["status"] != "SUCCEEDED":
                state["controller_state"] = "FAILED"
                meta.update(status="failed", stop_reason=f"supervised_{component}_{terminal['status'].lower()}",
                             gpu_used=False if self.mode == "cpu_fixture" else True if meta.get("gpu_used") is True else None)
                self._event(bridge, f"{stage}_{component}", "failed", "El supervisor no completó la operación.", terminal["status"])
                self._event(bridge, stage, "failed", "Fallo terminal persistido. No se inicia la etapa siguiente.", terminal["status"])
            elif component == "qwen":
                artifacts[f"{prefix}/llm-interpretation.json"] = projected
                bridge["expected"] = operation(bridge["registration"], state, "crosstext2loc", str(uuid4()),
                                               interpretation=projected, qwen_commit=terminal_sha)
                state["controller_state"] = "CT2L_RETRIEVAL"
                meta.update(current_stage=f"CT2L_{stage}", gpu_used=meta.get('gpu_used') is True or (
                    self.mode == 'real' and terminal['release'].get('worker_device') != 'cpu'))
                self._event(bridge, f"{stage}_qwen", "completed", "Interpretación Qwen verificada y guardada.")
                self._event(bridge, f"{stage}_crosstext2loc", "pending", "Ranking CT2L pendiente de su propia autorización y resultado.")
            elif component == 'dq_pilot':
                visual.update(generation=projected, dq_terminal_sha256=terminal_sha)
                self._status(meta, state, 'AWAITING_QUESTION_REVIEW', 'waiting_review', f'QUESTION_{stage}')
                self._event(bridge, f'{stage}_dq_pilot', 'completed', 'Pregunta EN y liberación verificadas.')
                self._event(bridge, stage, 'waiting_review', 'Se requiere revisión perceptual de la pregunta y su panel.')
            elif component == 'qwen_translation':
                self.save_translation(meta, bridge, stage, projected, origin='supervised_qwen' if self.mode == 'real' else 'cpu_fixture')
            else:
                artifacts[record["ranking_ref"]] = ranking
                artifacts[record["reserve_ref"]] = reserve
                state["rounds"].append(record)
                if stage == 'E0':
                    self._persist_reserve_geometry(bridge, ranking)
                stopped = bool(state['turns'] and (state['turns'][-1].get('answer') or {}).get('user_requests_stop'))
                done = stage == 'E3' or stopped
                status = 'completed' if done else 'waiting_review'
                self._status(meta, state, 'COMPLETED' if done else 'AWAITING_DQ_AUTHORIZATION', status,
                             None if done else f'DQ_{stage}', stop='human_requested_stop_after_updated_retrieval' if stopped else
                             'max_questions_reached_after_e3' if done else None)
                meta.update(search_executed=True, rankings_available=True, gpu_used=self.mode == 'real')
                self._event(bridge, f"{stage}_crosstext2loc", "completed", "Recuperación exhaustiva CT2L verificada.")
                self._event(bridge, f"{stage}_ranking", "completed", "Ranking completo guardado; Top-10 disponible.")
                self._event(bridge, stage, status, "Ranking final disponible." if done else "Ranking disponible. DQ-Pilot no se inicia automáticamente.")
            # Snapshot único: recepción, resultado/estado y outbox se publican juntos o no se publican.
            return service._persist_meta(meta), True

    def consume_final_visual(self, session_id):
        self.service.load(session_id)  # Valida el ID antes de resolver el archivo.
        try:
            evidence = json.loads(_read_document(self.inbox / 'final-visual', f'{session_id}.json'))
        except (OSError, ValueError) as exc:
            raise DQIterativeConflict('evidencia visual final no disponible o inválida') from exc
        return self.apply_final_visual(session_id, evidence)
