import unittest
from helpers import packet_helpers, cfx_codecs
from construct import Container


class TestCfxCodecs(unittest.TestCase):
    def test_checksum_valid(self):

        pkt = cfx_codecs.request_packet.build(Container(requested_variable_type='VARIABLE',
                                                        variable_name=b'A\xFF\xFF\xFF\xFF\xFF\xFF\xFF'))
        pkt = packet_helpers.calculate_checksum(pkt)
        self.assertTrue(len(pkt), 50)
        self.assertTrue(packet_helpers.checksum_valid(pkt))

