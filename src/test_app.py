import app
import unittest


class test_api(unittest.TestCase):

    def setUp(self):
        self.app = app.app.test_client()
        self.app.testing = True

    def tearDown(self):
        pass

    def test_sample_status_code(self):
        response = self.app.get('/decrypt/35cfe69780d1c5ada3ee5c5bda24c035/QmNZrXDhjs9eWaFijkVydT5NAqz4SosSGLv2AN9HoQzrbG')
        self.assertEqual(response.status_code, 200)

    def test_search_status_code(self):
        response = self.app.get('/search?terms=tax')
        self.assertEqual(response.status_code, 200)



if __name__ == '__main__':
    unittest.main()