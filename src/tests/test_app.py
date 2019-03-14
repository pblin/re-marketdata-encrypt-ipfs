import app
import unittest


class test_api(unittest.TestCase):

    def setUp(self):
        self.app = app.app.test_client()
        self.app.testing = True

    def test_sample_status_code(self):
        assert self.app.get('/sample/nyc_lot/test123').status_code == 200

    def test_search_status_code(self):
        assert self.app.get('/search?terms=tax').status_code == 200



if __name__ == '__main__':
    unittest.main()