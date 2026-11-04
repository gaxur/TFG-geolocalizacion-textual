import json
import unittest
from pathlib import Path

import jsonschema

from src.tfg_phase0.i20_assisted_annotation import I20AssistedError,annotation_evidence_draft_schema_v10,materialize_annotation_evidence_draft,unique_literal_span


ROOT=Path(__file__).resolve().parents[1]
V9_RAW=ROOT/'results/generated/i01-i20-assisted-annotation-v9/diagnostics/attempts/annotation-I01/attempt-001/raw.json'


def draft(description='Se observa una tienda con el rótulo TIGER junto a una calle urbana con edificios y peatones.'):
    return {'description_es':description,'claims':[{'kind':'visible_text','semantic_text_es':'Se ve el nombre comercial TIGER','evidence_quote':'el rótulo TIGER','observability':'direct','certainty':'certain','requires_ocr':True,'requires_orientation':False,'orientation_frame':'unknown','limitations':[]}],'visible_text':[{'transcription_es':'TIGER','evidence_quote':'el rótulo TIGER','legibility':'readable','certainty':'certain'}],'visual_uncertainty':{'overall_status':'adequate','limitations':[],'notes_es':None},'orientation':{'status':'unknown','bearing_degrees':None,'uncertainty_degrees':None,'meaning':'unknown','source':'not_available','evidence_ids':[],'cardinal_conversion_allowed':False},'human_review_required':True}


class I20LiteralEvidenceTests(unittest.TestCase):
    def test_unique_literal_span_exact_python_indices(self):
        text='Árbol junto a TIGER; señal al fondo.';span=unique_literal_span(text,'TIGER');self.assertEqual(span,{'start':14,'end':19});self.assertEqual(text[span['start']:span['end']],'TIGER')

    def test_materializer_separates_semantic_text_and_literal_contract(self):
        source=draft();result=materialize_annotation_evidence_draft(source);claim=result['claims'][0];self.assertEqual(claim['text_es'],'el rótulo TIGER');self.assertEqual(result['description_es'][claim['span']['start']:claim['span']['end']],claim['text_es']);self.assertNotIn('semantic_text_es',claim);self.assertNotIn('evidence_quote',claim);self.assertTrue(claim['claim_id'].startswith('i20-claim-sha256-'));self.assertEqual(result['visible_text'][0]['span'],claim['span']);self.assertEqual(source['claims'][0]['semantic_text_es'],'Se ve el nombre comercial TIGER')

    def test_absent_duplicate_empty_and_substring_ambiguity_rejected(self):
        with self.assertRaisesRegex(I20AssistedError,'no aparece'):unique_literal_span('Una calle','TIGER')
        with self.assertRaisesRegex(I20AssistedError,'múltiples'):unique_literal_span('TIGER y TIGER','TIGER')
        with self.assertRaisesRegex(I20AssistedError,'vacío'):unique_literal_span('Una calle','')
        with self.assertRaisesRegex(I20AssistedError,'múltiples'):unique_literal_span('aaaa','aa')

    def test_unicode_combining_forms_are_not_normalized_silently(self):
        composed='Café visible';decomposed='Cafe\u0301'
        with self.assertRaisesRegex(I20AssistedError,'no aparece'):unique_literal_span(composed,decomposed)
        span=unique_literal_span('Cafe\u0301 visible',decomposed);self.assertEqual('Cafe\u0301 visible'[span['start']:span['end']],decomposed)

    def test_spaces_punctuation_and_long_description(self):
        description=('Edificios y aceras. '*30)+'Texto: TIGER, junto a la entrada.';quote='TIGER,';span=unique_literal_span(description,quote);self.assertEqual(description[span['start']:span['end']],quote)
        with self.assertRaisesRegex(I20AssistedError,'no aparece'):unique_literal_span(description,'TIGER ,')

    def test_claim_without_evidence_is_contractually_rejected(self):
        source=draft();del source['claims'][0]['evidence_quote']
        with self.assertRaises(jsonschema.ValidationError):materialize_annotation_evidence_draft(source)

    def test_v9_raw_diagnosis_is_not_reinterpreted_as_v10(self):
        original=json.loads(V9_RAW.read_text());draft_v9=json.loads(original['raw_output']);description=draft_v9['description_es'];self.assertEqual(description.count('TIGER'),3)
        with self.assertRaisesRegex(I20AssistedError,'múltiples'):unique_literal_span(description,'TIGER')
        self.assertNotIn('evidence_quote',draft_v9['claims'][0]);self.assertFalse((V9_RAW.parent/'result.json').exists())

    def test_materialization_failure_is_explicit_for_ambiguous_quote(self):
        source=draft('TIGER aparece en un rótulo urbano y TIGER vuelve a citarse en la descripción completa.')
        source['claims'][0]['evidence_quote']='TIGER';source['visible_text'][0]['evidence_quote']='TIGER'
        with self.assertRaisesRegex(I20AssistedError,'múltiples'):materialize_annotation_evidence_draft(source)


if __name__=='__main__':unittest.main()
