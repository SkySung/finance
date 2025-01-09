import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    holding = db.execute("SELECT * FROM holding WHERE user_id = ?", session["user_id"])
    cash_table = db.execute("SELECT cash from users WHERE id = ?", session["user_id"])
    cash = cash_table[0]["cash"]
    total_market_value = float(cash)
    for row in holding:
        lookup_result = lookup(row["symbol"])
        # if lookup_result somehow fail, the UI shouldn't be crashed.
        row["price"] = float(lookup_result["price"]) if lookup_result else 0
        row["total"] = int(row["shares"]) * float(row["price"])
        total_market_value += float(row["total"])

    return render_template("index.html", holding=holding, cash=cash, total=total_market_value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        try:
            shares = int(shares)
            if shares <= 0:
                flash("Positive number only.")
                return apology("Positive numbers only.")
            else:
                pass
        except:
            flash("Numbers only")
            return apology("Numbers only.")

        result = lookup(symbol)
        if result is None:
            flash("There is no result. Please try again.", 400)
            return apology("There is no result. Please try again.", 400)
        result_price = float(result["price"])

        # should check if the result_name effect to SQL Syntax
        result_name = result["name"]
        result_symbol = result["symbol"]

        total_price = result_price * shares
        rows = db.execute("SELECT cash from users WHERE id = ?", session["user_id"])
        user_cash = float(rows[0]["cash"])
        balance_check = bool(False)
        balance_check = user_cash > total_price
        if balance_check is False:
            flash("Cash is not enough, please adjust numbers of buying shares")
            return render_template("buy.html")

        # All good, buy process start
        cash_update = user_cash - total_price
        db.execute("UPDATE users SET cash = ? WHERE id = ?", cash_update, session["user_id"])
        db.execute("INSERT INTO history (user_id, symbol, shares, price, type) VALUES (?,?,?,?,?)", session["user_id"], result_symbol, shares, result_price, "buy")
        # TABLE history finish

        # TABLE holding start
        holding_check = db.execute("SELECT * FROM holding WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)
        if len(holding_check) == 0:
            db.execute("INSERT INTO holding (user_id, symbol, name, shares) VALUES (?,?,?,?)", session["user_id"], result_symbol, result_name, shares)
        else:
            update_shares = int(holding_check[0]["shares"]) + shares
            db.execute("UPDATE holding SET shares = ? WHERE user_id = ? AND symbol = ?", update_shares, session["user_id"], symbol)
        flash(f"Buy {shares} shares of {symbol} at ${result_price:.2f}.")
        flash(f"Total amount is ${total_price}")
        return redirect("/")
    # Via GET
    else:
        return render_template("buy.html",)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute("SELECT * FROM history WHERE user_id = ? ORDER BY transacted", session["user_id"])

    return render_template("history.html", rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        result = lookup(symbol)
        # frontend will be "There is no result. Please try again."
        if result is None:
            return apology("Symbol invalid", 400)
        else:
            return render_template("quoted.html", result=result)
    # Via GET, render the unqouted template
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        username_check = db.execute("SELECT username FROM users WHERE username = ?", username)
        if not len(username_check) == 0:
            return apology("username exist. Try another name", 400)
        if username == "" or password == "" or confirmation == "":
            return apology("Some blank here?", 400)
        if not password == confirmation:
            return apology("password and confirmation not match", 400)
        hash_password = generate_password_hash(password)
        db.execute("INSERT INTO users (username,hash) VALUES (?,?)", username, hash_password)
        rows = db.execute("SELECT id from users WHERE username = ?", username)
        if rows:
            session["user_id"] = rows[0]["id"]
        flash('Register success. You now have $10,000 as starting fund.')

        return redirect("/", )
    # Via GET with no session
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    rows = db.execute("SELECT symbol FROM holding WHERE user_id = ?", session["user_id"])
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        try:
            shares = int(shares)
            if shares <= 0:
                flash("Positive number only.")
                return apology("Positive numbers only.")
            else:
                pass
        except:
            flash("Numbers only")
            return apology("Numbers only.")

        holding_shares = db.execute("SELECT shares FROM holding WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)
        holding_shares = int(holding_shares[0]["shares"])
        shares_check = bool(False)
        shares_check = holding_shares >= shares

        if shares_check is False:
            return apology("Invalid shares. You don't have enough shares to sell.", 400)

        # ALL check pass, sell process start
        update_shares = holding_shares - shares
        if update_shares == 0:
            db.execute("DELETE FROM holding WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)
        else:
            db.execute("UPDATE holding SET shares = ? WHERE user_id = ? AND symbol =?", update_shares, session["user_id"], symbol)

        lookup_result = lookup(symbol)
        shares_value = float(lookup_result["price"]) * shares
        user_cash = db.execute("SELECT cash from users WHERE id = ?", session["user_id"])
        user_cash = float(user_cash[0]["cash"])

        update_cash = user_cash + shares_value
        db.execute("UPDATE users SET cash = ? WHERE id = ?", update_cash, session["user_id"])
        return redirect("/")
    else:
        return render_template("sell.html", rows=rows)
