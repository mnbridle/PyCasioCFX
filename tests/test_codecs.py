import unittest
from helpers import cfx_codecs
from construct import Container


class TestCfxCodecs(unittest.TestCase):

    def test_sign_info_byte(self):

        parsed_signinfobyte = cfx_codecs.signinfobyte.parse(b'\x80')
        self.assertEqual(parsed_signinfobyte["isComplex"], True)
        self.assertEqual(parsed_signinfobyte["isNegative"], False)
        self.assertEqual(parsed_signinfobyte["expSignIsPositive"], False)

        parsed_signinfobyte = cfx_codecs.signinfobyte.parse(b'\x50')
        self.assertEqual(parsed_signinfobyte["isComplex"], False)
        self.assertEqual(parsed_signinfobyte["isNegative"], True)
        self.assertEqual(parsed_signinfobyte["expSignIsPositive"], False)

        parsed_signinfobyte = cfx_codecs.signinfobyte.parse(b'\x81')
        self.assertEqual(parsed_signinfobyte["isComplex"], True)
        self.assertEqual(parsed_signinfobyte["isNegative"], False)
        self.assertEqual(parsed_signinfobyte["expSignIsPositive"], True)

    def test_real_value_packet(self):
        pkt = b':\x00\x00\x00\x00\x01\x01#Eg\x89\x01#\x01B'
        decoded_pkt = Container(row=b'\x00', col=b'\x00', real_int=b'\x01', real_frac=b'\x01#Eg\x89\x01#',
                                real_signinfo=Container(isComplex=False, isNegative=False,
                                                        expSignIsPositive=True), real_exponent=b'B'
                                )

        self.assertEqual(cfx_codecs.real_value_packet.parse(pkt), decoded_pkt)

    def test_complex_value_packet(self):
        pkt = b':\x00\x00\x00\x00\x01\x01#Eg\x89\x01#\x81\x05\x01\x01#Eg\x89\x01#\x81\x05'
        decoded_pkt = Container(row=b'\x00', col=b'\x00',
                                real_int=b'\x01', real_frac=b'\x01#Eg\x89\x01#',
                                real_signinfo=Container(
                                    isComplex=True,
                                    isNegative=False,
                                    expSignIsPositive=True
                                ), real_exponent=b'\x05',
                                imag_int=b'\x01', imag_frac=b'\x01#Eg\x89\x01#',
                                imag_signinfo=Container(
                                    isComplex=True,
                                    isNegative=False,
                                    expSignIsPositive=True
                                ), imag_exponent=b'\x05')

        self.assertEqual(decoded_pkt, cfx_codecs.complex_value_packet.parse(pkt))

    def test_variable_description_packet(self):
        pkt = b':VAL\x00VM\x00\x01\x00\x01A\xff\xff\xff\xff\xff\xff\xffVariableC\n\xff\xff\xff' \
              b'\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff'
        decoded_pkt = Container(requested_variable_type='VARIABLE',
                                rowsize=b'\x01',
                                colsize=b'\x01',
                                variable_name=b"A\xFF\xFF\xFF\xFF\xFF\xFF\xFF",
                                real_or_complex='COMPLEX')

        self.assertEqual(decoded_pkt, cfx_codecs.variable_description_packet.parse(pkt))

    def test_request_packet(self):
        pkt = b':REQ\x00VM\xff\xff\xff\xffA\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff' \
              b'\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff'
        decoded_pkt = Container(
            requested_variable_type='VARIABLE',
            variable_name=b'A\xFF\xFF\xFF\xFF\xFF\xFF\xFF',
        )

        self.assertEqual(decoded_pkt, cfx_codecs.request_packet.parse(pkt))

    def test_end_packet(self):
        pkt = b':END\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff' \
              b'\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff'
        decoded_pkt = Container(tag=b'END')

        self.assertEqual(decoded_pkt, cfx_codecs.end_packet.parse(pkt))


if __name__ == '__main__':
    unittest.main()
