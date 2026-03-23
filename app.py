from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
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
        cursor = conn.cursor()
        
        user = cursor.execute(
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

    
    return render_template("login.html",error="Invalid login")

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

    search = request.args.get("search", "")

    conn = get_db()

    if search:
        books = conn.execute("""
            SELECT * FROM books
            WHERE title LIKE ? OR author LIKE ?
        """, ('%' + search + '%', '%' + search + '%')).fetchall()
    else:
        books = conn.execute("SELECT * FROM books").fetchall()

    conn.close()

    return render_template("view_books.html", books=books, search=search)

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

def add_real_books_safe():
    conn = get_db()
    cursor = conn.cursor()

    books = [
        ("The Alchemist", "Paulo Coelho"),
        ("Harry Potter 1", "J.K. Rowling"),
        ("Harry Potter 2", "J.K. Rowling"),
        ("Harry Potter 3", "J.K. Rowling"),
        ("The Hobbit", "J.R.R. Tolkien"),
        ("The Lord of the Rings", "J.R.R. Tolkien"),
        ("1984", "George Orwell"),
        ("Animal Farm", "George Orwell"),
        ("The Great Gatsby", "F. Scott Fitzgerald"),
        ("To Kill a Mockingbird", "Harper Lee"),
        ("Pride and Prejudice", "Jane Austen"),
        ("Moby Dick", "Herman Melville"),
        ("War and Peace", "Leo Tolstoy"),
        ("Crime and Punishment", "Dostoevsky"),
        ("Brave New World", "Aldous Huxley"),
        ("The Kite Runner", "Khaled Hosseini"),
        ("The Book Thief", "Markus Zusak"),
        ("The Da Vinci Code", "Dan Brown"),
        ("Inferno", "Dan Brown"),
        ("Angels and Demons", "Dan Brown"),
        ("Digital Fortress", "Dan Brown"),
        ("Deception Point", "Dan Brown"),
        ("The Hunger Games", "Suzanne Collins"),
        ("Catching Fire", "Suzanne Collins"),
        ("Mockingjay", "Suzanne Collins"),
        ("Twilight", "Stephenie Meyer"),
        ("New Moon", "Stephenie Meyer"),
        ("Eclipse", "Stephenie Meyer"),
        ("Breaking Dawn", "Stephenie Meyer"),
        ("The Fault in Our Stars", "John Green"),
        ("Looking for Alaska", "John Green"),
        ("Paper Towns", "John Green"),
        ("Rich Dad Poor Dad", "Robert Kiyosaki"),
        ("Think and Grow Rich", "Napoleon Hill"),
        ("Atomic Habits", "James Clear"),
        ("Ikigai", "Hector Garcia"),
        ("Deep Work", "Cal Newport"),
        ("Zero to One", "Peter Thiel"),
        ("The Lean Startup", "Eric Ries"),
        ("Sapiens", "Yuval Noah Harari"),
        ("Homo Deus", "Yuval Noah Harari"),
        ("The Psychology of Money", "Morgan Housel"),
        ("Can't Hurt Me", "David Goggins"),
        ("The Subtle Art of Not Giving a F*ck", "Mark Manson"),
        ("The 7 Habits", "Stephen Covey"),
        ("How to Win Friends", "Dale Carnegie"),
        ("The Monk Who Sold His Ferrari", "Robin Sharma"),
        ("Wings of Fire", "A.P.J Abdul Kalam"),
        ("Ignited Minds", "A.P.J Abdul Kalam"),
        ("India 2020", "A.P.J Abdul Kalam"),
        ("The White Tiger", "Aravind Adiga"),
        ("Train to Pakistan", "Khushwant Singh"),
        ("The Guide", "R.K Narayan"),
        ("Malgudi Days", "R.K Narayan"),
        ("Gitanjali", "Rabindranath Tagore"),
        ("Godan", "Premchand"),
        ("Half Girlfriend", "Chetan Bhagat"),
        ("2 States", "Chetan Bhagat"),
        ("Five Point Someone", "Chetan Bhagat"),
        ("One Night @ Call Center", "Chetan Bhagat"),
        ("3 Mistakes of My Life", "Chetan Bhagat"),
        ("Immortals of Meluha", "Amish Tripathi"),
        ("Secret of Nagas", "Amish Tripathi"),
        ("Oath of Vayuputras", "Amish Tripathi"),
        ("Sita: Warrior of Mithila", "Amish Tripathi"),
        ("Raavan", "Amish Tripathi"),
        ("The Hidden Hindu", "Akshat Gupta"),
        ("Life's Amazing Secrets", "Gaur Gopal Das"),
        ("Do Epic Shit", "Ankur Warikoo"),
        ("Get Epic Shit Done", "Ankur Warikoo"),
        ("You Can Win", "Shiv Khera"),
        ("Stay Hungry Stay Foolish", "Rashmi Bansal"),
        ("The Namesake", "Jhumpa Lahiri"),
        ("Interpreter of Maladies", "Jhumpa Lahiri"),
        ("A Suitable Boy", "Vikram Seth"),
        ("The Palace of Illusions", "Chitra Banerjee"),
    ]

    # Check existing books (duplicate avoid)
    existing_titles = [row[0] for row in cursor.execute("SELECT title FROM books").fetchall()]

    for title, author in books:
        if title not in existing_titles:
            cursor.execute(
                "INSERT INTO books (title, author, status) VALUES (?, ?, ?)",
                (title, author, "Available")
            )

    conn.commit()
    conn.close() 
    
# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))