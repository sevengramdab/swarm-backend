... def test_get_user():
  response = client.get('/users/1')
  self.assertEqual(response.status_code, 200)
  self.assertIn('user_data', response.json())