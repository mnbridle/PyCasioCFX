import unittest


class TestCfxCodecs(unittest.TestCase):

    def test_real_value_packet(self):
        print("Foo")
        self.assertEqual('foo', 'foo')


if __name__ == '__main__':
    unittest.main()
