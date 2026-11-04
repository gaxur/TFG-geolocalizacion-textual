import hashlib
import json
import unittest

from src.tfg_phase0.visual_reranking import (
    VisualRerankingError, aggregate_candidate_evidence, atomic_verification_prompt, compact_atomic_verdict_schema, compact_atomic_verification_prompt, compile_atomic_claims, compile_atomic_claims_v2, validate_atomic_claims_v2,
    evaluate_topk_transition, parse_atomic_verdict, parse_compact_atomic_verdict, parse_verdict_only, plan_multiview_associations, rerank_experimental, verdict_only_prompt, verdict_only_schema,
)


class AtomicClaimTests(unittest.TestCase):
    def test_claims_are_stable_literal_and_typed(self):
        text = "Estoy en una calle empedrada. A mi derecha hay una farmacia Primor."
        first = compile_atomic_claims(text, ["Primor"]); second = compile_atomic_claims(text, ["Primor"])
        self.assertEqual(first, second)
        self.assertTrue(any(row["requires_orientation"] for row in first["claims"]))
        self.assertTrue(any(row["requires_ocr"] for row in first["claims"]))
        for row in first["claims"]:
            span = row["evidence"]["span"]
            self.assertEqual(text[span["start"]:span["end"]], row["evidence"]["text"])

    def test_h11_distinctive_theater_and_sign_are_compiled(self):
        claims=compile_atomic_claims("Enfrente tengo un teatro con carteles publicitarios.")["claims"]
        values=[row["value"].get("object_type") for row in claims]
        self.assertIn("theater",values); self.assertIn("advertising_sign",values)

    def test_atomic_verdict_rejects_absence_contradiction_and_unreadable_name(self):
        claims = compile_atomic_claims("Veo Primor.", ["Primor"])["claims"]
        claim = next(row for row in claims if row["requires_ocr"])
        base = {"claim_id":claim["claim_id"],"candidate_id":"c","image_id":"i","verdict":"supported","observed_evidence":"un comercio","ocr_text":None,"orientation_comparable":False,"limitations":[]}
        with self.assertRaises(VisualRerankingError): parse_atomic_verdict(json.dumps(base,separators=(",",":")),claim,candidate_id="c",image_id="i")
        base.update({"verdict":"unverifiable","observed_evidence":None,"limitations":["none","too_far"]})
        with self.assertRaises(VisualRerankingError): parse_atomic_verdict(json.dumps(base,separators=(",",":")),claim,candidate_id="c",image_id="i")
        base.update({"verdict":"contradicted","limitations":["out_of_frame"]})
        with self.assertRaises(VisualRerankingError): parse_atomic_verdict(json.dumps(base,separators=(",",":")),claim,candidate_id="c",image_id="i")

    def test_trivalent_verdict_contract_accepts_visible_support_contradiction_and_ambiguity(self):
        claim=compile_atomic_claims("Veo una iglesia.")["claims"][0]
        common={"claim_id":claim["claim_id"],"candidate_id":"c","image_id":"i","ocr_text":None,"orientation_comparable":False}
        supported={**common,"verdict":"supported","observed_evidence":"fachada de iglesia visible","limitations":["none"]}
        contradicted={**common,"verdict":"contradicted","observed_evidence":"el edificio visible es una nave industrial incompatible","limitations":["none"]}
        ambiguous={**common,"verdict":"unverifiable","observed_evidence":None,"limitations":["occluded"]}
        self.assertEqual(parse_atomic_verdict(json.dumps(supported,separators=(",",":")),claim,candidate_id="c",image_id="i")["verdict"],"supported")
        self.assertEqual(parse_atomic_verdict(json.dumps(contradicted,separators=(",",":")),claim,candidate_id="c",image_id="i")["verdict"],"contradicted")
        self.assertEqual(parse_atomic_verdict(json.dumps(ambiguous,separators=(",",":")),claim,candidate_id="c",image_id="i")["verdict"],"unverifiable")

    def test_atomic_prompt_is_small_and_orientation_is_external(self):
        claim = compile_atomic_claims("A mi derecha hay una iglesia.")["claims"][0]
        prompt = atomic_verification_prompt(claim,candidate_id="c",image_id="i")
        self.assertLess(len(prompt),2200)
        self.assertIn("fijada externamente a false",prompt)
        raw={"claim_id":claim["claim_id"],"candidate_id":"c","image_id":"i","verdict":"supported","observed_evidence":"iglesia visible","ocr_text":None,"orientation_comparable":True,"limitations":[]}
        with self.assertRaisesRegex(VisualRerankingError,"comparabilidad"):
            parse_atomic_verdict(json.dumps(raw,separators=(",",":")),claim,candidate_id="c",image_id="i")

    def test_compact_output_adds_ids_deterministically(self):
        claim=compile_atomic_claims("Veo una iglesia.")["claims"][0]
        prompt=compact_atomic_verification_prompt(claim)
        self.assertNotIn(claim["claim_id"],prompt)
        raw='{"verdict":"supported","observed_evidence":"Iglesia visible","ocr_text":null,"limitations":["none"]}'
        parsed=parse_compact_atomic_verdict(raw,claim,candidate_id="c",image_id="i")
        self.assertEqual((parsed["claim_id"],parsed["candidate_id"],parsed["image_id"]),(claim["claim_id"],"c","i"))
        self.assertFalse(compact_atomic_verdict_schema()["additionalProperties"])

    def test_verdict_only_contract_is_independent_from_explanation(self):
        claim=compile_atomic_claims("Veo una iglesia.")["claims"][0]
        self.assertEqual(parse_verdict_only('{"verdict":"supported"}'),"supported")
        self.assertEqual(set(verdict_only_schema()["properties"]),{"verdict"})
        self.assertNotIn("explanation",verdict_only_prompt(claim))


class AggregateRerankingTests(unittest.TestCase):
    def test_sequence_duplicates_do_not_multiply_support(self):
        claim = compile_atomic_claims("Veo una iglesia.")["claims"][0]
        associations=[{"candidate_id":"c","image_id":"i1","sequence_id":"s"},{"candidate_id":"c","image_id":"i2","sequence_id":"s"}]
        verdicts=[{"status":"valid","candidate_id":"c","image_id":"i1","claim_id":claim["claim_id"],"verdict":"supported"},{"status":"valid","candidate_id":"c","image_id":"i2","claim_id":claim["claim_id"],"verdict":"supported"}]
        result=aggregate_candidate_evidence([claim],associations,verdicts)["candidates"][0]
        self.assertEqual(result["claims"][0]["independent_sequences"],1)
        self.assertEqual(result["positive_evidence"],1.0)

    def test_same_sequence_support_and_contradiction_is_neutral_conflict(self):
        claim=compile_atomic_claims("Veo una iglesia.")["claims"][0]
        associations=[{"candidate_id":"c","image_id":"i1","sequence_id":"s"},{"candidate_id":"c","image_id":"i2","sequence_id":"s"}]
        verdicts=[{"status":"valid","candidate_id":"c","image_id":"i1","claim_id":claim["claim_id"],"verdict":"supported"},{"status":"valid","candidate_id":"c","image_id":"i2","claim_id":claim["claim_id"],"verdict":"contradicted"}]
        result=aggregate_candidate_evidence([claim],associations,verdicts)["candidates"][0]
        self.assertEqual(result["claims"][0]["state"],"unverifiable")
        self.assertEqual(result["claims"][0]["conflicting_sequences"],1)
        self.assertEqual((result["positive_evidence"],result["negative_evidence"]),(0,0))

    def test_candidate_without_photos_is_kept_neutral(self):
        claim=compile_atomic_claims("Veo una iglesia.")["claims"][0]
        result=aggregate_candidate_evidence([claim],[],[],candidate_ids=["a"])["candidates"][0]
        self.assertEqual(result["candidate_id"],"a")
        self.assertEqual(result["coverage_status"],"no_coverage")
        self.assertEqual((result["positive_evidence"],result["negative_evidence"]),(0,0))

    def test_disabled_reranking_preserves_order_and_enabled_keeps_ids(self):
        baseline={"results":[{"rank":1,"candidate_id":"a","cosine_similarity":.4},{"rank":2,"candidate_id":"b","cosine_similarity":.3}]}
        aggregate={"candidates":[{"candidate_id":"a","positive_evidence":0,"negative_evidence":1},{"candidate_id":"b","positive_evidence":1,"negative_evidence":0}]}
        disabled=rerank_experimental(baseline,aggregate)
        self.assertEqual([r["candidate_id"] for r in disabled["results"]],["a","b"])
        enabled=rerank_experimental(baseline,aggregate,enabled=True,lambda_pos=1,lambda_neg=1)
        self.assertEqual({r["candidate_id"] for r in enabled["results"]},{"a","b"})
        self.assertEqual(enabled["results"][0]["candidate_id"],"b")

    def test_multiview_plan_reuses_asset_across_candidates(self):
        candidates=[{"candidate_id":"a","latitude":40.0,"longitude":-3.0},{"candidate_id":"b","latitude":40.0,"longitude":-3.0}]
        images=[{"image_id":"i","latitude":40.0,"longitude":-3.0,"orientation_degrees":0,"sequence_id":"s","camera_type":"equirectangular","quality_score":1}]
        plan=plan_multiview_associations(candidates,images,max_images_per_candidate=1)
        self.assertEqual(plan["association_count"],2)
        self.assertEqual(plan["unique_asset_count"],1)

    def test_multiview_plan_accepts_eight_images_per_candidate(self):
        candidates=[{"candidate_id":"a","latitude":40.0,"longitude":-3.0}]
        images=[{"image_id":str(index),"latitude":40.0,"longitude":-3.0,"orientation_degrees":index*40,"sequence_id":str(index),"camera_type":"perspective","quality_score":1.0} for index in range(8)]
        plan=plan_multiview_associations(candidates,images,max_images_per_candidate=8)
        self.assertEqual(plan["association_count"],8)

    def test_english_cartographic_claims_keep_exact_source_hash(self):
        text="To my left is a white building with columns and to my right is a stone building with flags."
        document=compile_atomic_claims(text)
        self.assertEqual(document["source_text_sha256"],hashlib.sha256(text.encode()).hexdigest())
        self.assertTrue({"building","column","flag"}<={row["value"].get("object_type") for row in document["claims"] if row["kind"]=="object_presence"})
        self.assertTrue(any(row["requires_orientation"] for row in document["claims"]))

    def test_v2_facing_targets_main_altar(self):
        document=compile_atomic_claims_v2("I am inside a church, facing the main altar.")
        claim=next(row for row in document["claims"] if row["kind"]=="egocentric_relation")
        self.assertEqual(claim["value"]["subject_type"],"altar")
        self.assertIn(claim["value"]["subject_entity_id"],{row["entity_id"] for row in document["entities"]})

    def test_v2_front_targets_dark_altarpiece(self):
        document=compile_atomic_claims_v2("In front of me is a dark altarpiece with columns.")
        relation=next(row for row in document["claims"] if row["kind"]=="egocentric_relation")
        dark=next(row for row in document["claims"] if row["kind"]=="attribute" and row["evidence"]["text"].casefold()=="dark")
        self.assertEqual(relation["value"]["subject_type"],"altarpiece")
        self.assertEqual(dark["value"]["subject_entity_id"],relation["value"]["subject_entity_id"])

    def test_v2_repeated_buildings_keep_distinct_entities(self):
        text="To my left is a large white building with columns, and to my right is a stone building with flags."
        document=compile_atomic_claims_v2(text)
        buildings=[row for row in document["entities"] if row["object_type"]=="building"]
        self.assertEqual(len(buildings),2)
        self.assertNotEqual(buildings[0]["entity_id"],buildings[1]["entity_id"])
        white=next(row for row in document["claims"] if row["kind"]=="attribute" and row["evidence"]["text"]=="white")
        stone=next(row for row in document["claims"] if row["kind"]=="attribute" and row["evidence"]["text"]=="stone")
        left=next(row for row in document["claims"] if row["kind"]=="egocentric_relation" and "left" in row["evidence"]["text"].casefold())
        right=next(row for row in document["claims"] if row["kind"]=="egocentric_relation" and "right" in row["evidence"]["text"].casefold())
        self.assertEqual(white["value"]["subject_entity_id"],left["value"]["subject_entity_id"])
        self.assertEqual(stone["value"]["subject_entity_id"],right["value"]["subject_entity_id"])
        self.assertNotEqual(white["value"]["subject_entity_id"],stone["value"]["subject_entity_id"])

    def test_v2_relation_can_target_preceding_entity(self):
        document=compile_atomic_claims_v2("The church is to my right.")
        relation=next(row for row in document["claims"] if row["kind"]=="egocentric_relation")
        self.assertEqual(relation["value"]["subject_type"],"church")

    def test_v2_missing_subject_is_unknown_not_invented(self):
        document=compile_atomic_claims_v2("To my left there is nothing identifiable.")
        relation=next(row for row in document["claims"] if row["kind"]=="egocentric_relation")
        self.assertEqual(relation["value"],{"subject_entity_id":None,"subject_type":"unknown","relation":"left_of_observer"})

    def test_v2_spans_hashes_and_entity_references_validate(self):
        text="A large white building has columns."
        document=compile_atomic_claims_v2(text)
        self.assertEqual(document["source_text_sha256"],hashlib.sha256(text.encode()).hexdigest())
        validate_atomic_claims_v2(document)
        for row in document["claims"]:
            span=row["evidence"]["span"]
            self.assertEqual(text[span["start"]:span["end"]],row["evidence"]["text"])
        manipulated=json.loads(json.dumps(document))
        attribute=next(row for row in manipulated["claims"] if row["kind"]=="attribute")
        attribute["value"]["subject_entity_id"]="visual-entity-sha256-"+"0"*64
        attribute["claim_id"]="visual-claim-sha256-"+hashlib.sha256(json.dumps({k:v for k,v in attribute.items() if k!="claim_id"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        with self.assertRaisesRegex(VisualRerankingError,"entidad"):
            validate_atomic_claims_v2(manipulated)

    def test_multiview_and_reranking_reject_ground_truth(self):
        with self.assertRaisesRegex(ValueError,"GT"):
            plan_multiview_associations([{"candidate_id":"a","latitude":40.0,"longitude":-3.0,"ground_truth":True}],[])
        with self.assertRaisesRegex(ValueError,"reference"):
            rerank_experimental({"results":[{"rank":1,"candidate_id":"a","cosine_similarity":.4}],"reference":{"latitude":40}}, {"candidates":[]})

    def test_gt_evaluation_requires_invariant_set_and_reports_improvement(self):
        baseline=[{"candidate_id":"a","latitude":40.0,"longitude":-3.01},{"candidate_id":"b","latitude":40.0,"longitude":-3.0}]
        experimental=[{"candidate_id":"b"},{"candidate_id":"a"}]
        result=evaluate_topk_transition(baseline,experimental,reference_latitude=40.0,reference_longitude=-3.0)
        self.assertEqual(result["transition"]["top1"],"improved")
        self.assertTrue(result["transition"]["top10_set_invariant"])
        self.assertTrue(result["experimental"]["geo5_50"])
        with self.assertRaises(VisualRerankingError): evaluate_topk_transition(baseline,[{"candidate_id":"c"},{"candidate_id":"a"}],reference_latitude=40.0,reference_longitude=-3.0)


if __name__ == "__main__": unittest.main()
