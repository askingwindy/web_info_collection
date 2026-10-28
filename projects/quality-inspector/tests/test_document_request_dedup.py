"""Lossless documentary request compaction; controlled strings, no external IO.

These tests exercise only the new pure codec and the existing request builder.
They never construct a model gateway, open a production ledger or call a model.
"""
from copy import deepcopy
import hashlib
import json
import unittest

from quality_inspector import document_request_dedup as dedup
from quality_inspector import document_text_qc as original_lane


META = '_webcollect_lossless_references_v1'
SPLICE = '$webcollect_json_string_splice_v1'


def sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def long_prompt(special=''):
    # A distinctive boundary makes the whole long string occur once, even
    # though its middle contains repeated text to make size reduction visible.
    return ('CONTROLLED_PROMPT_START\n' + special + '\n'
            + '完整保留任务目标、必要动作、可见终态和来源。' * 420
            + '\nCONTROLLED_PROMPT_END')


def materials(prompt=None, *, inner_ascii=False, facts_content=None):
    prompt = long_prompt() if prompt is None else prompt
    document = '# 合成方式说明\r\n\r\n```text\n' + prompt + '\n```\r\n保留末尾。\n'
    facts = {
        'schema_version': 'webcollect-production-facts-1',
        'unrelated': {'note': '不得改动其他事实', 'count': 1},
        'prompt_stages': [{
            'batch_id': 'CONTROLLED-BATCH',
            'declaration_sha256': 'a' * 64,
            'stages': {
                'planning': {'mode': 'model', 'description': '实际规划来源', 'prompt': prompt},
                'narrative': {'mode': 'template', 'template_version': 'controlled-v1'},
            },
        }],
    }
    if facts_content is None:
        facts_content = json.dumps(facts, ensure_ascii=inner_ascii, indent=2) + '\r\n'
    docs = {'合成方式说明.md': document, '来源与合规说明.md': '受控公开来源，不包含私人内容。\n'}
    value = {
        'documents': docs,
        'payload_files_sha256': {name: sha(content) for name, content in docs.items()},
        'documentary_material_sha256': 'b' * 64,
        'supplementary_evidence': {
            'schema_version': 'webcollect-documentary-materials-2',
            'review_boundaries': {'customer_acceptance': 'UNKNOWN'},
            'supporting_run_files_outside_customer_payload': [{
                'path': '/CONTROLLED/production/facts.json',
                'sha256': sha(facts_content),
                'bytes': len(facts_content.encode('utf-8')),
                'content': facts_content,
            }],
            'verified_current_evidence': {'formal_release_ready': False, 'sample_qc': {'status': 'PASS'}},
        },
    }
    text, schema = original_lane._request(value)
    return value, text, schema, prompt


class DocumentRequestDedupTests(unittest.TestCase):
    def assert_roundtrip(self, text, *, replacements=None):
        result = dedup.compact_request(text)
        self.assertEqual(result['binding']['original_text_sha256'], sha(text))
        self.assertEqual(result['binding']['wire_text_sha256'], sha(result['text']))
        self.assertEqual(result['metrics']['original_utf8_bytes'], len(text.encode('utf-8')))
        self.assertEqual(result['metrics']['compacted_utf8_bytes'], len(result['text'].encode('utf-8')))
        if replacements is not None:
            self.assertEqual(result['metrics']['replacement_count'], replacements)
        restored = dedup.restore_request(result['text'], expected_sha256=sha(text))
        self.assertEqual(restored.encode('utf-8'), text.encode('utf-8'))
        return result

    def assert_unchanged(self, text):
        result = self.assert_roundtrip(text, replacements=0)
        self.assertEqual(result['text'], text)
        return result

    def test_unique_long_planning_prompt_compacts_and_retains_all_documents(self):
        value, text, _, _ = materials()
        before = deepcopy(value)
        result = self.assert_roundtrip(text, replacements=1)
        wire = json.loads(result['text'])
        self.assertEqual(wire['documents'], value['documents'])
        self.assertIn(META, wire)
        item = wire['supplementary_evidence']['supporting_run_files_outside_customer_payload'][0]
        self.assertIn(SPLICE, item['content'])
        self.assertEqual(item['sha256'], value['supplementary_evidence'][
            'supporting_run_files_outside_customer_payload'][0]['sha256'])
        self.assertLess(result['metrics']['compacted_utf8_bytes'], result['metrics']['original_utf8_bytes'])
        self.assertEqual(value, before)

    def test_special_characters_and_both_inner_json_encoders_restore_exact_bytes(self):
        special = '引号"、反斜线\\、换行\n、制表\t、CRLF\r\n、emoji🙂、字符e\u0301和é、字面\\u4e2d'
        for inner_ascii in (False, True):
            with self.subTest(inner_ascii=inner_ascii):
                _, text, _, _ = materials(long_prompt(special), inner_ascii=inner_ascii)
                self.assert_roundtrip(text, replacements=1)

    def test_noncanonical_inner_escape_is_left_intact_without_replacement(self):
        # Escaping the first C as \u0043 preserves the decoded value but is
        # neither standard encoder's exact string token. No normalization loss.
        value, _, _, prompt = materials()
        content = value['supplementary_evidence']['supporting_run_files_outside_customer_payload'][0]['content']
        quoted = json.dumps(prompt, ensure_ascii=False)
        self.assertIn(quoted, content)
        content = content.replace(quoted, '"\\u0043' + quoted[2:], 1)
        _, text, _, _ = materials(prompt, facts_content=content)
        self.assert_unchanged(text)

    def test_root_whitespace_and_key_order_are_not_silently_normalized(self):
        _, text, _, _ = materials()
        obj = json.loads(text)
        variants = [
            '\n' + text + '\r\n',
            json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2),
            json.dumps(dict(reversed(list(obj.items()))), ensure_ascii=False),
        ]
        for variant in variants:
            with self.subTest(length=len(variant)):
                self.assertNotEqual(variant, text)
                self.assert_unchanged(variant)

    def test_absent_duplicate_and_short_values_are_not_rewritten(self):
        value, _, _, _ = materials()
        value['documents']['合成方式说明.md'] = '不包含原规划提示词。\n'
        self.assert_unchanged(original_lane._request(value)[0])
        _, short_text, _, _ = materials('短提示词')
        self.assert_unchanged(short_text)

    def test_match_must_be_unique_across_all_documents_and_within_one_document(self):
        for multiple_documents in (False, True):
            with self.subTest(multiple_documents=multiple_documents):
                value, _, _, prompt = materials()
                if multiple_documents:
                    value['documents']['另一个声明.md'] = '第二处\n' + prompt
                    value['payload_files_sha256']['另一个声明.md'] = sha(value['documents']['另一个声明.md'])
                else:
                    value['documents']['合成方式说明.md'] += '\n第二处\n' + prompt
                self.assert_unchanged(original_lane._request(value)[0])

    def test_only_allowlisted_facts_planning_prompt_is_replaced(self):
        for mutation in ('other_file', 'other_stage', 'other_key', 'nonstring'):
            with self.subTest(mutation=mutation):
                value, _, _, prompt = materials()
                item = value['supplementary_evidence']['supporting_run_files_outside_customer_payload'][0]
                facts = json.loads(item['content'])
                if mutation == 'other_file':
                    item['path'] = '/CONTROLLED/production/other.json'
                elif mutation == 'other_stage':
                    stage = facts['prompt_stages'][0]['stages'].pop('planning')
                    facts['prompt_stages'][0]['stages']['revision'] = stage
                elif mutation == 'other_key':
                    facts['prompt_stages'][0]['stages']['planning'].pop('prompt')
                    facts['unrelated']['prompt'] = prompt
                else:
                    facts['prompt_stages'][0]['stages']['planning']['prompt'] = {'text': prompt}
                item['content'] = json.dumps(facts, ensure_ascii=False, indent=2) + '\r\n'
                item['sha256'] = sha(item['content'])
                item['bytes'] = len(item['content'].encode('utf-8'))
                self.assert_unchanged(original_lane._request(value)[0])

    def test_duplicate_root_document_keys_are_rejected_even_if_root_is_noncanonical(self):
        for text in ('{"documents":{},"documents":{}}', '{"a":1,"a":2}'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    dedup.compact_request(text)

    def test_duplicate_inner_facts_keys_are_rejected(self):
        value, _, _, _ = materials()
        item = value['supplementary_evidence']['supporting_run_files_outside_customer_payload'][0]
        item['content'] = '{"prompt_stages":[],"prompt_stages":[]}'
        item['sha256'] = sha(item['content'])
        item['bytes'] = len(item['content'].encode('utf-8'))
        with self.assertRaises(ValueError):
            dedup.compact_request(original_lane._request(value)[0])

    def test_original_facts_hash_and_utf8_byte_count_must_match_when_present(self):
        value, _, _, _ = materials()
        item = value['supplementary_evidence']['supporting_run_files_outside_customer_payload'][0]
        exact_bytes = item['bytes']
        for field, invalid_values in (
            ('sha256', ('0' * 64, '', None, True)),
            ('bytes', (exact_bytes + 1, 0, -1, True, False, float(exact_bytes), str(exact_bytes), None)),
        ):
            for invalid in invalid_values:
                with self.subTest(field=field, invalid=invalid):
                    damaged = deepcopy(value)
                    damaged['supplementary_evidence']['supporting_run_files_outside_customer_payload'][0][field] = invalid
                    with self.assertRaises(ValueError):
                        dedup.compact_request(original_lane._request(damaged)[0])

    def test_absent_optional_facts_metadata_remains_losslessly_restorable(self):
        # The codec is not a source-material approval gate. Its external full
        # request hash still protects every byte when optional metadata is absent.
        for omitted in (('sha256',), ('bytes',), ('sha256', 'bytes')):
            with self.subTest(omitted=omitted):
                value, _, _, _ = materials()
                item = value['supplementary_evidence']['supporting_run_files_outside_customer_payload'][0]
                for key in omitted:
                    item.pop(key)
                self.assert_roundtrip(original_lane._request(value)[0], replacements=1)

    def test_malformed_supplementary_and_original_content_types_reject(self):
        invalid_objects = (None, [], 'wrong', 1, True)
        for invalid in invalid_objects:
            with self.subTest(field='supplementary_evidence', invalid=invalid):
                value, _, _, _ = materials()
                value['supplementary_evidence'] = invalid
                with self.assertRaises(ValueError):
                    dedup.compact_request(original_lane._request(value)[0])
        for invalid in (None, {}, 'wrong', 1, True):
            with self.subTest(field='support_list', invalid=invalid):
                value, _, _, _ = materials()
                value['supplementary_evidence']['supporting_run_files_outside_customer_payload'] = invalid
                with self.assertRaises(ValueError):
                    dedup.compact_request(original_lane._request(value)[0])
        for invalid in invalid_objects + ({'unexpected': 'object'},):
            with self.subTest(field='facts_content', invalid=invalid):
                value, _, _, _ = materials()
                value['supplementary_evidence']['supporting_run_files_outside_customer_payload'][0]['content'] = invalid
                with self.assertRaises(ValueError):
                    dedup.compact_request(original_lane._request(value)[0])

    def test_two_original_facts_files_each_restore_independently(self):
        value, _, _, _ = materials()
        items = value['supplementary_evidence']['supporting_run_files_outside_customer_payload']
        second = deepcopy(items[0])
        second['path'] = '/CONTROLLED/another/facts.json'
        second['content'] = '\r\n' + second['content'] + '\n'
        second['sha256'] = sha(second['content'])
        second['bytes'] = len(second['content'].encode('utf-8'))
        items.append(second)
        self.assert_roundtrip(original_lane._request(value)[0], replacements=2)

    def test_external_expected_hash_is_required_and_wrong_hash_rejects(self):
        _, text, _, _ = materials()
        wire = dedup.compact_request(text)['text']
        with self.assertRaises(TypeError):
            dedup.restore_request(wire)
        for expected in ('0' * 64, '', None):
            with self.subTest(expected=expected):
                with self.assertRaises((TypeError, ValueError)):
                    dedup.restore_request(wire, expected_sha256=expected)

    def test_tampered_retained_document_and_truncated_wire_reject(self):
        _, text, _, _ = materials()
        wire = dedup.compact_request(text)['text']
        obj = json.loads(wire)
        obj['documents']['合成方式说明.md'] += '篡改'
        for changed in (canonical(obj), wire[:-1]):
            with self.subTest(kind='truncated' if changed == wire[:-1] else 'document'):
                with self.assertRaises(ValueError):
                    dedup.restore_request(changed, expected_sha256=sha(text))

    def test_tampered_reference_metadata_or_original_source_rejects(self):
        _, text, _, _ = materials()
        wire = dedup.compact_request(text)['text']
        obj = json.loads(wire)
        for key in (META,):
            damaged = deepcopy(obj)
            damaged[key] = None
            with self.assertRaises(ValueError):
                dedup.restore_request(canonical(damaged), expected_sha256=sha(text))
        damaged = deepcopy(obj)
        damaged['supplementary_evidence']['supporting_run_files_outside_customer_payload'][0]['content'] = {
            SPLICE: {'corrupt': True}}
        with self.assertRaises(ValueError):
            dedup.restore_request(canonical(damaged), expected_sha256=sha(text))

    def test_malformed_wire_supplementary_or_splice_types_reject(self):
        _, text, _, _ = materials()
        wire = dedup.compact_request(text)['text']
        for invalid in (None, [], 'wrong', 1, True):
            with self.subTest(field='wire_supplementary', invalid=invalid):
                damaged = json.loads(wire)
                damaged['supplementary_evidence'] = invalid
                with self.assertRaises(ValueError):
                    dedup.restore_request(canonical(damaged), expected_sha256=sha(text))
            with self.subTest(field='wire_splice', invalid=invalid):
                damaged = json.loads(wire)
                damaged['supplementary_evidence']['supporting_run_files_outside_customer_payload'][0]['content'] = invalid
                with self.assertRaises(ValueError):
                    dedup.restore_request(canonical(damaged), expected_sha256=sha(text))

    def test_reference_ranges_digests_encoders_and_target_paths_are_bound(self):
        _, text, _, _ = materials()
        wire = dedup.compact_request(text)['text']

        def find_reference(value):
            if isinstance(value, dict):
                if 'reference' in value and 'ensure_ascii' in value:
                    return value
                for child in value.values():
                    found = find_reference(child)
                    if found is not None:
                        return found
            elif isinstance(value, list):
                for child in value:
                    found = find_reference(child)
                    if found is not None:
                        return found
            return None

        mutations = {
            'start_shift': lambda p: p['reference'].__setitem__('start_char', p['reference']['start_char'] + 1),
            'end_shift': lambda p: p['reference'].__setitem__('end_char', p['reference']['end_char'] + 1),
            'negative_range': lambda p: p['reference'].__setitem__('start_char', -1),
            'boolean_range': lambda p: p['reference'].__setitem__('start_char', True),
            'range_unit': lambda p: p['reference'].__setitem__('range_unit', 'utf8-bytes'),
            'source_document': lambda p: p['reference'].__setitem__('document', '来源与合规说明.md'),
            'source_document_type': lambda p: p['reference'].__setitem__('document', []),
            'document_hash': lambda p: p['reference'].__setitem__('document_sha256', '0' * 64),
            'content_hash': lambda p: p['reference'].__setitem__('text_sha256', '0' * 64),
            'content_id': lambda p: p['reference'].__setitem__('content_id', 'sha256:' + '0' * 64),
            'encoder_type': lambda p: p.__setitem__('ensure_ascii', 0),
            'encoder_choice': lambda p: p.__setitem__('ensure_ascii', not p['ensure_ascii']),
            'target_path': lambda p: p.__setitem__('json_value_pointer', '/prompt_stages/0/stages/narrative/prompt'),
            'lexeme_hash': lambda p: p.__setitem__('original_lexeme_sha256', '0' * 64),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                damaged = json.loads(wire)
                reference = find_reference(damaged)
                self.assertIsNotNone(reference)
                mutate(reference)
                with self.assertRaises(ValueError):
                    dedup.restore_request(canonical(damaged), expected_sha256=sha(text))

    def test_minimum_length_is_explicit_and_invalid_thresholds_reject(self):
        _, text, _, _ = materials()
        for minimum in (True, 0, 255, -1, '4096', None):
            with self.subTest(minimum=minimum):
                with self.assertRaises((TypeError, ValueError)):
                    dedup.compact_request(text, min_chars=minimum)
        self.assertEqual(dedup.compact_request(text, min_chars=256)['metrics']['replacement_count'], 1)
        self.assertEqual(dedup.compact_request(text, min_chars=len(text) + 1)['metrics']['replacement_count'], 0)

    def test_build_request_preserves_exact_original_schema_and_input_materials(self):
        value, original_text, schema, _ = materials()
        before = deepcopy(value)
        wire, actual_schema = dedup.build_request(value)
        self.assertEqual(actual_schema, schema)
        self.assertEqual(dedup.restore_request(wire, expected_sha256=sha(original_text)), original_text)
        self.assertEqual(json.loads(wire)['documents'], value['documents'])
        self.assertEqual(value, before)


if __name__ == '__main__':
    unittest.main()
