import unittest

import app


class FakeCursor:
    def __init__(self, db=None, rows=None):
        self.db = db
        self.rows = list(rows or [])
        self._index = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def execute(self, *args, **kwargs):
        self._index = 0
        if not args:
            self.rows = []
            return

        query = args[0]
        params = args[1] if len(args) > 1 else []

        if ('WHERE id = %s' in query or 'WHERE products.id = %s' in query) and params:
            product_id = str(params[0])
            matching_row = next(
                (row for row in self.db.rows if str(row.get('id')) == product_id),
                self.db.rows[0] if self.db.rows else {}
            )
            self.rows = [matching_row]
            return

        if 'SELECT * FROM products' in query or 'SELECT products.*' in query:
            self.rows = list(self.db.rows)
            return

        self.rows = list(self.db.rows)

    def fetchone(self):
        if not self.rows or self._index >= len(self.rows):
            return None
        row = self.rows[self._index]
        self._index += 1
        return row

    def fetchall(self):
        rows = list(self.rows)
        self._index = len(rows)
        return rows

    @property
    def rowcount(self):
        return len(self.rows)

    @property
    def lastrowid(self):
        return 1


class FakeDB:
    def __init__(self, rows=None):
        self.rows = []
        for index, row in enumerate(rows or [], start=1):
            normalized = dict(row)
            normalized.setdefault('id', index)
            self.rows.append(normalized)

    def cursor(self):
        return FakeCursor(self, self.rows)

    def close(self):
        pass


class UserLoginFlowTests(unittest.TestCase):
    def setUp(self):
        app.app.config['TESTING'] = True
        app.app.config['SECRET_KEY'] = 'test-secret'
        self.client = app.app.test_client()

    def test_login_redirects_user_to_cart_after_success(self):
        user_rows = [{
            'id': 1,
            'name': 'John',
            'email': '9876543210@users.local',
            'phone': '+919876543210',
            'password_hash': 'x',
        }]

        app.get_db_connection = lambda: FakeDB(user_rows)

        with self.client.session_transaction() as sess:
            sess['cart'] = {'1': 2}

        response = self.client.post('/login', data={'name': 'John', 'phone': '9876543210'}, follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/cart')

    def test_cart_summary_returns_quantity_and_total(self):
        app.get_db_connection = lambda: FakeDB([
            {'id': 1, 'actual_price': 200, 'discount_price': 200, 'category_name': 'Crackers'},
            {'id': 2, 'actual_price': 300, 'discount_price': 300, 'category_name': 'Crackers'},
        ])

        with app.app.test_request_context('/'):
            app.session.clear()
            app.session['cart'] = {'1': 2, '2': 1}
            summary = app.get_cart_summary()

        self.assertEqual(summary['count'], 3)
        self.assertEqual(summary['total'], 140)

    def test_admin_dashboard_uses_same_catalog_data_as_products_page(self):
        products = [
            {'id': 1, 'name': 'Firecrackers A', 'discount_price': 100, 'actual_price': 120, 'category_id': 2, 'brand_id': 3, 'category_name': 'Crackers'},
            {'id': 2, 'name': 'Firecrackers B', 'discount_price': 220, 'actual_price': 260, 'category_id': 2, 'brand_id': 3, 'category_name': 'Crackers'},
        ]

        db = FakeDB(products)
        cursor = FakeCursor(db, products)
        catalog = app.get_catalog_products(cursor)

        self.assertEqual(len(catalog), 2)
        self.assertEqual(catalog[0]['name'], 'Firecrackers A')
        self.assertEqual(catalog[0]['discount_price'], 24)
        self.assertEqual(catalog[1]['discount_price'], 52)

    def test_admin_access_allows_phone_match_when_email_is_null(self):
        app.app.config['ADMIN_EMAIL'] = ''
        app.app.config['ADMIN_PHONE'] = '+919876543210'
        app.get_db_connection = lambda: FakeDB([{
            'id': 1,
            'email': None,
            'phone': '+919876543210',
        }])

        with app.app.test_request_context('/'):
            app.session['logged_in'] = True
            app.session['user_id'] = 1
            result = app.require_admin()

        self.assertIsNone(result)

    def test_blank_admin_email_does_not_grant_client_admin_access(self):
        app.app.config['ADMIN_EMAIL'] = ''
        app.app.config['ADMIN_PHONE'] = ''
        app.get_db_connection = lambda: FakeDB([{
            'id': 1,
            'email': None,
            'phone': '+919876543210',
        }])

        with app.app.test_request_context('/'):
            app.session['logged_in'] = True
            app.session['user_id'] = 1
            result = app.require_admin()

        self.assertEqual(result.status_code, 302)
        self.assertEqual(result.location, '/')

    def test_image_resolver_uses_uploads_for_category_and_product_names(self):
        image_paths = [
            'uploads/sound crackers.jpg',
            'uploads/flower pot.jpg',
            'uploads/chakkras.jpg',
            'uploads/garland.jpg',
            'uploads/bomb.jpg',
            'uploads/rockets.jpg',
            'uploads/twinkling.jpg',
            'uploads/multishot.jpg',
            'uploads/whistling crackers.jpg',
            'uploads/10 cm Electric Sparklers.jpg',
            'uploads/unicorn_15items.jpeg',
        ]

        self.assertEqual(app.resolve_image_for_name('Ground Chakkar', image_paths), 'uploads/chakkras.jpg')
        self.assertEqual(app.resolve_image_for_name('Bombs', image_paths), 'uploads/bomb.jpg')
        self.assertEqual(app.resolve_image_for_name('4" Gold Lakshmi', image_paths), "uploads/4' gold lakshmi.jpg")

    def test_parse_estimate_items_extracts_full_receipt_details(self):
        estimate_text = """🚨 *Shantini Crackers Estimate Inquiry*
👤 *Customer:* John
📞 *Phone:* +919876543210
------------------------------------
• Ground Chakkar x 2 = ₹240.00
• Fancy Rocket x 1 = ₹180.00
------------------------------------
💰 *Total Estimated Value:* ₹420.00"""

        items, total = app.parse_estimate_items(estimate_text)

        self.assertEqual(total, 420.0)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['name'], 'Ground Chakkar')
        self.assertEqual(items[0]['quantity'], 2)
        self.assertEqual(items[0]['unit_price'], 120.0)
        self.assertEqual(items[1]['subtotal'], 180.0)


if __name__ == '__main__':
    unittest.main()
