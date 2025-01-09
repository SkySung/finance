import os

from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
# app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(basedir, 'finance.db')}"
# app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///finance.db"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
Session(app)

# Initialize SQLAlchemy
db = SQLAlchemy(app)


# Models
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, nullable=False, unique=True)
    hash = db.Column(db.String, nullable=False)
    cash = db.Column(db.Float, default=10000)


class Holding(db.Model):
    __tablename__ = "holding"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    symbol = db.Column(db.String, nullable=False)
    name = db.Column(db.String, nullable=False)
    shares = db.Column(db.Integer, nullable=False)


class History(db.Model):
    __tablename__ = "history"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    symbol = db.Column(db.String, nullable=False)
    shares = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    type = db.Column(db.String, nullable=False)
    transacted = db.Column(db.DateTime, default=db.func.current_timestamp())


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
    holding = Holding.query.filter_by(user_id=session["user_id"]).all()
    user = User.query.get(session["user_id"])
    total_market_value = user.cash

    for row in holding:
        lookup_result = lookup(row.symbol)
        row.price = float(lookup_result["price"]) if lookup_result else 0
        row.total = int(row.shares) * float(row.price)
        total_market_value += row.total

    return render_template("index.html", holding=holding, cash=user.cash, total=total_market_value)


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
        except:
            flash("Numbers only")
            return apology("Numbers only.")

        result = lookup(symbol)
        if result is None:
            flash("There is no result. Please try again.", 400)
            return apology("There is no result. Please try again.", 400)
        result_price = float(result["price"])

        # Ensure the result_name doesn't affect SQL Syntax
        result_name = result["name"]
        result_symbol = result["symbol"]

        total_price = result_price * shares
        user = User.query.get(session["user_id"])
        if user.cash < total_price:
            flash("Cash is not enough, please adjust numbers of buying shares")
            return render_template("buy.html")

        # Update user cash and add to history
        user.cash -= total_price
        db.session.add(History(user_id=session["user_id"], symbol=result_symbol, shares=shares, price=result_price, type="buy"))
        db.session.commit()

        holding = Holding.query.filter_by(user_id=session["user_id"], symbol=symbol).first()
        if not holding:
            new_holding = Holding(user_id=session["user_id"], symbol=result_symbol, name=result_name, shares=shares)
            db.session.add(new_holding)
        else:
            holding.shares += shares

        db.session.commit()
        flash(f"Bought {shares} shares of {symbol} at ${result_price:.2f}. Total: ${total_price}")
        return redirect("/")

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = History.query.filter_by(user_id=session["user_id"]).order_by(History.transacted.desc()).all()
    return render_template("history.html", rows=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    session.clear()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()

        if user is None or not check_password_hash(user.hash, password):
            return apology("invalid username and/or password", 403)

        # session["user_id"] = user.id
        return redirect("/")

    return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""
    session.clear()
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        result = lookup(symbol)
        if result is None:
            return apology("Symbol invalid", 400)
        return render_template("quoted.html", result=result)
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        if User.query.filter_by(username=username).first():
            return apology("Username already taken. Try another name.", 400)
        if password != confirmation:
            return apology("Passwords don't match.", 400)

        hash_password = generate_password_hash(password)
        new_user = User(username=username, hash=hash_password)
        db.session.add(new_user)
        db.session.commit()

        session["user_id"] = new_user.id
        flash("Registration successful! You now have $10,000 as a starting fund.")
        return redirect("/")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    holdings = Holding.query.filter_by(user_id=session["user_id"]).all()

    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        try:
            shares = int(shares)
            if shares <= 0:
                flash("Positive number only.")
                return apology("Positive numbers only.")
        except:
            flash("Numbers only")
            return apology("Numbers only.")

        holding = Holding.query.filter_by(user_id=session["user_id"], symbol=symbol).first()
        if not holding or holding.shares < shares:
            return apology("Invalid shares. You don't have enough shares to sell.", 400)

        holding.shares -= shares
        if holding.shares == 0:
            db.session.delete(holding)

        result = lookup(symbol)
        total_sale_value = float(result["price"]) * shares
        user = User.query.get(session["user_id"])
        user.cash += total_sale_value

        db.session.add(History(user_id=session["user_id"], symbol=symbol, shares=shares, price=result["price"], type="sell"))
        db.session.commit()

        flash(f"Sold {shares} shares of {symbol} for ${total_sale_value}")
        return redirect("/")

    return render_template("sell.html", rows=holdings)