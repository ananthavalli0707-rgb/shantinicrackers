import os
import re
import smtplib
from datetime import datetime
from difflib import SequenceMatcher
from email.message import EmailMessage
from io import BytesIO
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
import pymysql
import pymysql.cursors
from werkzeug.security import generate_password_hash, check_password_hash
import urllib.parse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from config import Config

app = Flask(__name__, static_folder=os.path.join('templates', 'static'))
app.config.from_object(Config)


@app.context_processor
def inject_config():
    return {
        'config': app.config,
        'cart_summary': get_cart_summary(),
        'nav_categories': get_navigation_categories(),
    }


def get_navigation_categories():
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT id, name, image_url FROM categories ORDER BY id")
            return cursor.fetchall()
    finally:
        db.close()


def is_gift_box_category(category_name):
    return str(category_name or '').strip().lower() == 'gift box'


def get_effective_discount_price(actual_price=None, category_name=None, stored_price=None):
    base_value = actual_price if actual_price not in (None, '', 0) else (stored_price if stored_price not in (None, '', 0) else 0)
    try:
        base = float(base_value)
    except (TypeError, ValueError):
        return 0

    if is_gift_box_category(category_name):
        return int(round(float(stored_price if stored_price not in (None, '', 0) else base)))
    return int(round(base * 0.2))


def normalize_product_display_price(product):
    if not product:
        return product

    category_name = product.get('category_name') or product.get('category') or ''
    actual_price = product.get('actual_price', 0)
    stored_price = product.get('discount_price', 0)
    product['discount_price'] = get_effective_discount_price(actual_price, category_name, stored_price)
    return product


def get_cart_summary():
    cart = session.get('cart', {})
    if not cart:
        return {'count': 0, 'total': 0}

    total_count = 0
    total_amount = 0
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            for product_id, quantity in cart.items():
                try:
                    qty = int(quantity)
                except (TypeError, ValueError):
                    continue
                if qty <= 0:
                    continue
                total_count += qty
                cursor.execute("""
                    SELECT products.*, categories.name AS category_name
                    FROM products
                    LEFT JOIN categories ON categories.id = products.category_id
                    WHERE products.id = %s
                """, [product_id])
                product = cursor.fetchone()
                if product:
                    normalized = normalize_product_display_price(product)
                    total_amount += int(normalized.get('discount_price', 0) or 0) * qty
    finally:
        db.close()

    return {'count': total_count, 'total': total_amount}

# --- NATIVE PYMYSQL CONNECTION CONFIGURATION ---
def get_db_connection():
    return pymysql.connect(
        host=app.config.get('MYSQL_HOST', 'localhost'),
        user=app.config.get('MYSQL_USER', 'root'),
        password=app.config.get('MYSQL_PASSWORD', ''),
        database=app.config.get('MYSQL_DB', 'fireworks_db'),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True # Automatically commits data insert/update statements
    )


def parse_estimate_items(estimate_text):
    items = []
    total = 0.0

    for raw_line in estimate_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        item_match = re.search(r"[•\-*]?\s*(.+?)\s*x\s*(\d+)\s*=\s*₹?\s*([0-9,]+(?:\.\d+)?)", line, flags=re.IGNORECASE)
        if item_match:
            name = item_match.group(1).strip().strip('*').strip('•').strip('-')
            quantity = int(item_match.group(2))
            subtotal = float(item_match.group(3).replace(',', ''))
            unit_price = subtotal / quantity if quantity else 0.0
            items.append({
                'name': name,
                'quantity': quantity,
                'unit_price': unit_price,
                'subtotal': subtotal,
            })
            continue

        total_match = re.search(r"(?:Total Estimated Value|Total).*?₹?\s*([0-9,]+(?:\.\d+)?)", line, flags=re.IGNORECASE)
        if total_match:
            total = float(total_match.group(1).replace(',', ''))

    return items, total


def generate_estimate_pdf(customer_name, estimate_text):
    safe_name = re.sub(r'[^a-zA-Z0-9._-]+', '_', customer_name).strip('_') or 'customer'
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    pdf_dir = os.path.join(app.root_path, 'downloads', 'estimates')
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, f'{safe_name}-{timestamp}-estimate.pdf')

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph('Shantini Crackers', styles['Title']))
    story.append(Paragraph(f'Estimate for {customer_name}', styles['Heading2']))
    story.append(Spacer(1, 12))

    customer_details = []
    for line in estimate_text.splitlines():
        value = line.strip()
        if value and any(prefix in value for prefix in ['👤', '📞', '✉️', 'Customer:', 'Phone:', 'Email:']):
            customer_details.append(value)

    for detail in customer_details[:3]:
        story.append(Paragraph(detail.replace('&', '&amp;'), styles['BodyText']))

    story.append(Spacer(1, 12))

    items, total = parse_estimate_items(estimate_text)
    table_data = [['Product', 'Qty', 'Unit Price', 'Subtotal']]
    for item in items:
        table_data.append([
            item['name'],
            str(item['quantity']),
            f"₹{item['unit_price']:.2f}",
            f"₹{item['subtotal']:.2f}",
        ])

    if items:
        table_data.append(['Total', '', '', f'₹{total or sum(item["subtotal"] for item in items):.2f}'])

    table = Table(table_data, colWidths=[180, 40, 90, 95])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1d3557')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.whitesmoke, colors.white]),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    story.append(table)

    if not items:
        for line in estimate_text.splitlines():
            if line.strip():
                story.append(Paragraph(line.replace('&', '&amp;'), styles['BodyText']))

    story.append(Spacer(1, 20))
    story.append(Paragraph('Thank you for choosing Shantini Crackers.', styles['BodyText']))
    doc.build(story)

    pdf_data = buffer.getvalue()
    with open(pdf_path, 'wb') as pdf_file:
        pdf_file.write(pdf_data)

    return pdf_data, pdf_path


def send_estimate_email(recipient, customer_name, estimate_text):
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        return False

    pdf_data, pdf_path = generate_estimate_pdf(customer_name, estimate_text)

    message = EmailMessage()
    message['Subject'] = 'Your Shantini Crackers Estimate'
    message['From'] = app.config['MAIL_FROM']
    message['To'] = recipient
    message.set_content(
        f"Hello {customer_name},\n\nYour fireworks estimate is attached as a PDF.\n\nThank you,\nShantini Crackers"
    )
    message.add_attachment(
        pdf_data,
        maintype='application',
        subtype='pdf',
        filename=os.path.basename(pdf_path)
    )

    with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as smtp:
        if app.config['MAIL_USE_TLS']:
            smtp.starttls()
        smtp.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        smtp.send_message(message)

    return pdf_path


def require_admin():
    if not session.get('logged_in') or not session.get('user_id'):
        flash("Please log in to open the admin dashboard.", "warning")
        return redirect(url_for('login'))

    db = get_db_connection()
    with db.cursor() as cursor:
        cursor.execute("SELECT email, phone FROM users WHERE id = %s", [session['user_id']])
        user = cursor.fetchone()
    db.close()

    if not is_admin_user(user):
        flash("You do not have permission to access this page.", "danger")
        return redirect(url_for('index'))
    return None


def is_admin_user(user):
    if not user:
        return False

    user_email = (user.get('email') or '').strip().lower()
    user_phone = normalize_phone(user.get('phone') or '')
    admin_email = str(app.config.get('ADMIN_EMAIL') or '').strip().lower()
    admin_phone = normalize_phone(app.config.get('ADMIN_PHONE') or '')

    email_matches = bool(admin_email) and user_email == admin_email
    phone_matches = bool(admin_phone) and user_phone == admin_phone
    return email_matches or phone_matches


def normalize_phone(phone):
    return ''.join(character for character in str(phone) if character.isdigit())


def get_whatsapp_admin_phone():
    phone = normalize_phone(app.config.get('ADMIN_PHONE') or '917708971956')
    if len(phone) == 10:
        phone = '91' + phone
    return phone


def normalize_image_token(value):
    if value is None:
        return ''
    text = str(value).lower().replace('&', 'and')
    text = re.sub(r'[^a-z0-9]+', '', text)
    return text


def resolve_image_for_name(name, available_images, explicit_aliases=None):
    if not name:
        return None

    aliases = explicit_aliases if explicit_aliases is not None else {**CATEGORY_IMAGE_ALIASES, **PRODUCT_IMAGE_ALIASES}
    normalized_name = normalize_image_token(name)
    if not normalized_name:
        return None

    for key, value in aliases.items():
        normalized_key = normalize_image_token(key)
        if normalized_key == normalized_name:
            return value
        if normalized_name in normalized_key or normalized_key in normalized_name:
            return value

    best_match = None
    best_score = 0
    name_tokens = [token for token in re.split(r'[^a-z0-9]+', str(name).lower()) if token]

    for image_path in available_images:
        image_name = os.path.basename(image_path)
        normalized_image = normalize_image_token(image_name)
        image_tokens = [token for token in re.split(r'[^a-z0-9]+', image_name.lower()) if token]
        if not image_tokens:
            continue

        overlap = sum(1 for token in name_tokens if token in image_tokens)
        substring_bonus = sum(
            1 for token in name_tokens
            for image_token in image_tokens
            if token in image_token or image_token in token
        )
        fuzzy_score = SequenceMatcher(None, normalized_name, normalized_image).ratio()
        score = (overlap * 100) + (substring_bonus * 25) + (fuzzy_score * 10)

        if normalized_name == normalized_image or normalized_name in normalized_image or normalized_image in normalized_name:
            return image_path
        if score > best_score:
            best_match = image_path
            best_score = score

    return best_match if best_match is not None and best_score > 0 else (available_images[0] if available_images else None)


def ensure_existing_image(image_path, fallback_paths=None):
    fallback_paths = fallback_paths or []
    if not image_path:
        return fallback_paths[0] if fallback_paths else None

    full_path = os.path.join(app.static_folder, image_path.replace('/', os.sep))
    if os.path.isfile(full_path):
        return image_path

    for fallback in fallback_paths:
        fallback_full_path = os.path.join(app.static_folder, fallback.replace('/', os.sep))
        if os.path.isfile(fallback_full_path):
            return fallback

    return image_path


CATEGORY_IMAGE_ALIASES = {
    'sound crackers': 'uploads/sound crackers.jpg',
    'flower pots': 'uploads/flower pot.jpg',
    'ground chakkar': 'uploads/chakkras.jpg',
    'garlands': 'uploads/garland.jpg',
    'paper blast': 'uploads/paper blast.jpg',
    'bombs': 'uploads/bomb.jpg',
    'rockets': 'uploads/rockets.jpg',
    'twinkling stars': 'uploads/twinkling.jpg',
    'bijili crackers': 'uploads/bijili crackers.png',
    'fancy shots': 'uploads/multishot.jpg',
    'whistling crackers': 'uploads/whistling crackers.jpg',
    'fancy novelties': 'uploads/30 Shot Multicolor SkyShot.jpg',
    'sparklers': 'uploads/10 cm Electric Sparklers.jpg',
    'child crackers': 'uploads/unicorn_15items.jpeg',
    'color matches': 'uploads/WhatsApp Image 2026-08-21 at 10.57.43 PM.jpeg',
    'varieties': 'uploads/5 colour fountain.jpg',
    'gift box': 'uploads/unicorn_15items.jpeg',
    'fountain': 'uploads/shot.jpg',
    'multicolour sky shot': 'uploads/multishot.jpg',
}

PRODUCT_IMAGE_ALIASES = {
    '4" gold lakshmi': 'uploads/4\' gold lakshmi.jpg',
    '4" deluxe lakshmi': 'uploads/4-deluxe-lakshmi-cracker.jpg',
    '4" lakshmi': 'uploads/4\' lakshmi.jpg',
    '3½" lakshmi': 'uploads/3\' lakshmi.jpg',
    '2¾" kuruvi': 'uploads/2 kuruvi.jpg',
    '2 sound': 'uploads/2 sound.jpg',
    '5" lakshmi / lion': 'uploads/5 lakshmi.jpg',
    '6" warior / lakshmi': 'uploads/6 lakshmi.jpg',
    '1½" twinkling star': 'uploads/1 twinkling star.jfif',
    '4" twinkling star': 'uploads/4 inch twinkling star.jfif',
    'red bijili': 'uploads/red bijili.jfif',
    'stripped bijili': 'uploads/stripped bijili.jfif',
    'chotta fancy': 'uploads/chotta fancy.jfif',
    'penta fancy (5 pcs)': 'uploads/penta fancy.jfif',
    'whiztling rocket': 'uploads/whistling rocket.jfif',
    'siren': 'uploads/siren.jfif',
    'mini siren': 'uploads/mini siren.jfif',
    'whiztling wheel': 'uploads/whistling wheel.jfif',
    'bullet bomb': 'uploads/bullet.jfif',
    'atom bomb': 'uploads/atom.jfif',
    'hydro bomb': 'uploads/hydro.jfif',
    'king of king bomb': 'uploads/king of king.jfif',
    'classic bomb': 'uploads/classic.jfif',
    'agni bomb': 'uploads/agni.jfif',
    'digital bomb': 'uploads/digital.jfif',
    'baby rockets': 'uploads/baby rocket.jfif',
    'rocket bomb': 'uploads/rocket bomb.jfif',
}

HOME_CATEGORY_NAMES = [
    'Sound Crackers', 'Flower Pots', 'Ground Chakkar', 'Garlands',
    'Paper Blast', 'Bombs', 'Rockets', 'Twinkling Stars',
    'Bijili Crackers', 'Fancy Shots', 'Whistling Crackers',
    'Fancy Novelties', 'Sparklers', 'Child Crackers', 'Color Matches',
    'Varieties', 'Gift Box'
]

GIFT_BOX_IMAGE_PATHS = [
    'uploads/unicorn_15items.jpeg', 'uploads/unicorn_20items.jpeg',
    'uploads/unicorn_25items.jpeg', 'uploads/unicorn_30items.jpeg',
    'uploads/unicorn_35items.jpeg', 'uploads/unicorn_40items.jpeg',
    'uploads/unicorn_50items.jpeg', 'uploads/unicorn_60items.jpeg'
]

GIFT_BOX_PRODUCT_NAMES = [
    '15 Items (Milky Bar)', '20 Items (Croods / Moana)',
    '25 Items (Lion King / 5 Star)', '30 Items (Spiderman / Kit Kat)',
    '35 Items (Ice Age / Dairy Milk)', '40 Items (Venkatesh / Snickers)',
    '50 Items (Krishna / Avengers)', '60 Items (Mahabharata)'
]

def ensure_gift_box_images(cursor):
    cursor.executemany(
        """
        UPDATE products
        INNER JOIN categories ON categories.id = products.category_id
        SET products.image_url = %s
        WHERE categories.name = 'Gift Box' AND products.name = %s
        """,
        list(zip(GIFT_BOX_IMAGE_PATHS, GIFT_BOX_PRODUCT_NAMES))
    )


def get_catalog_products(cursor, category_id=None, include_only_in_stock=False):
    if category_id:
        cursor.execute(
            "SELECT products.*, categories.name AS category_name, brands.name AS brand_name FROM products LEFT JOIN categories ON categories.id = products.category_id LEFT JOIN brands ON brands.id = products.brand_id WHERE products.category_id = %s" + (" AND products.is_stock = 1" if include_only_in_stock else ""),
            (category_id,)
        )
    else:
        cursor.execute(
            "SELECT products.*, categories.name AS category_name, brands.name AS brand_name FROM products LEFT JOIN categories ON categories.id = products.category_id LEFT JOIN brands ON brands.id = products.brand_id" + (" WHERE products.is_stock = 1" if include_only_in_stock else "") + " ORDER BY products.id"
        )

    catalog = cursor.fetchall()
    for product in catalog:
        normalize_product_display_price(product)
    return catalog


def get_product_detail(product_id):
    db = get_db_connection()
    try:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT products.*, categories.name AS category_name, brands.name AS brand_name FROM products LEFT JOIN categories ON categories.id = products.category_id LEFT JOIN brands ON brands.id = products.brand_id WHERE products.id = %s",
                [product_id],
            )
            product = cursor.fetchone()
    finally:
        db.close()

    if not product:
        return None

    product = normalize_product_display_price(product)

    uploads_dir = os.path.join(app.static_folder, 'uploads')
    available_images = []
    if os.path.isdir(uploads_dir):
        available_images = [
            os.path.join('uploads', filename)
            for filename in sorted(os.listdir(uploads_dir))
            if os.path.isfile(os.path.join(uploads_dir, filename))
        ]

    product_name = (product.get('name') or '').strip()
    resolved_image = product.get('image_url')
    if not resolved_image:
        resolved_image = resolve_image_for_name(product_name, available_images, PRODUCT_IMAGE_ALIASES)
    resolved_image = ensure_existing_image(
        resolved_image,
        [resolve_image_for_name(product_name, available_images, PRODUCT_IMAGE_ALIASES), 'uploads/bar - 1.jpg']
    ) or 'uploads/bar - 1.jpg'
    product['image_url'] = resolved_image

    category_name = product.get('category_name') or 'Fireworks'
    product['description'] = (
        f"{product_name} is a premium {category_name.lower()} product from Shantini Crackers, designed to brighten celebrations with vibrant colors, festive energy, and a memorable experience for family and friends."
    )
    return product

# --- HOME & PRODUCT DISCOVERY ---
@app.route('/')
def index():
    db = get_db_connection()
    with db.cursor() as cursor:
        ensure_gift_box_images(cursor)
        cursor.execute("SELECT * FROM categories ORDER BY id")
        categories = cursor.fetchall()
        all_products = get_catalog_products(cursor, include_only_in_stock=True)[:50]

    category_order = {name.lower(): position for position, name in enumerate(HOME_CATEGORY_NAMES)}
    categories.sort(key=lambda category: category_order.get(category['name'].lower(), len(category_order)))

    uploads_dir = os.path.join(app.static_folder, 'uploads')
    available_images = []
    if os.path.isdir(uploads_dir):
        available_images = [
            os.path.join('uploads', filename)
            for filename in sorted(os.listdir(uploads_dir))
            if os.path.isfile(os.path.join(uploads_dir, filename))
        ]

    category_image_map = {}

    for category in categories:
        category_name = (category.get('name') or '').strip()
        category_image_map[category['id']] = category.get('image_url')

        if not category_image_map[category['id']]:
            category_image_map[category['id']] = resolve_image_for_name(category_name, available_images, CATEGORY_IMAGE_ALIASES)

        category_image_map[category['id']] = ensure_existing_image(
            category_image_map.get(category['id']),
            [resolve_image_for_name(category_name, available_images, CATEGORY_IMAGE_ALIASES)]
        )

    for product in all_products:
        category_id = product.get('category_id')
        if category_id and not category_image_map.get(category_id):
            category_image_map[category_id] = product.get('image_url')

    for category in categories:
        category['banner_image'] = ensure_existing_image(category_image_map.get(category['id']), ['uploads/bar - 1.jpg']) or 'uploads/bar - 1.jpg'

    db.close()
    return render_template('index.html', categories=categories, popular_products=all_products[:8])

@app.route('/products')
def products():
    category_id = request.args.get('category')
    db = get_db_connection()
    with db.cursor() as cursor:
        ensure_gift_box_images(cursor)
        all_products = get_catalog_products(cursor, category_id=category_id)
    uploads_dir = os.path.join(app.static_folder, 'uploads')
    available_images = []
    if os.path.isdir(uploads_dir):
        available_images = [
            os.path.join('uploads', filename)
            for filename in sorted(os.listdir(uploads_dir))
            if os.path.isfile(os.path.join(uploads_dir, filename))
        ]

    sound_cracker_images = {
        '4" gold lakshmi': 'uploads/4\' gold lakshmi.jpg',
        '4" deluxe lakshmi': 'uploads/4-deluxe-lakshmi-cracker.jpg',
        '4" lakshmi': 'uploads/4\' lakshmi.jpg',
        '3½" lakshmi': 'uploads/3\' lakshmi.jpg',
        '2¾" kuruvi': 'uploads/2 kuruvi.jpg',
        '2 sound': 'uploads/2 sound.jpg',
        '5" lakshmi / lion': 'uploads/5 lakshmi.jpg',
        '6" warior / lakshmi': 'uploads/6 lakshmi.jpg',
    }
    for product in all_products:
        product_name = (product.get('name') or '').strip()
        if product.get('image_url'):
            product['image_url'] = ensure_existing_image(
                product.get('image_url'),
                [
                    resolve_image_for_name(product_name, available_images, PRODUCT_IMAGE_ALIASES),
                    'uploads/bar - 1.jpg'
                ]
            )
            continue
        if str(category_id) == '1' and product_name:
            product['image_url'] = ensure_existing_image(
                sound_cracker_images.get(product_name.lower(), 'uploads/sound crackers.jpg'),
                [
                    resolve_image_for_name(product_name, available_images, PRODUCT_IMAGE_ALIASES),
                    'uploads/sound crackers.jpg'
                ]
            )
        else:
            product['image_url'] = ensure_existing_image(
                resolve_image_for_name(product_name, available_images, PRODUCT_IMAGE_ALIASES),
                ['uploads/bar - 1.jpg']
            ) or 'uploads/bar - 1.jpg'
    db.close()
    return render_template('products.html', products=all_products)


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = get_product_detail(product_id)
    if not product:
        flash('Product not found.', 'warning')
        return redirect(url_for('products'))
    return render_template('product_detail.html', product=product)


@app.route('/price-list.pdf')
def price_list_pdf():
    return send_file(os.path.join(app.static_folder, 'uploads', 'price-list.pdf'))


@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/admin/dashboard')
def admin_dashboard():
    access_denied = require_admin()
    if access_denied:
        return access_denied

    db = get_db_connection()
    with db.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM products")
        product_count = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) AS total FROM products WHERE is_stock = 1")
        in_stock_count = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) AS total FROM users")
        customer_count = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) AS total FROM inquiries")
        inquiry_count = cursor.fetchone()['total']
        products = get_catalog_products(cursor)
        cursor.execute("""
            SELECT inquiries.id, inquiries.total_amount, inquiries.status,
                   inquiries.created_at, users.name, users.email
            FROM inquiries
            LEFT JOIN users ON users.id = inquiries.user_id
            ORDER BY inquiries.created_at DESC
            LIMIT 8
        """)
        recent_inquiries = cursor.fetchall()
    db.close()

    stats = {
        'product_count': product_count,
        'in_stock_count': in_stock_count,
        'customer_count': customer_count,
        'inquiry_count': inquiry_count,
    }
    return render_template('admin_dashboard.html', stats=stats, recent_inquiries=recent_inquiries, products=products)

# --- USER IDENTITY LOGIC ---
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower() or None
        phone = normalize_phone(request.form.get('phone', ''))
        password = request.form.get('password', '')

        if not name or not phone or not password:
            flash("Please enter your name, phone number, and password.", "danger")
            return render_template('signup.html')

        password_hash = generate_password_hash(password)

        db = get_db_connection()
        try:
            with db.cursor() as cursor:
                phone_variants = {phone}
                if len(phone) == 10:
                    phone_variants.add('91' + phone)
                elif phone.startswith('91') and len(phone) == 12:
                    phone_variants.add(phone[2:])

                duplicate_query = "SELECT id FROM users WHERE phone IN (%s, %s)"
                duplicate_values = list(phone_variants)
                while len(duplicate_values) < 2:
                    duplicate_values.append(phone)
                if email:
                    duplicate_query += " OR email = %s"
                    duplicate_values.append(email)
                cursor.execute(duplicate_query, duplicate_values)
                if cursor.fetchone():
                    flash("This email or mobile number is already registered.", "danger")
                    return render_template('signup.html')

                cursor.execute(
                    "INSERT INTO users (name, email, phone, password_hash) VALUES (%s, %s, %s, %s)",
                    (name, email, phone, password_hash)
                )
            flash("Account registered! Please login.", "success")
            return redirect(url_for('login'))
        except pymysql.IntegrityError:
            flash("This email or mobile number is already registered.", "danger")
        except Exception:
            flash("We could not create your account right now. Please try again.", "danger")
        finally:
            db.close()
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        for session_key in ('logged_in', 'user_id', 'user_name', 'user_email', 'user_phone', 'is_admin'):
            session.pop(session_key, None)

        identifier = (request.form.get('identifier') or request.form.get('email') or '').strip()
        name = (request.form.get('name') or '').strip()
        phone = normalize_phone(request.form.get('phone') or '')
        password = request.form.get('password', '')

        if not (identifier or (name and phone)):
            flash("Please enter your email or mobile number and password.", "danger")
            return render_template('login.html')

        db = get_db_connection()
        with db.cursor() as cursor:
            if name and phone and not identifier:
                cursor.execute("SELECT * FROM users WHERE name = %s AND phone = %s", [name, phone])
            elif '@' in identifier:
                cursor.execute("SELECT * FROM users WHERE email = %s", [identifier.lower()])
            else:
                cursor.execute("SELECT * FROM users WHERE phone = %s", [normalize_phone(identifier)])
            user = cursor.fetchone()
        db.close()

        valid_login = False
        if user:
            if name and phone and not identifier and not password:
                valid_login = True
            elif password and check_password_hash(user['password_hash'], password):
                valid_login = True
            elif password and user.get('password_hash') == password:
                valid_login = True

        if valid_login:
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']
            session['user_phone'] = normalize_phone(user.get('phone') or '')
            session['is_admin'] = is_admin_user(user)
            session.setdefault('cart', {})
            if session.get('cart'):
                return redirect(url_for('view_cart'))
            return redirect(url_for('products'))
        else:
            flash("Invalid credentials.", "danger")
    return render_template('login.html')

# --- SESSION-BASED ESTIMATE CART ---
@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']
    qty = int(request.form.get('quantity', 1))

    p_id_str = str(product_id)
    if p_id_str in cart:
        cart[p_id_str] += qty
    else:
        cart[p_id_str] = qty

    session['cart'] = cart
    flash("Item added to estimate sheet.", "info")

    return_to = request.form.get('return_to')
    if not return_to:
        referrer = request.referrer or ''
        parsed_referrer = urllib.parse.urlparse(referrer)
        if parsed_referrer.path and parsed_referrer.path != '/cart':
            return_to = parsed_referrer.path

    if return_to and return_to.startswith('/'):
        return redirect(return_to)
    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    if not session.get('logged_in'):
        return render_template(
            'cart.html',
            cart_items=[],
            total=0,
            catalog_products=[],
            guest_cart_count=len(session.get('cart', {}))
        )

    db = get_db_connection()
    with db.cursor() as cursor:
        catalog_products = get_catalog_products(cursor)

    if 'cart' not in session or not session['cart']:
        db.close()
        return render_template('cart.html', cart_items=[], total=0, catalog_products=catalog_products)
        
    cart_items = []
    total = 0
    
    with db.cursor() as cursor:
        for p_id, qty in session['cart'].items():
            cursor.execute("""
                SELECT products.*, categories.name AS category_name
                FROM products
                LEFT JOIN categories ON categories.id = products.category_id
                WHERE products.id = %s
            """, [p_id])
            product = cursor.fetchone()
            if product:
                product = normalize_product_display_price(product)
                subtotal = product['discount_price'] * qty
                total += subtotal
                product['quantity'] = qty
                product['subtotal'] = subtotal
                cart_items.append(product)
    db.close()
            
    return render_template('cart.html', cart_items=cart_items, total=total, catalog_products=catalog_products)


@app.route('/cart/update/<int:product_id>', methods=['POST'])
def update_cart_item(product_id):
    cart = session.get('cart', {})
    product_key = str(product_id)
    try:
        quantity = int(request.form.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 1

    if product_key not in cart:
        flash("That product is not in your estimate sheet.", "warning")
    elif quantity > 0:
        cart[product_key] = quantity
        session['cart'] = cart
        flash("Estimate quantity updated.", "success")
    else:
        cart.pop(product_key)
        session['cart'] = cart
        flash("Item removed from estimate sheet.", "info")
    return redirect(url_for('view_cart'))


@app.route('/cart/remove/<int:product_id>', methods=['POST'])
def remove_cart_item(product_id):
    cart = session.get('cart', {})
    if cart.pop(str(product_id), None) is not None:
        session['cart'] = cart
        flash("Item removed from estimate sheet.", "info")
    else:
        flash("That product is not in your estimate sheet.", "warning")
    return redirect(url_for('view_cart'))

# --- WHATSAPP ESTIMATE EXPORT ---
@app.route('/submit_inquiry', methods=['POST'])
def submit_inquiry():
    if not session.get('logged_in'):
        flash("Please log in to complete your inquiry.", "warning")
        return redirect(url_for('login'))

    if 'cart' not in session or not session['cart']:
        return redirect(url_for('index'))

    customer_name = (request.form.get('customer_name') or session.get('user_name') or 'Customer').strip()
    customer_phone = normalize_phone(request.form.get('customer_phone') or session.get('user_phone') or '')
    customer_email = (request.form.get('customer_email') or session.get('user_email') or '').strip()

    if not customer_phone:
        flash("Please enter the customer phone number before sending the order.", "warning")
        return redirect(url_for('view_cart'))

    MINIMUM_ESTIMATE_AMOUNT = 3000
    db = get_db_connection()
    total = 0
    items_to_save = []

    whatsapp_text = f"🚨 *Shantini Crackers Estimate Inquiry*\n"
    whatsapp_text += f"👤 *Customer:* {customer_name}\n"
    whatsapp_text += f"📞 *Phone:* {customer_phone}\n"
    if customer_email:
        whatsapp_text += f"✉️ *Email:* {customer_email}\n"
    whatsapp_text += f"------------------------------------\n"

    with db.cursor() as cursor:
        for p_id, qty in session['cart'].items():
            cursor.execute("""
                SELECT products.name, products.actual_price, products.discount_price, categories.name AS category_name
                FROM products
                LEFT JOIN categories ON categories.id = products.category_id
                WHERE products.id = %s
            """, [p_id])
            p = cursor.fetchone()
            if p:
                p = normalize_product_display_price(p)
                subtotal = p['discount_price'] * qty
                total += subtotal
                items_to_save.append((p_id, qty, p['discount_price']))
                whatsapp_text += f"• {p['name']} x {qty} = ₹{subtotal:.2f}\n"

        whatsapp_text += f"------------------------------------\n"
        whatsapp_text += f"💰 *Total Estimated Value:* ₹{total:.2f}"

        if total < MINIMUM_ESTIMATE_AMOUNT:
            db.close()
            flash(f"Minimum estimate amount is ₹{MINIMUM_ESTIMATE_AMOUNT}. Please add more items to reach the minimum order value.", "warning")
            session['cart'] = session.get('cart', {})
            return redirect(url_for('view_cart'))

        # Save into database logs
        cursor.execute("INSERT INTO inquiries (user_id, total_amount) VALUES (%s, %s)", (session['user_id'], total))
        inquiry_id = cursor.lastrowid

        for p_id, qty, price in items_to_save:
            cursor.execute(
                "INSERT INTO inquiry_items (inquiry_id, product_id, quantity, price_at_booking) VALUES (%s, %s, %s, %s)",
                (inquiry_id, p_id, qty, price)
            )

    db.close()

    pdf_data, pdf_path = generate_estimate_pdf(customer_name, whatsapp_text)
    if not customer_email or '@' not in customer_email:
        flash(f"Estimate receipt saved locally to {os.path.basename(pdf_path)}.", "success")
    else:
        try:
            email_sent = send_estimate_email(customer_email, customer_name, whatsapp_text)
            if email_sent:
                flash("Estimate receipt saved locally and sent to the customer email.", "success")
            else:
                flash("Estimate receipt was saved locally, but email sending is disabled because SMTP credentials are not configured.", "warning")
        except (OSError, smtplib.SMTPException):
            flash("Order saved locally, but the customer receipt email could not be sent.", "warning")

    session.pop('cart', None)

    admin_phone = get_whatsapp_admin_phone()
    encoded_message = urllib.parse.quote(whatsapp_text)
    whatsapp_url = f"https://wa.me/{admin_phone}?text={encoded_message}"

    return redirect(whatsapp_url)

@app.route('/logout')
def logout():
    session.clear()
    return render_template('logout.html')

UPLOAD_FOLDER = os.path.join('templates', 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Limit file upload size to 5MB to protect your laptop's storage
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
@app.route('/admin/add-product', methods=['GET', 'POST'])
def admin_add_product():
    access_denied = require_admin()
    if access_denied:
        return access_denied
    db = get_db_connection()
    
    if request.method == 'POST':
        name = request.form['name']
        category_id = request.form['category_id']
        brand_id = request.form['brand_id']
        actual_price = request.form['actual_price']

        category_name = ''
        with db.cursor() as cursor:
            cursor.execute("SELECT name FROM categories WHERE id = %s", [category_id])
            category_row = cursor.fetchone()
            if category_row:
                category_name = category_row.get('name', '')

        discount_price = get_effective_discount_price(actual_price, category_name)
        
        # Handle the image file upload
        if 'image' not in request.files:
            flash('No image part in the form', 'danger')
            return redirect(request.url)
            
        file = request.files['image']
        
        if file.filename == '':
            flash('No selected image file', 'danger')
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            # secure_filename prevents malicious path injections (e.g., ../../etc/passwd)
            filename = secure_filename(file.filename)
            # Save the file to static/uploads/
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            # Store the relative path string in your MySQL database
            relative_image_path = f"uploads/{filename}"
            
            with db.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO products (name, category_id, brand_id, actual_price, discount_price, image_url, is_stock) 
                    VALUES (%s, %s, %s, %s, %s, %s, 1)
                """, (name, category_id, brand_id, actual_price, discount_price, relative_image_path))
            
            flash("🎉 New product with image added successfully!", "success")
            return redirect(url_for('products'))
            
    # GET Request: Fetch categories and brands to populate form dropdown choices
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM categories")
        categories = cursor.fetchall()
        cursor.execute("SELECT * FROM brands")
        brands = cursor.fetchall()
    db.close()
    
    return render_template('admin_add_product.html', categories=categories, brands=brands)


@app.route('/admin/edit-product/<int:product_id>', methods=['GET', 'POST'])
def admin_edit_product(product_id):
    access_denied = require_admin()
    if access_denied:
        return access_denied
    db = get_db_connection()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM products WHERE id = %s", [product_id])
        product = cursor.fetchone()
        if not product:
            db.close()
            flash("Product not found.", "danger")
            return redirect(url_for('admin_dashboard'))
        if request.method == 'POST':
            image = request.files.get('image')
            image_url = product['image_url']
            selected_category_id = request.form['category_id']
            selected_actual_price = request.form['actual_price']

            category_name = ''
            cursor.execute("SELECT name FROM categories WHERE id = %s", [selected_category_id])
            category_row = cursor.fetchone()
            if category_row:
                category_name = category_row.get('name', '')

            effective_discount = get_effective_discount_price(selected_actual_price, category_name)

            if image and image.filename:
                if not allowed_file(image.filename):
                    db.close()
                    flash("Please upload a PNG, JPG, JPEG, WEBP, or GIF image.", "danger")
                    return redirect(request.url)
                filename = secure_filename(image.filename)
                image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_url = f"uploads/{filename}"
            cursor.execute("""
                UPDATE products
                SET name = %s, category_id = %s, brand_id = %s,
                    actual_price = %s, discount_price = %s, image_url = %s,
                    is_stock = %s
                WHERE id = %s
            """, (request.form['name'], selected_category_id, request.form['brand_id'],
                  selected_actual_price, effective_discount, image_url,
                  request.form.get('is_stock', '0'), product_id))
            db.close()
            flash("Product updated successfully.", "success")
            return redirect(url_for('admin_dashboard'))
        cursor.execute("SELECT * FROM categories ORDER BY name")
        categories = cursor.fetchall()
        cursor.execute("SELECT * FROM brands ORDER BY name")
        brands = cursor.fetchall()
    db.close()
    return render_template('admin_edit_product.html', product=product, categories=categories, brands=brands)


@app.route('/admin/delete-product/<int:product_id>', methods=['POST'])
def admin_delete_product(product_id):
    access_denied = require_admin()
    if access_denied:
        return access_denied
    db = get_db_connection()
    with db.cursor() as cursor:
        cursor.execute("DELETE FROM products WHERE id = %s", [product_id])
        deleted = cursor.rowcount
    db.close()
    flash("Product removed successfully." if deleted else "Product not found.", "success" if deleted else "warning")
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
