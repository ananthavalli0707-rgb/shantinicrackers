import pymysql
import pymysql.cursors
from werkzeug.security import generate_password_hash
from config import Config

def initialize_and_seed():
    try:
        # Connect to MySQL Server (Without choosing a DB yet)
        conn = pymysql.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        cursor = conn.cursor()
        
        # 1. Create Database if it does not exist
        cursor.execute("CREATE DATABASE IF NOT EXISTS fireworks_db;")
        cursor.execute("USE fireworks_db;")
        print("Database 'fireworks_db' ready.")

        # 2. Build Table Schema
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            phone VARCHAR(15) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("ALTER TABLE users MODIFY email VARCHAR(100) NULL;")
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            image_url VARCHAR(255)
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS brands (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            category_id INT,
            brand_id INT,
            actual_price DECIMAL(10, 2) NOT NULL,
            discount_price DECIMAL(10, 2) NOT NULL,
            image_url VARCHAR(255),
            is_stock INT DEFAULT 1,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
            FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE SET NULL
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS inquiries (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            total_amount DECIMAL(10, 2) NOT NULL,
            status VARCHAR(50) DEFAULT 'Pending Review',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS shipping_details (
            id INT AUTO_INCREMENT PRIMARY KEY,
            inquiry_id INT NOT NULL,
            shipping_name VARCHAR(100) NOT NULL,
            shipping_address_1 VARCHAR(255) NOT NULL,
            shipping_address_2 VARCHAR(255),
            city VARCHAR(100) NOT NULL,
            pincode VARCHAR(10) NOT NULL,
            district VARCHAR(100) NOT NULL,
            state VARCHAR(100) NOT NULL,
            landmark VARCHAR(255),
            contact_number VARCHAR(20) NOT NULL,
            alternate_contact_number VARCHAR(20),
            whatsapp_number VARCHAR(20),
            customer_email VARCHAR(100),
            FOREIGN KEY (inquiry_id) REFERENCES inquiries(id) ON DELETE CASCADE
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS inquiry_items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            inquiry_id INT,
            product_id INT,
            quantity INT NOT NULL,
            price_at_booking DECIMAL(10, 2) NOT NULL,
            FOREIGN KEY (inquiry_id) REFERENCES inquiries(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        );
        """)
        
        # Clear old rows to prevent duplication errors
        cursor.execute("TRUNCATE TABLE shipping_details;")
        cursor.execute("TRUNCATE TABLE inquiry_items;")
        cursor.execute("TRUNCATE TABLE inquiries;")
        cursor.execute("TRUNCATE TABLE products;")
        cursor.execute("TRUNCATE TABLE brands;")
        cursor.execute("TRUNCATE TABLE categories;")
        cursor.execute("TRUNCATE TABLE users;")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        print("Tables configured successfully.")

        # 3. Seed Brands and Categories
        brands = [('Anil Brand',), ('Vanitha Brand',), ('Standard Brand',), ('Sri Narayana Brand',)]
        cursor.executemany("INSERT INTO brands (name) VALUES (%s)", brands)
        
        categories = [
            ('Sound Crackers', 'uploads/sound crackers.jpg'),
            ('Flower Pots', 'uploads/flower pot.jpg'),
            ('Ground Chakkar', 'uploads/chakkras.jpg'),
            ('Garlands', 'uploads/garland.jpg'),
            ('Paper Blast', 'uploads/paper blast.jpg'),
            ('Bombs', 'uploads/bomb.jpg'),
            ('Rockets', 'uploads/rockets.jpg'),
            ('Twinkling Stars', 'uploads/twinkling.jpg'),
            ('Bijili Crackers', 'uploads/bijili crackers.png'),
            ('Fancy Shots', 'uploads/multishot.jpg'),
            ('Whistling Crackers', 'uploads/whistling crackers.jpg'),
            ('Fancy Novelties', 'uploads/fancy items.jfif'),
            ('Sparklers', 'uploads/10 cm Electric Sparklers.jpg'),
            ('Child Crackers', 'uploads/unicorn_15items.jpeg'),
            ('Color Matches', 'uploads/super deluxe colour matches.jpg'),
            ('Varieties', 'uploads/bar - 2.jpg'),
            ('Gift Box', 'uploads/unicorn_15items.jpeg')
        ]
        cursor.executemany("INSERT INTO categories (name, image_url) VALUES (%s, %s)", categories)

        # Fetch maps
        cursor.execute("SELECT id, name FROM categories")
        cat_map = {row['name']: row['id'] for row in cursor.fetchall()}
        cursor.execute("SELECT id, name FROM brands")
        brand_map = {row['name']: row['id'] for row in cursor.fetchall()}

        # 4. Seed Product Catalog from the price list
        products_data = []

        def add_products(category_name, items, image_paths=None):
            products_data.extend(
                (name, cat_map[category_name], brand_map['Standard Brand'], rate, rate,
                 image_paths[item_index] if image_paths and item_index < len(image_paths) else None)
                for item_index, (name, rate) in enumerate(items)
            )

        add_products('Sound Crackers', [
            ('4" Gold Lakshmi', 167), ('4" Deluxe Lakshmi', 167), ('4" Lakshmi', 120),
            ('3½" Lakshmi', 80), ('2¾" Kuruvi', 55), ('2 Sound', 200),
            ('5" Lakshmi / Lion', 270), ('6" Warior / Lakshmi', 350)
        ], [
            'uploads/4\' gold lakshmi.jpg', 'uploads/4-deluxe-lakshmi-cracker.jpg',
            'uploads/4\' lakshmi.jpg', 'uploads/3\' lakshmi.jpg', 'uploads/2 kuruvi.jpg',
            'uploads/2 sound.jpg', 'uploads/5 lakshmi.jpg', 'uploads/6 lakshmi.jpg'
        ])
        add_products('Flower Pots', [
            ('Flower Pots Big', 350), ('Flower Pots Special', 480), ('Flower Pots Asoka', 550),
            ('Flower Pots Deluxe (5 Pcs)', 900), ('Flower Pots SuperDeluxe (2Pcs)', 600),
            ('Colour Koti', 1200), ('Tri Colour (5 Pcs)', 1300)
        ], [
            'uploads/flower pot big.jpg', 'uploads/flower pot special.jpg', 'uploads/flower pot asoka.jpg',
            'uploads/Flower Pot Deluxe.jpg', 'uploads/flower pot super deluxe.jpg',
            'uploads/colour koti.jpg', 'uploads/tricolour.jpg'
        ])
        add_products('Ground Chakkar', [
            ('Ground Chakkar Big', 200), ('Ground Chakkar Special', 450),
            ('Ground Chakkar Deluxe', 800), ('Disco Wheel', 500)
        ], [
            'uploads/Ground Chakkar Big.jpg', 'uploads/Ground Chakkar special.jpg',
            'uploads/Ground Chakkar deluxe.jpg', 'uploads/chakkras.jpg'
        ])
        add_products('Garlands', [
            ('1000 Wala', 1334), ('2000 Wala', 2668), ('5000 Wala', 6670), ('10000 Wala', 13340)
        ], [
            'uploads/1000 wala.jpg', 'uploads/2000 wala.jpg', 'uploads/5000 wala.jpg', 'uploads/10000 wala.jpeg'
        ])
        add_products('Paper Blast', [('¼ kg', 267), ('½ kg', 534), ('1 kg', 1068)], [
            'uploads/paper blast.jpg', 'uploads/half paper.jpg', 'uploads/1 kg paper.jpg'
        ])
        add_products('Bombs', [
            ('Bullet Bomb', 200), ('Atom Bomb', 285), ('Hydro Bomb', 400),
            ('King of King Bomb', 500), ('Classic Bomb', 600), ('Agni Bomb', 1050),
            ('Digital Bomb', 1200)
        ], [
            'uploads/bullet.jfif', 'uploads/atom.jfif', 'uploads/hydro.jfif',
            'uploads/king of king.jfif', 'uploads/classic.jfif', 'uploads/agni.jfif', 'uploads/digital.jfif'
        ])
        add_products('Rockets', [('Baby Rockets', 210), ('Rocket Bomb', 400)], [
            'uploads/baby rocket.jfif', 'uploads/rocket bomb.jfif'
        ])
        add_products('Twinkling Stars', [('1½" Twinkling Star', 135), ('4" Twinkling Star', 335)], [
            'uploads/1 twinkling star.jfif', 'uploads/4 inch twinkling star.jfif'
        ])
        add_products('Bijili Crackers', [('Red Bijili', 200), ('Stripped Bijili', 230)], [
            'uploads/red bijili.jfif', 'uploads/stripped bijili.jfif'
        ])
        add_products('Fancy Shots', [
            ('Chotta Fancy', 335), ('Penta Fancy (5 pcs)', 1000), ('2" Fancy (3 Pcs)', 1500),
            ('2" Fancy (Boom with Color)', 700), ('2"Fancy Trible Color', 1140),
            ('3" Fancy (Boom with Color)', 1300), ('3½" Fancy (Boom with Color)', 1400),
            ('4" Fancy Color', 1800), ('7 Shots (5 Pcs)', 668), ('12 Shot\'s Rider & Colour', 950),
            ('12 Shot\'s Multicolour', 1200), ('30 Shots Multicolour', 2335),
            ('60 Shot\'s Multicolour', 4670), ('120 Shot\'s Multicolour', 9340),
            ('240 Shot\'s Multicolour', 18680)
        ], [
            'uploads/chotta fancy.jfif', 'uploads/penta fancy.jfif', 'uploads/2 inch fancy.jfif',
            'uploads/2 inch fancy boom .jfif', 'uploads/2 inch fancy triple color.jfif',
            'uploads/3 inch fancy.jfif', 'uploads/3 inch fancy boom.jfif', 'uploads/4 inch fancy.jfif',
            'uploads/7 shots.jfif', 'uploads/12 shots.jfif', 'uploads/12 shots multicolour.jfif',
            'uploads/30 shots.jfif', 'uploads/60 shots.jfif', 'uploads/120 shots.jfif', 'uploads/240 shots.jfif'
        ])
        add_products('Whistling Crackers', [
            ('Whiztling Rocket', 950), ('Egg', 1200), ('Siren', 1000),
            ('Mini Siren', 740), ('Whiztling Wheel', 600)
        ], [
            'uploads/whistling rocket.jfif', 'uploads/egg rockets.png', 'uploads/siren.jfif',
            'uploads/mini siren.jfif', 'uploads/whistling wheel.jfif'
        ])
        add_products('Fancy Novelties', [
            ('Butterfly Green', 500), ('Top Gun', 1100), ('Chit Put', 220),
            ('Colour Shower', 570), ('Helicopter', 534), ('Old is Gold', 600),
            ('Colour Rain', 534), ('Ashrafi Pops', 534), ('Peacock Feather', 534),
            ('Golden Peacock', 1000), ('Bambaram', 500), ('Selfie Stick', 660),
            ('Hi-Fi Pencil', 1000), ('Photo Flash', 400), ('Magic Show', 1000),
            ('Bada Peacock', 2200), ('Colour Smoke', 600), ('Canon Ball', 1068),
            ('Lollipop', 930), ('Money Bank', 634), ('Rotating Sparklers', 1100),
            ('Angry Bird', 768), ('4 X 4 Wheel', 1140)
        ], [
            'uploads/butterfly.jpg', 'uploads/top gun.jpg', 'uploads/chitput.jpg',
            'uploads/colour shower.jpg', 'uploads/helicopter.jpg', 'uploads/old is gold.jpg',
            'uploads/colour rain.jpg', 'uploads/asrifi pops.jpg', 'uploads/peacock feather.jpg',
            'uploads/golden peacock.jpg', 'uploads/bambaram.jpg', 'uploads/selfie stick.jpg',
            'uploads/hi fi pencil.jpg', 'uploads/photo flash.jpg', 'uploads/magic show.jpg',
            'uploads/beda peacock.jpg', 'uploads/colour smoke.jpg', 'uploads/canon ball.jpg',
            'uploads/lollipop.jpg', 'uploads/money bank.jpg', 'uploads/rotating sparklers.jpg',
            'uploads/angry bird.jpg', 'uploads/4  4 wheels'
        ])
        add_products('Sparklers', [
            ('7 cm Electric', 67), ('7 cm Colour', 85), ('7 cm Green', 100), ('7 cm Red', 120),
            ('10 cm Electric', 127), ('10 cm Colour', 140), ('10 cm Green', 148), ('10 cm Red', 160),
            ('15 cm Electric', 254), ('15 cm Colour', 270), ('15 cm Green', 290), ('15 cm Red', 300),
            ('30 cm Electric', 254), ('30 cm Colour', 270), ('30 cm Green', 290), ('30 cm Red', 300),
            ('50 cm Electric', 934), ('50 cm Colour', 1067)
        ], [
            'uploads/7 cm sparklers.jpg', 'uploads/7 cm colour sparklers.jpg', 'uploads/7 cm green sparklers.jpg', 'uploads/7 cm red sparklers.jpg',
            'uploads/10 cm Electric Sparklers.jpg', 'uploads/10 cm colour sparklers.jpg', 'uploads/10 cm green sparklers.jpg', 'uploads/10 cm red sparklers.jpg',
            'uploads/15 cm electric sparklers.jpg', 'uploads/15 cm colour sparklers.jpg', 'uploads/15 cm green sparklers.jpg', 'uploads/15 cm red sparklers.jpg',
            'uploads/30 cm electric sparklers.jpg', 'uploads/30 cm colour sparklers.jpg', 'uploads/30 cm green sparklers.png', 'uploads/30 cm red sparklers.jpg',
            'uploads/50 cm electric sparklers.jpg', 'uploads/50 cm colour sparklers.jpg'
        ])
        add_products('Child Crackers', [
            ('Electric Stone', 67), ('Jee Boom Baa', 67), ('Roll Caps', 380),
            ('Cartoon', 220), ('Ring Gun', 670), ('Serpent Egg', 200)
        ], [
            'uploads/electric stone.jpg', 'uploads/jee boom baa.jpg', 'uploads/roll cap.jpg',
            'uploads/cartoon.jpg', 'uploads/ring gun.jpg', 'uploads/serpent egg.jpg'
        ])
        add_products('Color Matches', [('Super Deluxe', 500), ('Lamba', 800), ('Mega Laptop', 1200)], [
            'uploads/super deluxe colour matches.jpg', 'uploads/lamba.jpg', 'uploads/mega laptop.jpg'
        ])
        add_products('Varieties', [
            ('Ganga Jamuna', 500), ('Ashrafi Pops Small', 350), ('Colourful Pencil', 900),
            ('Wire Chakkar', 900), ('5 Colour Fountain', 900)
        ], [
            'uploads/ganga jamuna.jpg', 'uploads/ashrafi pops small.jpg', 'uploads/colourful pencil.jpg',
            'uploads/wire chakkar.jpg', 'uploads/5 colour fountain.jpg'
        ])
        add_products('Gift Box', [
            ('15 Items (Milky Bar)', 170), ('20 Items (Croods / Moana)', 255),
            ('25 Items (Lion King / 5 Star)', 325), ('30 Items (Spiderman / Kit Kat)', 390),
            ('35 Items (Ice Age / Dairy Milk)', 465), ('40 Items (Venkatesh / Snickers)', 575),
            ('50 Items (Krishna / Avengers)', 765), ('60 Items (Mahabharata)', 980)
        ], [
            'uploads/unicorn_15items.jpeg', 'uploads/unicorn_20items.jpeg',
            'uploads/unicorn_25items.jpeg', 'uploads/unicorn_30items.jpeg',
            'uploads/unicorn_35items.jpeg', 'uploads/unicorn_40items.jpeg',
            'uploads/unicorn_50items.jpeg', 'uploads/unicorn_60items.jpeg'
        ])
        cursor.executemany(
            "INSERT INTO products (name, category_id, brand_id, actual_price, discount_price, image_url, is_stock) VALUES (%s, %s, %s, %s, %s, %s, 1)",
            products_data
        )

        # 5. Seed Test Admin user
        cursor.execute(
            "INSERT INTO users (name, email, password_hash, phone) VALUES (%s, %s, %s, %s)",
            ('System Admin', Config.ADMIN_EMAIL, generate_password_hash('ananthi'), Config.ADMIN_PHONE)
        )
        
        print("🎉 Database initialized and seeded over direct network port connection!")

    except Exception as e:
        print(f"❌ Initialization error: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    initialize_and_seed()
