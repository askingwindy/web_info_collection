"""Completion prose uses observed readouts, including old empty button values."""
from copy import deepcopy
import unittest
from webcollect.collect import assert_state,completion_from_assertions


class AssertionNarratives(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_loan_results_and_button_mode_keep_actual_values(self):
        conditions=[];targets=[]
        for selector,text in [('#monthlyPayment','10165.98 元'),('#totalPayment','121991.73 元'),
                              ('#totalInterest','1991.73 元'),('#mode','商业贷款')]:
            condition={'selector':selector,'contains':text};conditions.append(condition)
            targets.append({'selector':selector,'index':0,'visible':True,'text':text,'target_text':text,
                            'value':None,'value_visible':False,'display_value':'' if selector=='#mode' else None})
        observed={'url':'https://www.jyshare.com/front-end/9986/','assertion_targets':targets}
        assertions=await assert_state(None,conditions,observed)
        self.assertTrue(all('display_actual' not in row for row in assertions))
        narration=completion_from_assertions(assertions)
        for text in ('10165.98 元','121991.73 元','1991.73 元','商业贷款'):self.assertIn(text,narration)
        self.assertNotIn('「」',narration)
        old=deepcopy(assertions);old[-1]['display_actual']=''
        self.assertEqual(completion_from_assertions(old),narration)

    async def test_actual_loan_result_mismatch_cannot_be_filled_from_expected(self):
        condition={'selector':'#monthlyPayment','contains':'10165.98 元'}
        for actual in ('','9999.99 元','不可读'):
            target={'selector':'#monthlyPayment','index':0,'visible':True,'text':actual,'target_text':actual,
                    'value':None,'value_visible':False,'display_value':''}
            with self.assertRaises(ValueError):await assert_state(None,[condition],{'assertion_targets':[target]})
        for actual in ('',None,'   '):
            with self.assertRaises(ValueError):completion_from_assertions([
                {'expected':{'selector':'#result','number':10165.98},'actual':actual,'display_actual':'','passed':True}])

    async def test_select_display_requires_observed_visible_value(self):
        condition={'selector':'#repaymentType','value':'equalPayment'}
        target={'selector':'#repaymentType','index':0,'visible':True,'text':'','target_text':'还款方式',
                'value':'equalPayment','value_visible':True,'display_value':'等额本息'}
        rows=await assert_state(None,[condition],{'assertion_targets':[target]})
        self.assertIn('等额本息',completion_from_assertions(rows))
        target['value_visible']=False
        with self.assertRaises(ValueError):await assert_state(None,[condition],{'assertion_targets':[target]})

    async def test_matrix_narration_comes_from_actual_rows_and_rejects_changed_text(self):
        from webcollect.html_table_strategy import TABLE_SELECTOR,EXPECTED_MATRIX
        row={'expected':{'selector':TABLE_SELECTOR,'html_table_matrix':EXPECTED_MATRIX},
             'actual':deepcopy(EXPECTED_MATRIX),'passed':True}
        text=completion_from_assertions([row]);self.assertIn('2行2列表格',text);self.assertIn('「苹果」',text)
        row['actual'][1][1]='13'
        with self.assertRaises(ValueError):completion_from_assertions([row])


if __name__=='__main__':unittest.main()
