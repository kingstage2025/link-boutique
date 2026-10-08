from __future__ import annotations

import os
import re
import sqlite3
import uuid
from functools import wraps
from pathlib import Path
from xml.sax.saxutils import escape

from flask import Flask, flash, g, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.environ.get("DATABASE_URL")
DATABASE = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "linkboutik.db"))
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}

app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-this-secret"),
                  DATABASE=DATABASE, DATABASE_URL=DATABASE_URL, MAX_CONTENT_LENGTH=MAX_UPLOAD,
                  ADMIN_EMAIL=os.environ.get("ADMIN_EMAIL", "admin@linkboutik.local"))
CATEGORIES = ("Mode", "Beauté", "Maison", "Alimentation", "Services", "Autres")
SLUG_RE = re.compile(r"[^a-z0-9]+")


def get_db():
    if "db" not in g:
        if app.config["DATABASE_URL"]:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            url = app.config["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
            g.db = psycopg2.connect(url, cursor_factory=RealDictCursor)
        else:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def execute(sql: str, parameters=()):
    if app.config["DATABASE_URL"]:
        sql = sql.replace("?", "%s")
        cursor = get_db().cursor()
        cursor.execute(sql, parameters)
        return cursor
    return get_db().execute(sql, parameters)


def commit():
    get_db().commit()


def database_errors():
    if app.config["DATABASE_URL"]:
        import psycopg2
        return (sqlite3.Error, psycopg2.Error)
    return (sqlite3.Error,)


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = get_db()
    statements = [
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT FALSE, plan TEXT NOT NULL DEFAULT 'free',
            referral_code TEXT UNIQUE, referred_by INTEGER, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS shops (
            id INTEGER PRIMARY KEY, user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL, description TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '', whatsapp TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
            hours TEXT NOT NULL DEFAULT '', logo_url TEXT NOT NULL DEFAULT '', plan TEXT NOT NULL DEFAULT 'free',
            reported BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY, shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
            name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT 'Autres',
            price NUMERIC NOT NULL CHECK(price > 0), stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
            image_url TEXT NOT NULL DEFAULT '', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY, shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id), product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0), unit_price NUMERIC NOT NULL CHECK(unit_price > 0),
            customer_name TEXT NOT NULL, customer_phone TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'new', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY, shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
            name TEXT NOT NULL, phone TEXT NOT NULL, email TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '', balance NUMERIC NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(shop_id, phone))""",
        """CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY, shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
            customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL, number TEXT NOT NULL,
            description TEXT NOT NULL, amount NUMERIC NOT NULL CHECK(amount > 0),
            status TEXT NOT NULL DEFAULT 'unpaid', due_date TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    ]
    if app.config["DATABASE_URL"]:
        statements = [s.replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY").replace("BOOLEAN NOT NULL DEFAULT FALSE", "BOOLEAN NOT NULL DEFAULT FALSE") for s in statements]
        with db.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
            # Keep databases created by an earlier MVP schema compatible.
            migrations = (
                ("users", "is_admin BOOLEAN NOT NULL DEFAULT FALSE"),
                ("users", "plan TEXT NOT NULL DEFAULT 'free'"),
                ("users", "referral_code TEXT"),
                ("users", "referred_by INTEGER"),
                ("shops", "description TEXT NOT NULL DEFAULT ''"),
                ("shops", "phone TEXT NOT NULL DEFAULT ''"),
                ("shops", "whatsapp TEXT NOT NULL DEFAULT ''"),
                ("shops", "location TEXT NOT NULL DEFAULT ''"),
                ("shops", "hours TEXT NOT NULL DEFAULT ''"),
                ("shops", "logo_url TEXT NOT NULL DEFAULT ''"),
                ("shops", "plan TEXT NOT NULL DEFAULT 'free'"),
                ("shops", "reported BOOLEAN NOT NULL DEFAULT FALSE"),
                ("products", "description TEXT NOT NULL DEFAULT ''"),
                ("products", "category TEXT NOT NULL DEFAULT 'Autres'"),
                ("products", "price NUMERIC NOT NULL DEFAULT 1 CHECK(price > 0)"),
                ("products", "stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0)"),
                ("products", "image_url TEXT NOT NULL DEFAULT ''"),
            )
            for table, column in migrations:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column}")
    else:
        db.executescript(";\n".join(statements) + ";")
        # Migrate the original MVP database without destroying any data.
        for table, column in (("users", "is_admin BOOLEAN NOT NULL DEFAULT FALSE"),
                              ("users", "plan TEXT NOT NULL DEFAULT 'free'"),
                              ("users", "referral_code TEXT"), ("users", "referred_by INTEGER"),
                              ("shops", "plan TEXT NOT NULL DEFAULT 'free'"),
                              ("shops", "reported BOOLEAN NOT NULL DEFAULT FALSE")):
            try:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column}")
            except sqlite3.OperationalError:
                pass
    db.commit()


@app.before_request
def prepare_request():
    init_db()
    g.user = None
    if session.get("user_id"):
        g.user = execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()


@app.template_filter("xaf")
def format_xaf(value):
    return f"{float(value):,.0f}".replace(",", " ") + " FCFA"


def slugify(value):
    return SLUG_RE.sub("-", value.strip().lower()).strip("-")[:70]


def current_shop():
    return execute("SELECT * FROM shops WHERE user_id = ?", (g.user["id"],)).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            flash("Connectez-vous pour accéder à votre espace.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user or not (g.user["is_admin"] or g.user["email"] == app.config["ADMIN_EMAIL"]):
            return render_template("not_found.html"), 404
        return view(*args, **kwargs)
    return wrapped


def shop_values():
    name = request.form.get("name", "").strip()
    slug = slugify(request.form.get("slug", "") or name)
    if not 2 <= len(name) <= 80 or not slug:
        return None, "Le nom doit contenir entre 2 et 80 caractères."
    return {"name": name, "slug": slug, "description": request.form.get("description", "").strip()[:500],
            "phone": request.form.get("phone", "").strip()[:40], "whatsapp": request.form.get("whatsapp", "").strip()[:40],
            "location": request.form.get("location", "").strip()[:120], "hours": request.form.get("hours", "").strip()[:120],
            "logo_url": request.form.get("logo_url", "").strip()[:500]}, None


def save_upload(file):
    if not file or not file.filename:
        return ""
    extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Formats acceptés : JPG, PNG, WEBP ou GIF.")
    if file.content_length and file.content_length > MAX_UPLOAD:
        raise ValueError("L'image ne doit pas dépasser 5 Mo.")
    filename = f"{uuid.uuid4().hex}.{extension}"
    file.save(UPLOAD_DIR / secure_filename(filename))
    return url_for("uploaded_file", filename=filename)


@app.route("/")
def index():
    return render_template("landing.html")


@app.route("/register", methods=("GET", "POST"))
def register():
    if request.method == "POST":
        email, password = request.form.get("email", "").strip().lower(), request.form.get("password", "")
        referral = request.form.get("ref", "").strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Saisissez une adresse e-mail valide.", "danger")
        elif len(password) < 8:
            flash("Le mot de passe doit contenir au moins 8 caractères.", "danger")
        else:
            referrer = execute("SELECT id FROM users WHERE referral_code = ?", (referral,)).fetchone() if referral else None
            try:
                code = uuid.uuid4().hex[:8].upper()
                execute("INSERT INTO users (email,password_hash,referral_code,referred_by) VALUES (?,?,?,?)",
                        (email, generate_password_hash(password), code, referrer["id"] if referrer else None))
                commit()
                flash("Compte créé. Connectez-vous pour créer votre boutique.", "success")
                return redirect(url_for("login"))
            except Exception as error:
                if "unique" in str(error).lower():
                    flash("Cette adresse e-mail est déjà utilisée.", "danger")
                else:
                    raise
    return render_template("login.html", mode="register")


@app.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        user = execute("SELECT * FROM users WHERE email = ?", (request.form.get("email", "").strip().lower(),)).fetchone()
        if not user or not check_password_hash(user["password_hash"], request.form.get("password", "")):
            flash("E-mail ou mot de passe incorrect.", "danger")
        else:
            session.clear(); session["user_id"] = user["id"]; return redirect(url_for("dashboard"))
    return render_template("login.html", mode="login")


@app.post("/logout")
def logout():
    session.clear(); return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    shop = current_shop()
    products = execute("SELECT * FROM products WHERE shop_id=? ORDER BY id DESC", (shop["id"],)).fetchall() if shop else ()
    orders = execute("SELECT * FROM orders WHERE shop_id=? ORDER BY id DESC LIMIT 50", (shop["id"],)).fetchall() if shop else ()
    customers = execute("SELECT * FROM customers WHERE shop_id=? ORDER BY id DESC", (shop["id"],)).fetchall() if shop else ()
    invoices = execute("SELECT * FROM invoices WHERE shop_id=? ORDER BY id DESC", (shop["id"],)).fetchall() if shop else ()
    return render_template("dashboard.html", shop=shop, products=products, orders=orders, customers=customers,
                           invoices=invoices, categories=CATEGORIES)


@app.post("/shop/create")
@login_required
def create_shop():
    values, error = shop_values()
    if current_shop(): error = "Vous avez déjà une boutique."
    if error: flash(error, "danger")
    else:
        try:
            execute("INSERT INTO shops (user_id,name,slug,description,phone,whatsapp,location,hours,logo_url,plan) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (g.user["id"], *values.values(), g.user["plan"])); commit()
            flash("Votre boutique est créée. Ajoutez votre premier produit !", "success")
        except Exception as exc:
            if "unique" in str(exc).lower(): flash("Ce lien de boutique est déjà pris.", "danger")
            else: raise
    return redirect(url_for("dashboard"))


@app.post("/shop/update")
@login_required
def update_shop():
    shop, (values, error) = current_shop(), shop_values()
    if shop and not error:
        try:
            execute("UPDATE shops SET name=?,slug=?,description=?,phone=?,whatsapp=?,location=?,hours=?,logo_url=? WHERE id=?",
                    (*values.values(), shop["id"])); commit(); flash("Informations enregistrées.", "success")
        except Exception:
            flash("Ce lien de boutique est déjà pris.", "danger")
    elif error: flash(error, "danger")
    return redirect(url_for("dashboard"))


@app.post("/products/create")
@login_required
def create_product():
    shop = current_shop()
    try:
        price, stock = float(request.form.get("price", 0)), int(request.form.get("stock", 0))
        image = save_upload(request.files.get("image"))
    except (ValueError, TypeError) as error:
        flash(str(error) or "Produit invalide.", "danger"); return redirect(url_for("dashboard"))
    name, category = request.form.get("name", "").strip(), request.form.get("category", "Autres")
    limit = 50 if g.user["plan"] == "pro" else 10
    if not shop or not name or price <= 0 or stock < 0 or category not in CATEGORIES:
        flash("Produit invalide.", "danger")
    elif execute("SELECT COUNT(*) FROM products WHERE shop_id=?", (shop["id"],)).fetchone()[0] >= limit:
        flash(f"La formule actuelle est limitée à {limit} produits.", "warning")
    else:
        image = image or request.form.get("image_url", "").strip()[:500]
        execute("INSERT INTO products (shop_id,name,description,category,price,stock,image_url) VALUES (?,?,?,?,?,?,?)",
                (shop["id"], name, request.form.get("description", "").strip()[:500], category, price, stock, image))
        commit(); flash("Produit ajouté au catalogue.", "success")
    return redirect(url_for("dashboard"))


@app.post("/products/<int:product_id>/delete")
@login_required
def delete_product(product_id):
    shop = current_shop()
    if shop: execute("DELETE FROM products WHERE id=? AND shop_id=?", (product_id, shop["id"])); commit()
    return redirect(url_for("dashboard"))


@app.route("/shop/<slug>", methods=("GET", "POST"))
def public_shop(slug):
    shop = execute("SELECT * FROM shops WHERE slug=?", (slug,)).fetchone()
    if not shop: return render_template("not_found.html"), 404
    if request.method == "POST":
        product = execute("SELECT * FROM products WHERE id=? AND shop_id=?", (request.form.get("product_id", type=int), shop["id"])).fetchone()
        quantity, name, phone = request.form.get("quantity", type=int), request.form.get("customer_name", "").strip(), request.form.get("customer_phone", "").strip()
        if not product or not name or not phone or not quantity or quantity < 1 or quantity > product["stock"]:
            flash("Produit, quantité, nom et téléphone valides sont requis.", "danger")
        elif execute("UPDATE products SET stock=stock-? WHERE id=? AND stock>=?", (quantity, product["id"], quantity)).rowcount != 1:
            flash("Stock insuffisant.", "danger")
        else:
            execute("INSERT INTO orders (shop_id,product_id,product_name,quantity,unit_price,customer_name,customer_phone,note) VALUES (?,?,?,?,?,?,?,?)",
                    (shop["id"], product["id"], product["name"], quantity, product["price"], name, phone, request.form.get("note", "")[:300]))
            execute("INSERT INTO customers (shop_id,name,phone) VALUES (?,?,?) ON CONFLICT(shop_id,phone) DO UPDATE SET name=excluded.name",
                    (shop["id"], name, phone)); commit(); flash("Commande envoyée !", "success")
            return redirect(url_for("public_shop", slug=slug))
    return render_template("public_shop.html", shop=shop, products=execute("SELECT * FROM products WHERE shop_id=? ORDER BY id DESC", (shop["id"],)).fetchall())


@app.route("/discover")
def discover():
    query = request.args.get("q", "").strip()
    like = f"%{query}%"
    try:
        shops = execute("SELECT * FROM shops WHERE name LIKE ? OR description LIKE ? ORDER BY id DESC LIMIT 30", (like, like)).fetchall()
        products = execute("SELECT p.*,s.name AS shop_name,s.slug AS shop_slug FROM products p JOIN shops s ON s.id=p.shop_id WHERE p.name LIKE ? OR p.description LIKE ? LIMIT 50", (like, like)).fetchall()
    except database_errors():
        app.logger.exception("Public discovery query failed")
        flash("La découverte est temporairement indisponible. Réessaie dans un instant.", "warning")
        shops, products = [], []
    return render_template("discover.html", shops=shops, products=products, query=query)


@app.route("/clients", methods=("GET", "POST"))
@login_required
def clients():
    shop = current_shop()
    if request.method == "POST" and shop:
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        try:
            balance = float(request.form.get("balance", 0) or 0)
        except ValueError:
            balance = -1
        if not name or not phone or balance < 0:
            flash("Nom, téléphone et solde valide sont requis.", "danger")
        else:
            existing = execute(
                "SELECT id FROM customers WHERE shop_id=? AND phone=?",
                (shop["id"], phone),
            ).fetchone()
            if existing:
                execute(
                    """
                    UPDATE customers SET name=?, email=?, notes=?, balance=?
                    WHERE id=? AND shop_id=?
                    """,
                    (
                        name,
                        request.form.get("email", "")[:120],
                        request.form.get("notes", "")[:500],
                        balance,
                        existing["id"],
                        shop["id"],
                    ),
                )
                flash("Client mis à jour.", "success")
            else:
                execute(
                    """
                    INSERT INTO customers (shop_id,name,phone,email,notes,balance)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (
                        shop["id"],
                        name,
                        phone,
                        request.form.get("email", "")[:120],
                        request.form.get("notes", "")[:500],
                        balance,
                    ),
                )
                flash("Client enregistré.", "success")
            commit()
    return redirect(url_for("dashboard"))


@app.post("/invoices/create")
@login_required
def create_invoice():
    shop = current_shop()
    if shop:
        execute("INSERT INTO invoices (shop_id,customer_id,number,description,amount,due_date) VALUES (?,?,?,?,?,?)",
                (shop["id"], request.form.get("customer_id") or None, f"FAC-{uuid.uuid4().hex[:6].upper()}",
                 request.form["description"][:300], float(request.form["amount"]), request.form.get("due_date", "")))
        commit(); flash("Facture créée.", "success")
    return redirect(url_for("dashboard"))


@app.post("/invoices/<int:invoice_id>/paid")
@login_required
def mark_invoice_paid(invoice_id):
    shop = current_shop()
    if shop: execute("UPDATE invoices SET status='paid' WHERE id=? AND shop_id=?", (invoice_id, shop["id"])); commit()
    return redirect(url_for("dashboard"))


@app.route("/pricing")
def pricing(): return render_template("pricing.html")


@app.route("/referral")
@login_required
def referral():
    return render_template("referral.html", code=g.user["referral_code"], link=url_for("register", ref=g.user["referral_code"], _external=True))


@app.route("/admin")
@admin_required
def admin():
    return render_template("admin.html", users=execute("SELECT * FROM users ORDER BY id DESC").fetchall(),
                           shops=execute("SELECT s.*,u.email FROM shops s JOIN users u ON u.id=s.user_id ORDER BY s.id DESC").fetchall(),
                           products=execute("SELECT p.*,s.name shop_name FROM products p JOIN shops s ON s.id=p.shop_id ORDER BY p.id DESC").fetchall(),
                           stats={"users": execute("SELECT COUNT(*) FROM users").fetchone()[0], "shops": execute("SELECT COUNT(*) FROM shops").fetchone()[0],
                                  "products": execute("SELECT COUNT(*) FROM products").fetchone()[0], "orders": execute("SELECT COUNT(*) FROM orders").fetchone()[0]})


@app.post("/admin/users/<int:user_id>/plan")
@admin_required
def admin_plan(user_id):
    plan = "pro" if request.form.get("plan") == "pro" else "free"
    execute("UPDATE users SET plan=? WHERE id=?", (plan, user_id)); execute("UPDATE shops SET plan=? WHERE user_id=?", (plan, user_id)); commit()
    return redirect(url_for("admin"))


@app.post("/admin/shops/<int:shop_id>/report")
@admin_required
def admin_report(shop_id):
    execute("UPDATE shops SET reported=NOT reported WHERE id=?", (shop_id,)); commit(); return redirect(url_for("admin"))


@app.post("/shop/<slug>/report")
def report_shop(slug):
    execute("UPDATE shops SET reported=TRUE WHERE slug=?", (slug,)); commit()
    flash("Merci, le signalement a été transmis.", "success")
    return redirect(url_for("public_shop", slug=slug))


@app.post("/admin/products/<int:product_id>/delete")
@admin_required
def admin_delete_product(product_id):
    execute("DELETE FROM products WHERE id=?", (product_id,)); commit()
    return redirect(url_for("admin"))


@app.route("/uploads/<path:filename>")
def uploaded_file(filename): return send_from_directory(UPLOAD_DIR, filename)


@app.route("/sitemap.xml")
def sitemap():
    try:
        slugs = execute("SELECT slug FROM shops ORDER BY id DESC").fetchall()
    except database_errors():
        app.logger.exception("Sitemap query failed")
        return "Sitemap temporairement indisponible.", 503, {"Content-Type": "text/plain; charset=utf-8"}
    urls = [
        f"<url><loc>{escape(url_for('index', _external=True))}</loc></url>",
        f"<url><loc>{escape(url_for('discover', _external=True))}</loc></url>",
    ]
    urls.extend(
        f"<url><loc>{escape(url_for('public_shop', slug=shop['slug'], _external=True))}</loc></url>"
        for shop in slugs
    )
    body = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(urls) + "</urlset>"
    return body, 200, {"Content-Type": "application/xml"}


@app.route("/robots.txt")
def robots(): return "User-agent: *\nAllow: /\nSitemap: " + url_for("sitemap", _external=True) + "\n", 200, {"Content-Type": "text/plain"}


@app.errorhandler(413)
def too_large(_error):
    flash("Image trop volumineuse (5 Mo maximum).", "danger"); return redirect(url_for("dashboard"))


@app.errorhandler(404)
def not_found(_error): return render_template("not_found.html"), 404


if __name__ == "__main__":
    app.run(debug=True)
