import app
import unittest


class TestHelloWorld(unittest.TestCase):

    def setUp(self):
        self.app = app.app.test_client()
        self.app.testing = True

    def test_status_code(self):
        response = self.app.get('/sample/nyc_lot/test123')
        self.assertEqual(response.status_code, 200)

    def test_message(self):
        response = self.app.get('/sample/nyc_lot/test123')

        assert b'error' not in response.data


if __name__ == '__main__':
    unittest.main()