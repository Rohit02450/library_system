from flask import Flask, render_template, redirect, url_for, request
from config import Config
from models import db, Book, Member, Transaction
from forms import BookForm, MemberForm, ImportForm
from datetime import datetime
import requests
import os

# Rent fee rules
FREE_DAYS = 14
PER_DAY_FEE = 2.0

# Folder settings
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

print("TEMPLATE FOLDER:", os.path.join(BASE_DIR, "templates"))
print("STATIC FOLDER:", os.path.join(BASE_DIR, "static"))

app.config.from_object(Config)
db.init_app(app)

# Auto-create DB tables
with app.app_context():
    db.create_all()


# ------------------------------------------------------
# HOME
# ------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ------------------------------------------------------
# BOOK CRUD
# ------------------------------------------------------

@app.route("/books")
def books():
    q = request.args.get("q", "")
    if q:
        results = Book.query.filter(
            (Book.title.ilike(f"%{q}%")) |
            (Book.authors.ilike(f"%{q}%"))
        ).all()
    else:
        results = Book.query.all()

    return render_template("books.html", books=results)


@app.route("/books/add", methods=["GET", "POST"])
def add_book():
    form = BookForm()
    if form.validate_on_submit():
        b = Book(
            title=form.title.data,
            authors=form.authors.data,
            isbn=form.isbn.data,
            publisher=form.publisher.data,
            num_pages=form.num_pages.data,
            stock=form.stock.data
        )
        db.session.add(b)
        db.session.commit()
        return redirect(url_for("books"))

    return render_template("add_book.html", form=form)


@app.route("/books/edit/<int:id>", methods=["GET", "POST"])
def edit_book(id):
    book = Book.query.get_or_404(id)
    form = BookForm(obj=book)

    if form.validate_on_submit():
        book.title = form.title.data
        book.authors = form.authors.data
        book.isbn = form.isbn.data
        book.publisher = form.publisher.data
        book.num_pages = form.num_pages.data
        book.stock = form.stock.data

        db.session.commit()
        return redirect(url_for("books"))

    return render_template("add_book.html", form=form)


@app.route("/books/delete/<int:id>")
def delete_book(id):
    book = Book.query.get_or_404(id)
    db.session.delete(book)
    db.session.commit()
    return redirect(url_for("books"))


# ------------------------------------------------------
# MEMBER CRUD
# ------------------------------------------------------

@app.route("/members")
def members():
    results = Member.query.all()
    return render_template("members.html", members=results)


@app.route("/members/add", methods=["GET", "POST"])
def add_member():
    form = MemberForm()
    if form.validate_on_submit():
        m = Member(
            name=form.name.data,
            email=form.email.data,
            phone=form.phone.data
        )
        db.session.add(m)
        db.session.commit()
        return redirect(url_for("members"))

    return render_template("add_member.html", form=form)


@app.route("/members/edit/<int:id>", methods=["GET", "POST"])
def edit_member(id):
    member = Member.query.get_or_404(id)
    form = MemberForm(obj=member)

    if form.validate_on_submit():
        member.name = form.name.data
        member.email = form.email.data
        member.phone = form.phone.data
        db.session.commit()
        return redirect(url_for("members"))

    return render_template("add_member.html", form=form)


@app.route("/members/delete/<int:id>")
def delete_member(id):
    member = Member.query.get_or_404(id)
    db.session.delete(member)
    db.session.commit()
    return redirect(url_for("members"))


# ------------------------------------------------------
# ISSUE BOOK
# ------------------------------------------------------

@app.route("/issue", methods=["GET", "POST"])
def issue():
    if request.method == "POST":
        member_id = int(request.form["member_id"])
        book_id = int(request.form["book_id"])

        member = Member.query.get(member_id)
        book = Book.query.get(book_id)

        if not member or not book:
            return "Invalid Member or Book"

        # BLOCK ISSUE IF DEBT > Rs. 500
        if member.outstanding_debt > 500:
            return "Cannot issue book. Member's outstanding debt is more than ₹500."

        # BLOCK ISSUE IF NO STOCK
        if book.stock <= 0:
            return "No stock available."

        # ISSUE THE BOOK
        book.stock -= 1
        tx = Transaction(
            member_id=member_id,
            book_id=book_id,
            type="issue",
            issued_at=datetime.utcnow()
        )

        db.session.add(tx)
        db.session.commit()

        return redirect(url_for("index"))

    members = Member.query.all()
    books = Book.query.all()
    return render_template("issue.html", members=members, books=books)


# ------------------------------------------------------
# RETURN BOOK + RENT FEE
# ------------------------------------------------------

@app.route("/return", methods=["GET", "POST"])
def return_book():
    if request.method == "POST":
        member_id = int(request.form["member_id"])
        book_id = int(request.form["book_id"])

        issue_tx = Transaction.query.filter_by(
            member_id=member_id, book_id=book_id, type="issue"
        ).order_by(Transaction.issued_at.desc()).first()

        if not issue_tx:
            return "No issue record found for this member and book."

        now = datetime.utcnow()
        days = (now - issue_tx.issued_at).days
        late_days = max(0, days - FREE_DAYS)
        fee = late_days * PER_DAY_FEE

        ret = Transaction(
            member_id=member_id,
            book_id=book_id,
            type="return",
            returned_at=now,
            fee=fee
        )

        book = Book.query.get(book_id)
        book.stock += 1

        member = Member.query.get(member_id)
        member.outstanding_debt += fee

        db.session.add(ret)
        db.session.commit()

        return f"Returned successfully! Rent Fee Charged: ₹{fee}"

    members = Member.query.all()
    books = Book.query.all()
    return render_template("return.html", members=members, books=books)


# ------------------------------------------------------
# FRAPPE IMPORT API
# ------------------------------------------------------

@app.route("/import", methods=["GET", "POST"])
def import_data():
    form = ImportForm()

    if form.validate_on_submit():
        count = form.count.data
        filters = {}

        if form.title.data:
            filters["title"] = form.title.data
        if form.authors.data:
            filters["authors"] = form.authors.data

        imported = 0
        page = 1

        while imported < count:
            params = {"page": page}
            params.update(filters)

            r = requests.get("https://frappe.io/api/method/frappe-library", params=params)
            items = r.json().get("message", [])

            if not items:
                break

            for item in items:
                if imported >= count:
                    break

                b = Book(
                    title=item.get("title"),
                    authors=item.get("authors"),
                    isbn=item.get("isbn"),
                    publisher=item.get("publisher"),
                    num_pages=item.get("num_pages"),
                    stock=1
                )

                db.session.add(b)
                db.session.commit()
                imported += 1

            page += 1

        return f"Imported {imported} books."

    return render_template("import.html", form=form)


# ------------------------------------------------------
# RUN SERVER
# ------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
