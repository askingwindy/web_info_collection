"""A real failure pattern: numeric punctuation is not a sentence ending."""
import unittest
from webcollect.collect import observed_excerpt

class NumericSentenceBoundary(unittest.TestCase):
    def test_coordinates_and_decimal_height_remain_one_observed_sentence(self):
        sentence='墓地位置东经118。 30分52秒，北纬31。29分35秒，海拔12。8米。'
        self.assertEqual(observed_excerpt(sentence+'下一句另述保护级别。'),sentence)
        self.assertEqual(observed_excerpt('否。'+sentence+'另一句。'),'否。'+sentence)
        self.assertEqual(observed_excerpt('仅有坐标118。30分，没有完整句号'),'仅有坐标118。30分，没有完整句号')
        self.assertEqual(observed_excerpt('第一句内容完整。第二句。'),'第一句内容完整。')

if __name__=='__main__':unittest.main()
