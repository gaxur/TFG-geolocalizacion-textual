import hashlib,json,sys,tempfile,time,unittest
from pathlib import Path

from scripts.qwen3_vl_dialogue_worker import DIAGNOSTIC_OUTPUT_LIMIT,generate_with_constraints,persist_generation_diagnostic,validate_request
from scripts.run_dialogue_v3_visual_worker_smoke import MAXIMUM_PSI_AVG10,MAXIMUM_SWAP_FRACTION,MINIMUM_RAM_BYTES,STABLE_SWAP_SAMPLES,evaluate_memory_gate,memory_pressure,request_id,run_supervised


ROOT=Path(__file__).resolve().parents[1]

def sample(*,ram=MINIMUM_RAM_BYTES+2*1024**3,swap_fraction=.99,psi=.0,vmstat=None,processes=None):
    total=10000
    return {"system":{"ram_available_bytes":ram,"swap_total_bytes":total,"swap_used_bytes":int(total*swap_fraction),"swap_free_bytes":total-int(total*swap_fraction)},"memory_pressure":{"status":"VERIFIED","some":{"avg10":psi},"full":{"avg10":psi}},"vmstat":vmstat or {"pswpin":1,"pswpout":2,"pgmajfault":3,"pgscan_direct":4,"pgsteal_direct":5,"oom_kill":0},"compute_processes":processes or []}

def stable_gate(samples):
    return evaluate_memory_gate(policy="stable-swap",host_compute_process_count=0,host_ollama_status="no_model_resident",samples=samples)

def request(root:Path):
    image=root/'image.png';image.write_bytes(b'fixture');doc={"schema_version":"1.0","contract_version":"dialogue-visual-worker-request-v1","model":{"model_id":"Qwen/Qwen3-VL-8B-Instruct","revision":"0c351dd01ed87e9c1b53cbc748cba10e6187ff3b","model_path":"/models/Qwen3-VL-8B"},"image":{"image_id":"i","path":"/authorized-images/image.png","sha256":hashlib.sha256(b'fixture').hexdigest(),"provenance":{"source":"synthetic"},"authorized":True,"authorization_id":"a","observer_relation":"synthetic_transport_only"},"claim":{"claim_id":"c","kind":"object_presence","value":{"object":"shape"},"source_text":"shape"},"generation":{"dtype":"bfloat16","attention":"sdpa","do_sample":False,"max_new_tokens":96},"timeouts":{"load_seconds":150,"inference_seconds":30,"total_seconds":240},"protocol":{"ground_truth_used":False,"reserved_sets_used":False,"network_used":False,"single_inference":True}};doc['request_id']=request_id(doc);return doc,image

class WorkerTests(unittest.TestCase):
    def test_generate_connects_prefix_callback_without_changing_limit(self):
        class Model:
            def generate(self,**kwargs):self.kwargs=kwargs;return "generated"
        model=Model();prefix=object();result=generate_with_constraints(model=model,inputs={"input_ids":"tokens"},max_new_tokens=192,prefix_allowed_tokens_fn=prefix)
        self.assertEqual(result,"generated");self.assertIs(model.kwargs["prefix_allowed_tokens_fn"],prefix);self.assertEqual(model.kwargs["max_new_tokens"],192);self.assertFalse(model.kwargs["do_sample"])

    def test_generation_diagnostic_validates_and_is_private(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);raw=json.dumps({"verdict":"unverifiable","observed_evidence":None,"ocr_text":None,"limitations":[]});doc=persist_generation_diagnostic(output_root=root,raw=raw,output_tokens=23,max_new_tokens=96,inference_ms=1.5,decode_ms=.2,eos_reached=True);path=root/'generation-diagnostic.json'
            self.assertEqual(doc['validation'],{"json_syntax":True,"json_schema":True,"semantic_contract":True,"error":None});self.assertEqual(path.stat().st_mode&0o777,0o600);self.assertNotIn('prompt',doc);self.assertEqual(doc['termination_reason'],'eos')

    def test_generation_diagnostic_rejects_invalid_truncated_and_special_text(self):
        for raw,tokens,reason in (("```json\n{}\n```",4,"other"),('{"verdict":',96,"max_new_tokens"),("x"*(DIAGNOSTIC_OUTPUT_LIMIT+1),96,"max_new_tokens")):
            with self.subTest(raw=raw[:20]),tempfile.TemporaryDirectory() as t:
                doc=persist_generation_diagnostic(output_root=Path(t),raw=raw,output_tokens=tokens,max_new_tokens=96,inference_ms=1,decode_ms=1,eos_reached=False);self.assertFalse(doc['validation']['semantic_contract']);self.assertEqual(doc['termination_reason'],reason);self.assertLessEqual(len(doc['raw_output']),DIAGNOSTIC_OUTPUT_LIMIT)

    def test_valid_request_and_allowlist(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);doc,image=request(root);self.assertEqual(validate_request(doc,ROOT/'schemas/dialogue_visual_worker_request.schema.json',root),image)

    def test_generation_contract_versions_bind_token_budget(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);doc,_=request(root);doc['contract_version']='dialogue-visual-worker-request-v2';doc['generation']['max_new_tokens']=192;doc['request_id']=request_id(doc);validate_request(doc,ROOT/'schemas/dialogue_visual_worker_request.schema.json',root)
            doc['generation']['max_new_tokens']=96;doc['request_id']=request_id(doc)
            with self.assertRaises(ValueError):validate_request(doc,ROOT/'schemas/dialogue_visual_worker_request.schema.json',root)
    def test_rejects_tampered_id_hash_and_path(self):
        for mutation in ('id','hash','path'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as t:
                root=Path(t);doc,_=request(root)
                if mutation=='id':doc['request_id']='visual-worker-request-sha256-'+'0'*64
                elif mutation=='hash':doc['image']['sha256']='0'*64;doc['request_id']=request_id(doc)
                else:doc['image']['path']='/authorized-images/../secret';doc['request_id']=request_id(doc)
                with self.assertRaises(Exception):validate_request(doc,ROOT/'schemas/dialogue_visual_worker_request.schema.json',root)
    def test_supervisor_enforces_real_timeout_and_terminates_child(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);result=run_supervised([sys.executable,'-c','import time;time.sleep(30)'],1,root);self.assertTrue(result['timed_out']);self.assertIsNotNone(result['returncode']);self.assertLess(result['duration_ms'],15000)
    def test_supervisor_records_nonzero_worker_failure(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);result=run_supervised([sys.executable,'-c','raise RuntimeError("CUDA simulated")'],10,root);self.assertFalse(result['timed_out']);self.assertNotEqual(result['returncode'],0);self.assertIn('CUDA simulated',result['stderr'])

    def test_supervisor_script_validate_only_end_to_end(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);images=root/'images';images.mkdir();fixture=images/'image.png';fixture.write_bytes(b'fixture');output=root/'out'
            completed=__import__('subprocess').run([sys.executable,str(ROOT/'scripts/run_dialogue_v3_visual_worker_smoke.py'),'--validate-only','--output-root',str(output),'--fixture',str(fixture),'--image-mount-dir',str(images),'--model-dir',str(root/'unused-model'),'--total-timeout','20','--host-compute-process-count','0','--host-ollama-status','no_model_resident'],capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stderr);self.assertTrue((output/'worker/request.validated.json').is_file())

    def test_resource_gate_constants_are_frozen(self):
        self.assertEqual(MINIMUM_RAM_BYTES,40*1024**3);self.assertEqual(MAXIMUM_SWAP_FRACTION,.95);self.assertEqual(MAXIMUM_PSI_AVG10,.10);self.assertIn(memory_pressure()['status'],{'VERIFIED','NOT_VERIFIED'})

    def test_hard_swap_remains_default_and_rejects_full_swap(self):
        gate=evaluate_memory_gate(policy="hard-swap",host_compute_process_count=0,host_ollama_status="no_model_resident",samples=[sample()]);self.assertFalse(gate["passed"]);self.assertIn("swap_fraction_above_limit",gate["blocking_reasons"])

    def test_stable_swap_accepts_quiet_full_swap_with_residual_risk(self):
        gate=stable_gate([sample() for _ in range(STABLE_SWAP_SAMPLES)]);self.assertTrue(gate["passed"]);self.assertIn("risk",gate["residual_risk"])

    def test_stable_swap_rejects_activity_pressure_ram_gpu_and_ollama(self):
        cases=[]
        active=[sample() for _ in range(STABLE_SWAP_SAMPLES)];active[-1]["vmstat"]["pswpin"]+=1;cases.append(stable_gate(active))
        cases.append(stable_gate([sample(psi=.1) for _ in range(STABLE_SWAP_SAMPLES)]))
        cases.append(stable_gate([sample(ram=MINIMUM_RAM_BYTES-1) for _ in range(STABLE_SWAP_SAMPLES)]))
        cases.append(stable_gate([sample(processes=[{"pid":1}]) for _ in range(STABLE_SWAP_SAMPLES)]))
        cases.append(evaluate_memory_gate(policy="stable-swap",host_compute_process_count=0,host_ollama_status="model_resident",samples=[sample() for _ in range(STABLE_SWAP_SAMPLES)]))
        for gate in cases:self.assertFalse(gate["passed"])

    def test_stable_swap_rejects_missing_or_unverifiable_metrics(self):
        missing=[sample() for _ in range(STABLE_SWAP_SAMPLES)];missing[-1]["vmstat"].pop("oom_kill");self.assertFalse(stable_gate(missing)["passed"])
        unverified=[sample() for _ in range(STABLE_SWAP_SAMPLES)];unverified[-1]["memory_pressure"]={"status":"NOT_VERIFIED"};self.assertFalse(stable_gate(unverified)["passed"])

    def test_observer_manifest_template_is_explicitly_unauthorized(self):
        from jsonschema import Draft202012Validator
        schema=json.loads((ROOT/'schemas/dialogue_observer_image_manifest.schema.json').read_text());template=json.loads((ROOT/'config/dialogue_observer_image_manifest.template.json').read_text());self.assertEqual(list(Draft202012Validator(schema).iter_errors(template)),[]);self.assertFalse(template['authorized']);self.assertEqual(template['status'],'template_incomplete');self.assertIsNone(template['observer_relation'])

    def test_supervisor_persists_blocked_preflight_without_starting_worker(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);images=root/'images';images.mkdir();fixture=images/'image.png';fixture.write_bytes(b'fixture');output=root/'out'
            completed=__import__('subprocess').run([sys.executable,str(ROOT/'scripts/run_dialogue_v3_visual_worker_smoke.py'),'--output-root',str(output),'--fixture',str(fixture),'--image-mount-dir',str(images),'--model-dir',str(root/'unused-model'),'--host-compute-process-count','1','--host-ollama-status','model_resident'],capture_output=True,text=True)
            self.assertEqual(completed.returncode,2);report=json.loads((output/'report.json').read_text());self.assertEqual(report['status'],'BLOCKED_BY_GPU');self.assertFalse(report['worker_started']);self.assertFalse((output/'worker').exists())

    def test_supervisor_distinguishes_memory_policy_block(self):
        source=(ROOT/'scripts/run_dialogue_v3_visual_worker_smoke.py').read_text()
        self.assertIn('BLOCKED_BY_MEMORY_POLICY',source)

if __name__=='__main__':unittest.main()
