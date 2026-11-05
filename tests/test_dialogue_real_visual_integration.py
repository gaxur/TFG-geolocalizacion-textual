import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path

from src.tfg_phase0.dialogue_visual_evidence import RESERVED_SET_EXCLUSION,RealQwen3VLDialogueEvidenceProvider,load_observer_image_manifest
from src.tfg_phase0.interactive_dialogue import InteractiveDialogueError

ROOT=Path(__file__).resolve().parents[1]

def manifest(root:Path):
    image=root/'observer.jpg';image.write_bytes(b'authorized observer bytes');sha=hashlib.sha256(image.read_bytes()).hexdigest();doc={"schema_version":"1.0","contract_version":"dialogue-observer-image-manifest-v1","status":"authorized","image_id":"observer-1","logical_path":"observer.jpg","sha256":sha,"source":"own-controlled-photo","author":"test-author","license_or_authorization":"local-test-authorization","acquired_at_utc":"2026-11-04T00:00:00Z","provenance_url":None,"observer_relation":"observer_view","observer_relation_evidence":"captured by the observer from the described viewpoint","usage_restrictions":["local-test-only"],"reserved_set_exclusion":RESERVED_SET_EXCLUSION,"session_id":"session-1","intent_family":"monument","authorized":True,"authorization_id":"auth-1"};path=root/'manifest.json';path.write_text(json.dumps(doc));return path,doc,image

def request():return {"session_id":"session-1","turn_index":1,"intent":{"intent_id":"intent-1","feature":"monument","label":"monumento"},"question_sha256":"a"*64,"input_ranking_sha256":"b"*64,"claim":{"claim_id":"claim-1","kind":"object_presence","value":{"feature":"monument"}},"image":{}}

class Executor:
    def __init__(self,result=None,error=None):self.result=result;self.error=error;self.calls=0
    def __call__(self,req,ref):self.calls+=1

class RealVisualIntegrationTests(unittest.TestCase):
    def load(self,root):return load_observer_image_manifest(manifest(root)[0],ROOT/'schemas/dialogue_observer_image_manifest.schema.json')
    def test_valid_manifest_builds_reference_and_provider_record(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);doc,ref=self.load(root);executor=lambda req,reference:{"status":"PASS","parsed_output":{"verdict":"supported","observed_evidence":"monumento visible","ocr_text":None,"limitations":[]}};provider=RealQwen3VLDialogueEvidenceProvider(manifest=doc,reference=ref,executor=executor);record=provider.inspect(request());self.assertEqual(record['state'],'supported');self.assertFalse(record['query_update_allowed']);self.assertFalse(record['ranking_update_allowed']);self.assertEqual(record['intent_family'],'monument')
    def test_manifest_rejections(self):
        mutations=(("incomplete",lambda d:d.update(status="template_incomplete",authorized=False)),("hash",lambda d:d.update(sha256="f"*64)),("authorization",lambda d:d.update(authorization_id=None)),("relation",lambda d:d.update(observer_relation=None)),("reserved",lambda d:d.update(reserved_set_exclusion="unknown")))
        for name,mutate in mutations:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as t:
                root=Path(t);path,doc,_=manifest(root);mutate(doc);path.write_text(json.dumps(doc))
                with self.assertRaises(InteractiveDialogueError):load_observer_image_manifest(path,ROOT/'schemas/dialogue_observer_image_manifest.schema.json')
    def test_session_and_intent_must_match_before_executor(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);doc,ref=self.load(root);calls=[];provider=RealQwen3VLDialogueEvidenceProvider(manifest=doc,reference=ref,executor=lambda req,reference:calls.append(req))
            for key,value in (("session_id","other"),("feature","church")):
                req=request()
                if key=="feature":req['intent']['feature']=value
                else:req[key]=value
                with self.assertRaises(InteractiveDialogueError):provider.inspect(req)
            self.assertEqual(calls,[])
    def test_worker_error_timeout_invalid_json_and_semantics_fail_closed(self):
        results=(RuntimeError("worker"),TimeoutError("timeout"),{"raw_output":"not json"},{"parsed_output":{"verdict":"supported","observed_evidence":None,"ocr_text":None,"limitations":[]}})
        for result in results:
            with self.subTest(result=repr(result)),tempfile.TemporaryDirectory() as t:
                root=Path(t);doc,ref=self.load(root)
                def execute(req,reference):
                    if isinstance(result,Exception):raise result
                    return result
                provider=RealQwen3VLDialogueEvidenceProvider(manifest=doc,reference=ref,executor=execute)
                with self.assertRaises(Exception):provider.inspect(request())
    def test_cli_requires_explicit_gpu_authorization_and_rejects_ambiguity(self):
        script=str(ROOT/'scripts/run_interactive_dialogue.py');base=[sys.executable,script,'--output-dir','/tmp/not-created']
        cases=(base+['--visual-image-manifest','manifest.json'],base+['--authorize-visual-gpu'],base+['--fake-visual-manifest','fake.json','--visual-image-manifest','real.json'])
        for command in cases:
            completed=subprocess.run(command,capture_output=True,text=True);self.assertEqual(completed.returncode,2);self.assertFalse(Path('/tmp/not-created').exists())

if __name__=='__main__':unittest.main()
