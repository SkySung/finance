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
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///finance.db"
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
    holdings = Holding.query.filter_by(user_id=session["user_id"]).all()
    user = User.query.get(session["user_id"])

    total_market_value = user.cash
    for holding in holdings:
        lookup_result = lookup(holding.symbol)
        holding.price = lookup_result["price"] if lookup_result else 0
        holding.total = holding.shares * holding.price
        total_market_value += holding.total

    return render_template(
        "index.html", holdings=holdings, cash=user.cash, total=total_market_value
    )


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
                return apology("Positive numbers only.")
        except ValueError:
            return apology("Numbers only.")

        result = lookup(symbol)
        if result is None:
            return apology("Invalid symbol.")

        total_price = result["price"] * shares
        user = User.query.get(session["user_id"])

        if user.cash < total_price:
            return apology("Not enough cash.")

        # Update user's cash
        user.cash -= total_price

        # Update or create holding
        holding = Holding.query.filter_by(user_id=user.id, symbol=symbol).first()
        if holding:
            holding.shares += shares
        else:
            new_holding = Holding(
                user_id=user.id, symbol=symbol, name=result["name"], shares=shares
            )
            db.session.add(new_holding)

        # Add to history
        new_history = History(
            user_id=user.id, symbol=symbol, shares=shares, price=result["price"], type="buy"
        )
        db.session.add(new_history)

        db.session.commit()
        flash(f"Bought {shares} shares of {symbol}.")
        return redirect("/")

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = History.query.filter_by(user_id=session["user_id"]).order_by(History.transacted).all()
    return render_template("history.html", rows=transactions)


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]
    holdings = Holding.query.filter_by(user_id=user_id).all()

    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        try:
            shares = int(shares)
            if shares <= 0:
                return apology("Positive numbers only.")
        except ValueError:
            return apology("Numbers only.")

        holding = Holding.query.filter_by(user_id=user_id, symbol=symbol).first()
        if not holding or holding.shares < shares:
            return apology("Not enough shares.")

        lookup_result = lookup(symbol)
        sell_value = shares * lookup_result["price"]

        # Update holding and user's cash
        holding.shares -= shares
        if holding.shares == 0:
            db.session.delete(holding)

        user = User.query.get(user_id)
        user.cash += sell_value

        # Add to history
        new_history = History(
            user_id=user_id, symbol=symbol, shares=-shares, price=lookup_result["price"], type="sell"
        )
        db.session.add(new_history)

        db.session.commit()
        flash(f"Sold {shares} shares of {symbol}.")
        return redirect("/")

    return render_template("sell.html", rows=holdings)
