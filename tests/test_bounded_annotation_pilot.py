import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from src.tfg_phase0.bounded_annotation_pilot import BoundedPilotError,PilotJob,TARGET_IDS,execute_bounded_pilot,validate_pilot_scope


def jobs():
    return [PilotJob(i,target,f"cache-{target}",{"target_id":target},{"target":target}) for i,target in enumerate(TARGET_IDS)]


class BoundedAnnotationPilotTests(unittest.TestCase):
    def test_scope_exact_order_and_budget(self):
        plan={"ordered_target_ids":["I02","I03","I04"],"budget":{"maximum_model_loads":1,"maximum_scene_calls":0,"maximum_annotation_calls":3,"maximum_total_future_calls":3,"maximum_calls_per_observation":1,"maximum_new_tokens_per_call":2048,"maximum_generated_tokens_total":6144,"retry_permitted":False,"resume_permitted":False},"execution_policy":{"continue_after_failure":False}}
        auth={"target_ids":["I02","I03","I04"],"maximum_scene_calls":0,"maximum_annotation_calls":3,"maximum_total_future_calls":3,"maximum_model_loads":1,"maximum_calls_per_observation":1,"retry_permitted":False,"resume_permitted":False,"continue_after_failure":False}
        self.assertEqual(validate_pilot_scope(plan,auth),TARGET_IDS)
        for key,value in (("target_ids",["I03","I02","I04"]),("maximum_total_future_calls",4),("retry_permitted",True)):
            changed={**auth,key:value}
            with self.subTest(key=key),self.assertRaises(BoundedPilotError):validate_pilot_scope(plan,changed)

    def test_scope_rejects_missing_wrong_type_length_order_duplicates_and_plan_budget(self):
        base={"ordered_target_ids":["I02","I03","I04"],"budget":{"maximum_model_loads":1,"maximum_scene_calls":0,"maximum_annotation_calls":3,"maximum_total_future_calls":3,"maximum_calls_per_observation":1,"maximum_new_tokens_per_call":2048,"maximum_generated_tokens_total":6144,"retry_permitted":False,"resume_permitted":False},"execution_policy":{"continue_after_failure":False}}
        auth={"target_ids":["I02","I03","I04"],"maximum_scene_calls":0,"maximum_annotation_calls":3,"maximum_total_future_calls":3,"maximum_model_loads":1,"maximum_calls_per_observation":1,"retry_permitted":False,"resume_permitted":False,"continue_after_failure":False}
        invalid=[{}, {**base,"ordered_target_ids":"I02"},{**base,"ordered_target_ids":[]},{**base,"ordered_target_ids":["I02","I03"]},{**base,"ordered_target_ids":["I02","I03","I04","I05"]},{**base,"ordered_target_ids":["I03","I02","I04"]},{**base,"ordered_target_ids":["I02","I02","I04"]},{**base,"budget":{**base["budget"],"maximum_scene_calls":1}},{**base,"budget":{**base["budget"],"retry_permitted":True}},{**base,"budget":{**base["budget"],"resume_permitted":True}},{**base,"execution_policy":{"continue_after_failure":True}}]
        for plan in invalid:
            with self.subTest(plan=plan),self.assertRaises(BoundedPilotError):validate_pilot_scope(plan,auth)

    def run_pilot(self,temporary,generate=None,build=None,write_report=None):
        calls={"load":0,"release":0,"generate":[]}
        def load():calls["load"]+=1;return object()
        def default_generate(runtime,job):calls["generate"].append(job.target_id);return json.dumps({"target":job.target_id}),{"generated_token_count":1}
        def default_build(job,raw,metadata):return {"query_id":None,"candidate_id":"annotation","image_id":job.target_id,"claim_id":job.cache_entry_id,"payload":json.loads(raw)}
        records=execute_bounded_pilot(runtime_root=Path(temporary)/"runtime",plan_id="plan",jobs=jobs(),load_runtime=load,generate_raw=generate or default_generate,parse_and_build=build or default_build,release_runtime=lambda runtime:(calls.__setitem__("release",calls["release"]+1)),now=lambda:"now",**({"write_report":write_report} if write_report else {}))
        return records,calls

    def test_three_successes_one_load_order_and_no_retry(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            records,calls=self.run_pilot(temporary);root=Path(temporary)/"runtime"
            self.assertEqual(calls,{"load":1,"release":1,"generate":["I02","I03","I04"]});self.assertEqual([r["image_id"] for r in records],list(TARGET_IDS));self.assertEqual(len((root/"checkpoints/annotation-proposals.jsonl").read_text().splitlines()),4);self.assertTrue((root/"run-start.json").exists());self.assertTrue((root/"pilot-report.json").exists());self.assertFalse((root/"run-failure.json").exists())
            for target in TARGET_IDS:self.assertTrue((root/f"diagnostics/attempts/annotation-{target}/attempt-001/raw.json").exists());self.assertTrue((root/f"diagnostics/attempts/annotation-{target}/attempt-001/result.json").exists())

    def test_first_failure_stops_following_jobs_and_preserves_raw(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            calls=[]
            def generate(runtime,job):calls.append(job.target_id);return "not-json",{}
            with self.assertRaises(json.JSONDecodeError):self.run_pilot(temporary,generate=generate,build=lambda job,raw,metadata:json.loads(raw))
            root=Path(temporary)/"runtime";self.assertEqual(calls,["I02"]);self.assertTrue((root/"diagnostics/attempts/annotation-I02/attempt-001/raw.json").exists());self.assertTrue((root/"diagnostics/attempts/annotation-I02/attempt-001/failure.json").exists());self.assertFalse((root/"diagnostics/attempts/annotation-I03").exists());self.assertFalse((root/"pilot-report.json").exists());self.assertTrue((root/"run-failure.json").exists())

    def test_second_and_third_failure_are_fail_fast(self):
        for failing,expected in (("I03",["I02","I03"]),("I04",["I02","I03","I04"])):
            with self.subTest(failing=failing),tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
                calls=[]
                def generate(runtime,job):calls.append(job.target_id);return json.dumps({"target":job.target_id}),{}
                def build(job,raw,metadata):
                    if job.target_id==failing:raise ValueError("contract failure")
                    return {"query_id":None,"candidate_id":"annotation","image_id":job.target_id,"claim_id":job.cache_entry_id}
                with self.assertRaises(ValueError):self.run_pilot(temporary,generate=generate,build=build)
                self.assertEqual(calls,expected);self.assertFalse((Path(temporary)/"runtime/pilot-report.json").exists())

    def test_generation_failure_charged_without_raw_and_stops(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            calls=[]
            def generate(runtime,job):calls.append(job.target_id);raise RuntimeError("GPU failure")
            with self.assertRaises(RuntimeError):self.run_pilot(temporary,generate=generate)
            root=Path(temporary)/"runtime/diagnostics/attempts/annotation-I02/attempt-001";self.assertEqual(calls,["I02"]);self.assertTrue((root/"attempt.json").exists());self.assertFalse((root/"raw.json").exists());self.assertTrue((root/"failure.json").exists())

    def test_load_failure_happens_before_generation(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            generated=[]
            with self.assertRaisesRegex(RuntimeError,"load"):execute_bounded_pilot(runtime_root=Path(temporary)/"runtime",plan_id="p",jobs=jobs(),load_runtime=lambda:(_ for _ in ()).throw(RuntimeError("load")),generate_raw=lambda r,j:(generated.append(j.target_id) or ("{}",{})),parse_and_build=lambda j,r,m:{},release_runtime=lambda r:None,now=lambda:"now")
            self.assertEqual(generated,[]);self.assertFalse((Path(temporary)/"runtime/diagnostics/attempts").exists());self.assertTrue((Path(temporary)/"runtime/run-failure.json").exists())

    def test_existing_runtime_rejects_before_load(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            (Path(temporary)/"runtime").mkdir();loads=[]
            with self.assertRaisesRegex(BoundedPilotError,"reanudación prohibida"):execute_bounded_pilot(runtime_root=Path(temporary)/"runtime",plan_id="p",jobs=jobs(),load_runtime=lambda:loads.append(True),generate_raw=lambda r,j:("{}",{}),parse_and_build=lambda j,r,m:{},release_runtime=lambda r:None,now=lambda:"now")
            self.assertFalse(loads)

    def test_checkpoint_or_report_failure_never_generates_again(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            calls=[]
            def generate(runtime,job):calls.append(job.target_id);return "{}",{}
            def build(job,raw,metadata):return {"query_id":None,"candidate_id":"annotation","image_id":job.target_id,"claim_id":job.cache_entry_id}
            with self.assertRaises(OSError):self.run_pilot(temporary,generate=generate,build=build,write_report=lambda path,doc:(_ for _ in ()).throw(OSError("report")))
            self.assertEqual(calls,list(TARGET_IDS));root=Path(temporary)/"runtime";self.assertFalse((root/"pilot-report.json").exists())
            with self.assertRaises(BoundedPilotError):self.run_pilot(temporary,generate=generate,build=build)
            self.assertEqual(calls,list(TARGET_IDS))

    def test_checkpoint_append_failure_stops_before_next_job(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            calls=[]
            def append(path,**kwargs):raise OSError("checkpoint")
            with self.assertRaisesRegex(OSError,"checkpoint"):execute_bounded_pilot(runtime_root=Path(temporary)/"runtime",plan_id="p",jobs=jobs(),load_runtime=lambda:object(),generate_raw=lambda r,j:(calls.append(j.target_id) or ("{}",{})),parse_and_build=lambda j,r,m:{"query_id":None,"candidate_id":"annotation","image_id":j.target_id,"claim_id":j.cache_entry_id},release_runtime=lambda r:None,now=lambda:"now",append_checkpoint=append)
            self.assertEqual(calls,["I02"]);root=Path(temporary)/"runtime/diagnostics/attempts/annotation-I02/attempt-001";self.assertTrue((root/"result.json").exists());self.assertFalse((Path(temporary)/"runtime/diagnostics/attempts/annotation-I03").exists())

    def test_core_module_does_not_import_torch(self):
        command="import sys; import src.tfg_phase0.bounded_annotation_pilot; print('torch' in sys.modules)"
        result=subprocess.run(["python","-c",command],capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout.strip(),"False")

    def test_wrong_job_order_rejected(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as temporary:
            reversed_jobs=list(reversed(jobs()))
            with self.assertRaises(BoundedPilotError):execute_bounded_pilot(runtime_root=Path(temporary)/"runtime",plan_id="p",jobs=reversed_jobs,load_runtime=lambda:None,generate_raw=lambda r,j:("{}",{}),parse_and_build=lambda j,r,m:{},release_runtime=lambda r:None,now=lambda:"now")


if __name__=="__main__":unittest.main()
