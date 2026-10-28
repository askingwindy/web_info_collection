"""Explicit-set accounting and exact-recall search; synthetic fixtures only."""
import copy
import csv
import json
import random
import shutil
import unittest

import test_delivery
from quality_inspector.cumulative import build_set_manifest, inspect_set
from quality_inspector.duplicates import analyze, exhaustive_routes, hamming_candidates, indexed_routes


class CumulativeTests(unittest.TestCase):
    setUp=test_delivery.DeliveryContractTests.setUp
    tearDown=test_delivery.DeliveryContractTests.tearDown
    seal=test_delivery.DeliveryContractTests.seal

    def test_complete_mechanical_set_never_claims_release_or_review(self):
        manifest=build_set_manifest([self.client]);before=copy.deepcopy(manifest)
        result=inspect_set(manifest,self.profile,verify_exhaustive=True)
        self.assertEqual(result['mechanical_status'],'PASS')
        self.assertFalse(result['release_ready'])
        self.assertEqual(result['semantic_review_status'],'NOT_EVALUATED')
        self.assertEqual(result['customer_actual_acceptance'],'UNKNOWN')
        self.assertEqual(manifest,before)
        self.assertEqual(result['duplicates']['search']['exhaustive_verification']['status'],'PASS')

    def test_manifest_is_invalidated_by_changed_package_bytes(self):
        manifest=build_set_manifest([self.client]);(self.client/'README.md').write_text('Changed after freezing')
        result=inspect_set(manifest,self.profile)
        self.assertEqual(result['mechanical_status'],'FAIL')
        self.assertTrue(any('frozen package hash' in row['reason'] for row in result['errors']))

    def test_cross_package_identical_copy_is_explicit_and_counted_once(self):
        other=self.root/'other';shutil.copytree(self.client,other)
        result=inspect_set(build_set_manifest([self.client,other]),self.profile)
        self.assertEqual(result['mechanical_status'],'PASS')
        self.assertEqual(result['sample_count'],1)
        self.assertEqual(len(result['version_comparison']['identical_copies']),1)

    def test_duplicate_and_nested_package_roots_rejected(self):
        with self.assertRaises(ValueError):build_set_manifest([self.client,self.client])
        with self.assertRaises(ValueError):build_set_manifest([self.client,self.client/'samples'])

    def test_cache_cannot_write_into_actual_package(self):
        with self.assertRaises(ValueError):inspect_set(build_set_manifest([self.client]),self.profile,cache=self.client/'cache.json')

    def test_profile_targets_apply_to_cumulative_actual_count(self):
        value=json.loads(self.profile.read_text());value['targets']['expected_samples']=1000
        value['internal_targets']={'minimum_registered_uris':20,'enforced_as_customer_contract':False}
        self.profile.write_text(json.dumps(value))
        result=inspect_set(build_set_manifest([self.client]),self.profile)
        self.assertEqual(result['mechanical_status'],'FAIL')
        self.assertTrue(any('Expected 1000 samples' in row['reason'] for row in result['errors']))
        self.assertFalse(result['internal_targets_enforced_as_customer_contract'])

    def test_internal_twenty_uri_target_is_information_not_contract_gate(self):
        value=json.loads(self.profile.read_text())
        value['internal_targets']={'minimum_registered_uris':20,'enforced_as_customer_contract':False}
        self.profile.write_text(json.dumps(value))
        result=inspect_set(build_set_manifest([self.client]),self.profile)
        self.assertEqual(result['mechanical_status'],'PASS')
        self.assertEqual(result['site_count'],1)
        self.assertFalse(result['internal_targets_enforced_as_customer_contract'])

    def test_same_count_metadata_missing_id_and_duplicate_replacement_fail(self):
        from quality_inspector.checksums import write_manifest
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                _,client,_=test_delivery.fixture(self.root/('two' if duplicate else 'one'),count=2)
                path=client/'metadata.csv'
                with path.open(newline='') as stream:
                    reader=csv.DictReader(stream);fields=reader.fieldnames;rows=list(reader)
                rows[1]['sample_id']=rows[0]['sample_id'] if duplicate else 'MISSING_REPLACEMENT'
                with path.open('w',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
                (client/'SHA256SUMS').unlink();write_manifest(client)
                result=inspect_set(build_set_manifest([client]),self.profile)
                self.assertEqual(result['sample_count'],len(rows))
                self.assertEqual(result['mechanical_status'],'FAIL')
                self.assertTrue(any('metadata IDs must cover' in row['reason'] for row in result['errors']))

    def test_unused_declared_site_cannot_meet_actual_site_count(self):
        path=self.client/'site-list.json';listing=json.loads(path.read_text())
        listing['sites'].append({'site_id':'UNUSED','uri':'https://unused.example.org/',
                                 'site_category':'学习教育','sample_ids':[]})
        path.write_text(json.dumps(listing));self.seal()
        result=inspect_set(build_set_manifest([self.client]),self.profile)
        self.assertEqual(result['site_count'],1)

    def test_cache_cannot_overwrite_manifest_or_profile(self):
        manifest=self.root/'set.json';manifest.write_text(json.dumps(build_set_manifest([self.client])))
        for path in (manifest,self.profile):
            before=path.read_bytes()
            with self.assertRaises(ValueError):inspect_set(manifest,self.profile,cache=path)
            self.assertEqual(path.read_bytes(),before)

    def test_cache_reuse_and_raw_verification_detect_corruption(self):
        cache=self.root/'cache.json';first=analyze(self.client,cache=cache,verify_exhaustive=True)
        self.assertEqual(first['search']['exhaustive_verification']['status'],'PASS')
        second=analyze(self.client,cache=cache,verify_exhaustive=False)
        self.assertEqual(second['search']['cache_hits'],1)
        value=json.loads(cache.read_text());next(iter(value['records'].values()))['first_dhash']^=255
        cache.write_text(json.dumps(value));third=analyze(self.client,cache=cache,verify_exhaustive=True)
        self.assertEqual(third['search']['exhaustive_verification']['status'],'FAIL')
        self.assertEqual(len(third['search']['exhaustive_verification']['cache_fingerprint_mismatches']),1)

    def test_changed_image_bytes_do_not_reuse_old_fingerprint(self):
        from PIL import Image
        cache=self.root/'cache.json';analyze(self.client,cache=cache,verify_exhaustive=False)
        image=next(self.client.glob('samples/*/images/step_001.png'));Image.new('RGB',(100,80),'red').save(image)
        result=analyze(self.client,cache=cache,verify_exhaustive=False)
        self.assertEqual(result['search']['cache_hits'],0)


class CompleteRecallTests(unittest.TestCase):
    def test_radius_boundaries_in_each_bit_block_are_never_missed(self):
        for radius in (3,4):
            values=[0]
            for count in range(radius+2):
                for offset in range(64):values.append(sum(1<<((offset+bit*13)%64) for bit in range(count)))
            candidates=hamming_candidates(values,radius)
            expected={(a,b) for a in range(len(values)) for b in range(a+1,len(values)) if (values[a]^values[b]).bit_count()<=radius}
            self.assertFalse(expected-candidates)
            filtered={(a,b) for a,b in candidates if (values[a]^values[b]).bit_count()<=radius}
            self.assertEqual(filtered,expected)

    def test_thousand_fingerprint_index_matches_499500_pair_oracle(self):
        rng=random.Random(20261025)
        rows=[{'sequence':[('click',str(i),'合成页面')], 'first_dhash':rng.getrandbits(64),
               'last_dhash':rng.getrandbits(64),'instruction_simhash':rng.getrandbits(64)} for i in range(1000)]
        for index in range(1,20):
            rows[index]['first_dhash']=rows[0]['first_dhash']^((1<<(index%6))-1)
            rows[index]['last_dhash']=rows[0]['last_dhash']^((1<<((index+1)%6))-1)
            rows[index]['instruction_simhash']=rows[0]['instruction_simhash']^((1<<(index%5))-1)
        rows[2]['sequence']=copy.deepcopy(rows[0]['sequence'])
        actual,_=indexed_routes(rows);expected=exhaustive_routes(rows)
        self.assertEqual(actual,expected)
        self.assertEqual(len(rows)*(len(rows)-1)//2,499500)
        self.assertIn((0,2),actual['route2'])


if __name__=='__main__':unittest.main()
