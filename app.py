from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret123"

# ---------------- DB CONNECTION ----------------
def get_db():
    conn = sqlite3.connect("library.db")
    conn.row_factory = sqlite3.Row
    return conn

# ---------------- CREATE ADMIN ----------------
def create_admin():
    conn = get_db()
    cursor = conn.cursor()

    admin = cursor.execute(
        "SELECT * FROM users WHERE role='admin'"
    ).fetchone()

    if not admin:
        cursor.execute("""
        INSERT INTO users (username, password, role)
        VALUES (?, ?, ?)
        """, ("admin", "admin123", "admin"))
        conn.commit()

    conn.close()

create_admin()

# ---------------- HOME ----------------
@app.route("/")
def home():
    return redirect(url_for("dashboard"))

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))
    else:
        return redirect(url_for("student_dashboard"))

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        ).fetchone()
        conn.close()

        if user:
            session["username"] = user["username"]
            session["role"] = user["role"]

            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("student_dashboard"))

        return "Invalid Login"

    return render_template("login.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect('/')

# ---------------- ADD BOOK ----------------
@app.route("/add", methods=["GET", "POST"])
def add_book():
    if "role" not in session or session["role"] != "admin":
        return "Access Denied"

    if request.method == "POST":
        title = request.form["title"]
        author = request.form["author"]

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO books (title, author, status)
            VALUES (?, ?, ?)
        """, (title, author, "Available"))

        conn.commit()
        conn.close()

        return redirect(url_for("view_books"))

    return render_template("add_book.html")

# ---------------- VIEW BOOKS ----------------
@app.route("/books")
def view_books():
    if "username" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    books = conn.execute("SELECT * FROM books").fetchall()
    conn.close()
    return render_template("view_books.html", books=books)

# ---------------- ISSUE BOOK ----------------
@app.route("/issue", methods=["GET", "POST"])
def issue_book():
    if "role" not in session or session["role"] != "admin":
        return "Access Denied"

    conn = get_db()
    cursor = conn.cursor()

    books = cursor.execute("SELECT * FROM books WHERE status='Available'").fetchall()
    students = cursor.execute("SELECT username FROM users WHERE role='student'").fetchall()

    if request.method == "POST":
        book_id = request.form["book_id"]
        issued_to = request.form["issued_to"]
        issue_date = request.form["issue_date"]
        due_date = request.form["due_date"]

        cursor.execute("""
            INSERT INTO issued_books (book_id, issued_to, issue_date, due_date)
            VALUES (?, ?, ?, ?)
        """, (book_id, issued_to, issue_date, due_date))

        cursor.execute("UPDATE books SET status='Issued' WHERE book_id=?", (book_id,))

        conn.commit()
        conn.close()
        return redirect(url_for("issued_books"))

    return render_template("issue_book.html", books=books, students=students)


# ---------------- ISSUED BOOKS ----------------
@app.route("/issued")
def issued_books():
    if "username" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    issued = conn.execute("""
        SELECT books.title,
               issued_books.issued_to,
               issued_books.issue_date,
               issued_books.due_date
        FROM issued_books
        JOIN books ON books.book_id = issued_books.book_id
        WHERE issued_books.return_date IS NULL
    """).fetchall()
    conn.close()

    return render_template("issued_books.html", issued=issued)

# ---------------- RETURN BOOK ----------------
@app.route("/return", methods=["GET", "POST"])
def return_book():
    if "role" not in session or session["role"] != "admin":
        return "Access Denied"

    if request.method == "POST":
        book_id = request.form["book_id"]

        conn = get_db()
        cursor = conn.cursor()

        data = cursor.execute("""
            SELECT issue_id, due_date FROM issued_books 
            WHERE book_id=? AND return_date IS NULL
        """, (book_id,)).fetchone()

        if not data:
            conn.close()
            return "Book not issued"

        due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
        today = datetime.today().date()

        late_days = (today - due_date).days
        fine = max(0, late_days * 10)

        cursor.execute("""
            UPDATE issued_books 
            SET fine=?, return_date=?, fine_paid=0
            WHERE issue_id=?
        """, (fine, today, data["issue_id"]))

        cursor.execute("UPDATE books SET status='Available' WHERE book_id=?", (book_id,))

        conn.commit()
        conn.close()
        return redirect(url_for("view_books"))

    return render_template("return_book.html")

# ---------------- STUDENT ISSUES ----------------
@app.route("/student_issues")
def student_issues():
    if session.get("role") != "admin":
        return "Access Denied"

    conn = get_db()

    students = conn.execute("SELECT username FROM users WHERE role='student'").fetchall()
    selected_student = request.args.get("student")

    books_raw = conn.execute("""
        SELECT books.title,
               issued_books.issue_date,
               issued_books.due_date,
               issued_books.return_date,
               issued_books.fine,
               issued_books.fine_paid,
               issued_books.issue_id
        FROM issued_books
        JOIN books ON books.book_id = issued_books.book_id
        WHERE issued_books.issued_to = ?
    """, (selected_student,)).fetchall()

    conn.close()

    today = datetime.today().date()
    books = []

    for book in books_raw:
        due_date = datetime.strptime(book["due_date"], "%Y-%m-%d").date()

        if book["fine_paid"] == 1:
            fine = book["fine"]  # ✅ stop calculation
        else:
            late_days = (today - due_date).days
            fine = max(0, late_days * 10)

        books.append({**book, "fine": fine})

    return render_template("student_issues.html", students=students, books=books, selected_student=selected_student)

# ---------------- STUDENT DASHBOARD ----------------
@app.route("/student_dashboard")
def student_dashboard():
    if session.get("role") != "student":
        return "Access Denied"

    username = session["username"]

    conn = get_db()
    books_raw = conn.execute("""
        SELECT books.title,
               issued_books.issue_date,
               issued_books.due_date,
               issued_books.return_date,
               issued_books.fine,
               issued_books.fine_paid
        FROM issued_books
        JOIN books ON books.book_id = issued_books.book_id
        WHERE issued_books.issued_to = ?
    """, (username,)).fetchall()

    conn.close()

    today = datetime.today().date()
    books = []

    for book in books_raw:
        due_date = datetime.strptime(book["due_date"], "%Y-%m-%d").date()

        if book["fine_paid"] == 1:
            fine = book["fine"]
        else:
            late_days = (today - due_date).days
            fine = max(0, late_days * 10)

        books.append({**book, "fine": fine})

    return render_template("student_dashboard.html", my_books=books)

# ---------------- ADMIN DASHBOARD ----------------
@app.route("/admin_dashboard")
def admin_dashboard():
    if session.get("role") != "admin":
        return "Access Denied"

    conn = get_db()

    total_books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    available_books = conn.execute("SELECT COUNT(*) FROM books WHERE status='Available'").fetchone()[0]
    total_students = conn.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0]
    total_issued_books = conn.execute("SELECT COUNT(*) FROM books WHERE status='Issued'").fetchone()[0]

    rows = conn.execute("SELECT due_date, fine, fine_paid FROM issued_books").fetchall()
    conn.close()

    today = datetime.today().date()
    total_pending_fine = 0
    total_fine_collected = 0

    for row in rows:
        if row["fine_paid"] == 1:
            total_fine_collected += row["fine"]
        else:
            due_date = datetime.strptime(row["due_date"], "%Y-%m-%d").date()
            late_days = (today - due_date).days
            fine = max(0, late_days * 10)
            total_pending_fine += fine

    return render_template(
        "admin_dashboard.html",
        total_books=total_books,
        available_books=available_books,
        total_students=total_students,
        total_issued_books=total_issued_books,
        total_pending_fine=total_pending_fine,
        total_fine_collected=total_fine_collected
    )

# ---------------- MARK FINE PAID ----------------
@app.route("/mark_fine_paid/<int:issue_id>")
def mark_fine_paid(issue_id):
    if session.get("role") != "admin":
        return "Access Denied"

    conn = get_db()
    cursor = conn.cursor()

    data = cursor.execute("SELECT due_date FROM issued_books WHERE issue_id=?", (issue_id,)).fetchone()

    due_date = datetime.strptime(data["due_date"], "%Y-%m-%d").date()
    today = datetime.today().date()

    late_days = (today - due_date).days
    final_fine = max(0, late_days * 10)

    cursor.execute("""
        UPDATE issued_books
        SET fine=?, fine_paid=1
        WHERE issue_id=?
    """, (final_fine, issue_id))

    conn.commit()
    conn.close()

    return redirect(url_for("student_issues"))

# ---------------- VIEW USERS ----------------
@app.route("/users")
def users():
    if session.get("role") != "admin":
        return "Access Denied"

    conn = get_db()
    users = conn.execute("SELECT id, username, role FROM users").fetchall()
    conn.close()

    return render_template("users.html", users=users)

# ---------------- ADD USER ----------------
@app.route("/add_user", methods=["GET", "POST"])
def add_user():
    if session.get("role") != "admin":
        return "Access Denied"

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        conn = get_db()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (username, password, role)
            )
            conn.commit()
        except:
            conn.close()
            return "Username already exists"

        conn.close()
        return redirect(url_for("users"))

    return render_template("add_user.html")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)