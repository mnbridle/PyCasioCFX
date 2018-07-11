import unittest
from helpers import cfx_codecs


class TestCfxCodecs(unittest.TestCase):

    def test_sign_info_byte(self):

        parsed_signinfobyte = cfx_codecs.signinfobyte.parse(b'\x80')
        self.assertEqual(parsed_signinfobyte["isImaginary"], True)
        self.assertEqual(parsed_signinfobyte["isNegative"], False)
        self.assertEqual(parsed_signinfobyte["signIsPositive"], False)

        parsed_signinfobyte = cfx_codecs.signinfobyte.parse(b'\x40')
        self.assertEqual(parsed_signinfobyte["isImaginary"], False)
        self.assertEqual(parsed_signinfobyte["isNegative"], True)
        self.assertEqual(parsed_signinfobyte["signIsPositive"], False)

        parsed_signinfobyte = cfx_codecs.signinfobyte.parse(b'\x81')
        self.assertEqual(parsed_signinfobyte["isImaginary"], True)
        self.assertEqual(parsed_signinfobyte["isNegative"], False)
        self.assertEqual(parsed_signinfobyte["signIsPositive"], True)


if __name__ == '__main__':
    unittest.main()
