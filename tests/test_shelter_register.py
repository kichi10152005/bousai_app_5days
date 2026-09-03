import unittest

from app import app, distance_from_city_hall, shelters


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

    def test_library_has_distance_and_map_popup_label(self):
        library = {
            'id': 5,
            'name': '青森市立図書館',
            'city': '青森市',
            'address': '青森県青森市新町1-3-7',
            'latitude': 40.8271913,
            'longitude': 140.7358986,
        }
        shelters[:] = [library]
        expected_distance = distance_from_city_hall(library)
        response = self.client.get('/search_results?name=青森市立図書館')
        page = response.get_data(as_text=True)

        self.assertIsNotNone(expected_distance)
        self.assertIn('青森市役所からの距離', page)
        self.assertIn(f'{expected_distance}m', page)
        self.assertIn('青森市立図書館', page)


if __name__ == '__main__':
    unittest.main()
