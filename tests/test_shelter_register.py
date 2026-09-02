import unittest

from app import app, shelters


class ShelterRegisterTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session['logged_in'] = True

        self.original_shelters = shelters[:]
        shelters[:] = [{"id": 1, "name": "既存避難所"}]

    def tearDown(self):
        shelters[:] = self.original_shelters

    def test_register_shelter_name(self):
        response = self.client.post('/shelter_register', data={'name': '新しい避難所'})
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('避難所名を登録しました。', page)
        self.assertTrue(any(item.get('name') == '新しい避難所' for item in shelters))


if __name__ == '__main__':
    unittest.main()
