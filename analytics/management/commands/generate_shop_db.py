"""
Management command : generate_shop_db

Genere une base SQLite complete d'un magasin de detail.
Tables : suppliers, categories, products, customers, orders, order_items

Usage :
    python manage.py generate_shop_db
    python manage.py generate_shop_db --out /tmp/shop.db
    python manage.py generate_shop_db --customers 1000 --orders 10000
"""
import random
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.core.management.base import BaseCommand
from faker import Faker

fake = Faker("fr_FR")

CATEGORIES = [
    ("Alimentation",        "Produits frais, epicerie, boissons"),
    ("Hygiene & Beaute",    "Soins, cosmetiques, parfums"),
    ("Electronique",        "Smartphones, accessoires, audio"),
    ("Maison & Jardin",     "Mobilier, decoration, jardinage"),
    ("Vetements Homme",     "Mode masculine toutes saisons"),
    ("Vetements Femme",     "Mode feminine toutes saisons"),
    ("Enfants & Jouets",    "Puericulture, jeux, loisirs"),
    ("Sport & Plein air",   "Equipements sportifs, fitness"),
    ("Librairie & Culture", "Livres, musique, papeterie"),
    ("Informatique",        "Ordinateurs, logiciels, peripheriques"),
]

PRODUCTS_BY_CAT = {
    "Alimentation":        [("Cafe Premium 250g",24.90,11.50),("The Vert Bio",6.50,3.80),("Miel Montagne 500g",12.00,7.00),("Huile Olive 1L",14.50,8.90),("Chocolat Noir 200g",4.20,2.40),("Pates Artisanales 500g",3.80,2.10),("Riz Basmati 1kg",5.90,3.40),("Saumon Fume 100g",9.50,5.80),("Fromage AOP 200g",11.00,6.50),("Confiture Artisanale 350g",7.20,4.20)],
    "Hygiene & Beaute":    [("Creme Hydratante 50ml",18.90,9.50),("Shampooing Keratine 300ml",13.50,7.20),("Parfum Floral 50ml",45.00,22.00),("Serum Vitamine C 30ml",32.00,16.00),("Dentifrice Blancheur",6.80,3.50),("Deodorant Bio 75ml",8.90,4.80),("Apres-rasage Bois",22.00,11.50),("Masque Hydratant 75ml",24.50,12.00),("Huile Corps 200ml",16.50,8.50),("Rouge a Levres Mat",19.00,9.00)],
    "Electronique":        [("Ecouteurs Bluetooth",59.90,28.00),("Batterie Externe 20000mAh",39.90,18.50),("Cable USB-C 2m",12.90,5.50),("Support Telephone Voiture",22.00,9.80),("Enceinte Portable IP67",49.90,23.00),("Montre Connectee Sport",129.00,62.00),("Casque Audio ANC",189.00,89.00),("Hub USB-C 7 ports",44.90,21.00),("Webcam Full HD",79.90,38.00),("Souris sans fil",35.90,16.50)],
    "Maison & Jardin":     [("Bougie Parfumee Vanille",14.90,6.80),("Plante Succulente 12cm",9.90,4.20),("Coussin Deco 45x45cm",24.90,11.50),("Lampe Bureau LED",39.90,18.90),("Nappe Coton 140x200cm",28.00,13.50),("Vase Ceramique 25cm",32.00,15.00),("Cadre Photo Bois 20x30cm",18.50,8.80),("Pot Terracotta",16.90,8.00),("Bougies LED x6",19.90,9.50),("Tapis Salon 120x170cm",89.00,42.00)],
    "Vetements Homme":     [("T-shirt Coton Bio M",24.90,11.50),("Jean Slim 32/32",59.90,28.00),("Polo Pique L",39.90,18.50),("Chaussettes Laine x3",16.90,7.80),("Pull Col V XL",49.90,23.50),("Chemise Oxford M",54.90,26.00),("Short Sport L",29.90,14.00),("Veste Legere M",89.00,42.00),("Ceinture Cuir 95cm",28.00,13.00),("Calecon x2 M",22.90,10.50)],
    "Vetements Femme":     [("Robe Fleurie T38",44.90,21.00),("Legging Sport T40",32.90,15.50),("Blouse Soie T36",64.90,30.00),("Pantalon Tailleur T42",74.90,35.00),("Cardigan Long T38",54.90,26.00),("Top Basique x2 T40",29.90,14.00),("Jupe Plissee T38",39.90,19.00),("Pyjama Coton T36",34.90,16.50),("Collants x3 T2",12.90,6.00),("Foulard Soie",28.00,13.00)],
    "Enfants & Jouets":    [("Puzzle 500 pieces",19.90,9.20),("Lego Classic 500p",44.90,21.00),("Peluche Lapin 40cm",24.90,11.50),("Livre Apprentissage 3-6ans",14.90,7.00),("Jeu de Societe Famille",32.00,15.00),("Crayons Couleur x24",12.90,6.00),("Pate a Modeler x6",16.90,7.80),("Voiture Telecommandee",54.90,26.00),("Dinette Bois 15p",39.90,18.50),("Trottinette 3 roues",69.90,33.00)],
    "Sport & Plein air":   [("Gourde Inox 750ml",24.90,11.50),("Tapis Yoga Antiderapant",34.90,16.50),("Resistance Elastique x5",22.90,10.50),("Gants Fitness M",18.90,8.80),("Sac Sport 30L",44.90,21.00),("Corde a Sauter Pro",16.90,7.80),("Chronometre Digital",19.90,9.20),("Bidon Velo 600ml",14.90,7.00),("Genouilleres x2",22.90,10.80),("Casquette Running",19.90,9.20)],
    "Librairie & Culture": [("Roman Policier Bestseller",21.90,10.50),("Guide Voyage Paris 2024",18.90,9.00),("Agenda 2024 Cuir",24.90,11.50),("Stylo Roller",12.90,6.00),("Cahier Dot Grid A5",9.90,4.60),("Marque-pages x10",7.90,3.60),("BD Manga Tome 1",8.50,4.00),("Cartes Postales x20",14.90,7.00),("Coloriage Adulte Zen",16.90,7.80),("Livre Recettes Vege",28.00,13.00)],
    "Informatique":        [("Cle USB 64Go",14.90,6.80),("SSD Externe 500Go",79.90,38.00),("Tapis Souris XXL",22.90,10.50),("Repose-poignet Gel",14.90,7.00),("Filtre Ecran 27",39.90,18.90),("Cable HDMI 2m",18.90,8.80),("Refroidisseur Laptop",34.90,16.50),("Nettoyant Ecran 200ml",9.90,4.60),("Carte SD 128Go",24.90,11.50),("Adaptateur USB-A/C",11.90,5.40)],
}

SUPPLIERS = ["DistribPro France","EuroSupply SARL","MediterraneeDistrib","NordLogistique","ImportExpress","FranceGros SA","EcoSourcePro","TechDistrib Europe"]
CITIES = ["Paris","Lyon","Marseille","Toulouse","Bordeaux","Lille","Nantes","Strasbourg","Rennes","Nice","Montpellier","Grenoble","Toulon","Dijon","Angers","Brest","Reims"]
SEGMENTS = ["Standard","Premium","Fidele","Nouveau","Inactif"]
STATUSES = ["completed","completed","completed","pending","cancelled","refunded"]
PAYMENTS = ["Carte bancaire","Carte bancaire","Virement","PayPal","Especes","Cheque"]


class Command(BaseCommand):
    help = "Genere une base SQLite d'un magasin (produits, clients, commandes)."

    def add_arguments(self, parser):
        parser.add_argument("--out",       type=str, default=None,  help="Chemin du fichier SQLite ou dossier CSV")
        parser.add_argument("--customers", type=int, default=500,   help="Nb clients (def: 500)")
        parser.add_argument("--orders",    type=int, default=3000,  help="Nb commandes (def: 3000)")
        parser.add_argument("--months",    type=int, default=24,    help="Periode en mois (def: 24)")
        parser.add_argument("--format",    type=str, default="sqlite", choices=["sqlite", "csv"],
                            help="Format de sortie : sqlite (defaut) ou csv")

    def handle(self, *args, **opts):
        from django.conf import settings
        n_cust   = max(10, opts["customers"])
        n_ord    = max(10, opts["orders"])
        n_mon    = max(1,  opts["months"])
        fmt      = opts["format"]   # "sqlite" ou "csv"
        stamp    = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ── Résolution du chemin de sortie ────────────────────────────────
        if opts["out"]:
            out = Path(opts["out"]).expanduser().resolve()
            is_dir_hint = out.is_dir() or str(opts["out"]).endswith("/") or str(opts["out"]).endswith(".")
            if fmt == "csv":
                # Pour CSV : --out pointe vers un dossier de destination
                if is_dir_hint:
                    csv_dir = out / f"shop_{stamp}"
                else:
                    # Chemin traité comme dossier de destination
                    csv_dir = out if out.suffix == "" else out.parent / out.stem
                # SQLite temporaire dans tmp_dbs
                tmp_dir = Path(settings.MEDIA_ROOT) / "tmp_dbs"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                sqlite_out = tmp_dir / f"_tmp_{stamp}.db"
            else:
                # SQLite : chemin vers un fichier
                if is_dir_hint:
                    sqlite_out = out / f"shop_{stamp}.db"
                elif out.suffix not in (".db", ".sqlite", ".sqlite3"):
                    sqlite_out = out.with_suffix(".db")
                else:
                    sqlite_out = out
                csv_dir = None
        else:
            base_dir = Path(settings.MEDIA_ROOT) / "tmp_dbs"
            base_dir.mkdir(parents=True, exist_ok=True)
            if fmt == "csv":
                csv_dir    = base_dir / f"shop_{stamp}"
                sqlite_out = base_dir / f"_tmp_{stamp}.db"
            else:
                sqlite_out = base_dir / f"shop_{stamp}.db"
                csv_dir    = None

        sqlite_out.parent.mkdir(parents=True, exist_ok=True)
        if sqlite_out.exists():
            sqlite_out.unlink()

        self.stdout.write(f"Generation des donnees ({fmt.upper()})...")
        conn = sqlite3.connect(str(sqlite_out))
        self._schema(conn)

        now   = datetime.now(tz=timezone.utc)
        start = now - timedelta(days=30 * n_mon)

        # Fournisseurs
        sup_ids = []
        for name in SUPPLIERS:
            sid = str(uuid.uuid4())
            conn.execute("INSERT INTO suppliers VALUES (?,?,?,?,?,?)",
                (sid, name, fake.email(), fake.phone_number(), fake.city(), fake.country()))
            sup_ids.append(sid)
        self.stdout.write(f"  v {len(sup_ids)} fournisseurs")

        # Categories & Produits
        cat_ids = {}
        for cname, cdesc in CATEGORIES:
            cid = str(uuid.uuid4())
            conn.execute("INSERT INTO categories VALUES (?,?,?)", (cid, cname, cdesc))
            cat_ids[cname] = cid

        prod_rows = []
        prod_ids  = []
        for cat, prods in PRODUCTS_BY_CAT.items():
            cid = cat_ids.get(cat, str(uuid.uuid4()))
            for pname, price, cost in prods:
                pid = str(uuid.uuid4())
                row = (pid, f"REF-{random.randint(10000,99999)}", pname, cat, cid,
                       round(price,2), round(cost,2), random.randint(0,500),
                       random.choice([1,1,1,0]), random.choice(sup_ids))
                prod_rows.append(row)
                prod_ids.append(pid)
        conn.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?)", prod_rows)
        self.stdout.write(f"  v {len(prod_ids)} produits")

        # Clients
        cust_ids = []
        cust_rows = []
        for _ in range(n_cust):
            cid = str(uuid.uuid4())
            g   = random.choice(["M","F"])
            fn  = fake.first_name_male() if g=="M" else fake.first_name_female()
            joined = start + timedelta(days=random.randint(0,(now-start).days))
            row = (cid, fn, fake.last_name(), fake.email(), fake.phone_number(),
                   random.choice(CITIES), random.randint(18,78), g,
                   random.choice(SEGMENTS), joined.strftime("%Y-%m-%d"))
            cust_rows.append(row)
            cust_ids.append(cid)
        conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?)", cust_rows)
        self.stdout.write(f"  v {len(cust_ids)} clients")

        # Commandes
        ord_rows  = []
        item_rows = []
        pmap = {r[0]: r for r in prod_rows}
        for _ in range(n_ord):
            oid    = str(uuid.uuid4())
            cid    = random.choice(cust_ids)
            status = random.choice(STATUSES)
            chosen = random.sample(prod_ids, min(random.randint(1,6), len(prod_ids)))
            subtot = 0.0
            for pid in chosen:
                pr   = pmap[pid]
                qty  = random.randint(1,4)
                disc = random.choice([0,0,0,5,10,15])
                lt   = round(qty * pr[5] * (1 - disc/100), 2)
                subtot += lt
                item_rows.append((str(uuid.uuid4()), oid, pid, pr[2], pr[3], qty, pr[5], disc, lt))
            ship = round(random.choice([0,0,4.90,5.90,7.90]), 2)
            d    = start + timedelta(days=random.randint(0,(now-start).days))
            ord_rows.append((oid, cid, d.strftime("%Y-%m-%d %H:%M:%S"), status,
                             round(subtot,2), ship, round(subtot+ship,2),
                             random.choice(PAYMENTS), random.choice(CITIES)))
        conn.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)", ord_rows)
        conn.executemany("INSERT INTO order_items VALUES (?,?,?,?,?,?,?,?,?)", item_rows)
        conn.commit()

        # ── Export CSV si demandé ─────────────────────────────────────────
        if fmt == "csv":
            csv_dir.mkdir(parents=True, exist_ok=True)
            tables = ["suppliers", "categories", "products", "customers", "orders", "order_items"]
            csv_files = []
            for table in tables:
                csv_path = csv_dir / f"{table}.csv"
                cur = conn.execute(f'SELECT * FROM "{table}"')
                cols = [d[0] for d in cur.description]
                rows_data = cur.fetchall()
                import csv as _csv
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = _csv.writer(f)
                    writer.writerow(cols)
                    writer.writerows(rows_data)
                csv_files.append((table, len(rows_data), csv_path))
                self.stdout.write(f"  Export {table}.csv — {len(rows_data):,} lignes")
            conn.close()
            # Supprime le SQLite temporaire
            sqlite_out.unlink(missing_ok=True)

            self.stdout.write(self.style.SUCCESS(
                f"\nFichiers CSV generes dans :\n  {csv_dir}\n\n"
                + "\n".join(f"  {t}.csv  ({n:,} lignes)" for t, n, _ in csv_files)
                + f"\n\nPour utiliser dans TransactIA :\n"
                  f"  > Choisir une source > Fichier CSV\n"
                  f"  > Choisissez l'un des fichiers ci-dessus (ex: orders.csv)\n"
                  f"  > Ou glissez-deposez directement"
            ))
        else:
            conn.close()
            size_kb = sqlite_out.stat().st_size // 1024
            self.stdout.write(self.style.SUCCESS(
                f"\nBase generee avec succes !\n"
                f"  Fichier   : {sqlite_out}\n"
                f"  Taille    : {size_kb} Ko\n"
                f"  Commandes : {n_ord:,} | Lignes : {len(item_rows):,} | Clients : {n_cust}\n\n"
                f"Pour l'utiliser dans TransactIA :\n"
                f"  > Choisir une source > Base SQLite > coller ce chemin :\n"
                f"  {sqlite_out}"
            ))

    def _schema(self, conn):
        conn.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE suppliers   (id TEXT PRIMARY KEY, name TEXT, email TEXT, phone TEXT, city TEXT, country TEXT);
        CREATE TABLE categories  (id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT);
        CREATE TABLE products    (id TEXT PRIMARY KEY, reference TEXT, name TEXT NOT NULL, category TEXT, category_id TEXT, price REAL, cost_price REAL, stock INTEGER DEFAULT 0, active INTEGER DEFAULT 1, supplier_id TEXT);
        CREATE TABLE customers   (id TEXT PRIMARY KEY, first_name TEXT, last_name TEXT, email TEXT, phone TEXT, city TEXT, age INTEGER, gender TEXT, segment TEXT, joined_date TEXT);
        CREATE TABLE orders      (id TEXT PRIMARY KEY, customer_id TEXT, order_date TEXT NOT NULL, status TEXT, subtotal REAL, shipping_cost REAL DEFAULT 0, total_amount REAL, payment_method TEXT, delivery_city TEXT);
        CREATE TABLE order_items (id TEXT PRIMARY KEY, order_id TEXT, product_id TEXT, product_name TEXT, category TEXT, quantity INTEGER, unit_price REAL, discount_pct INTEGER DEFAULT 0, line_total REAL);
        CREATE INDEX idx_orders_date     ON orders(order_date);
        CREATE INDEX idx_orders_status   ON orders(status);
        CREATE INDEX idx_orders_customer ON orders(customer_id);
        CREATE INDEX idx_items_order     ON order_items(order_id);
        CREATE INDEX idx_items_product   ON order_items(product_id);
        CREATE INDEX idx_products_cat    ON products(category);
        CREATE INDEX idx_customers_city  ON customers(city);
        """)
