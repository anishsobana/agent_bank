"""In-memory "core banking system", seeded with three demo customers.

Each customer's data is crafted to exercise a use case: a card-testing fraud pattern (Priya), a high
fixed-obligation loan decline (Arjun), a thin-file young professional with a low balance (Kavya).
Timestamps are relative to startup so the demo always looks recent.
"""
from __future__ import annotations

import itertools
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal

from .models import (Account, Beneficiary, Card, CreditProfile, Customer, Dispute, Loan,
                     LoanApplication, Transaction)

D = Decimal


class BankDataStore:
    def __init__(self, now: datetime | None = None) -> None:
        self.lock = threading.RLock()
        self.customers: dict[str, Customer] = {}
        self.accounts: dict[str, Account] = {}
        self.cards: dict[str, Card] = {}
        self.transactions: dict[str, list[Transaction]] = {}  # by account number
        self.beneficiaries: dict[str, list[Beneficiary]] = {}
        self.credit_profiles: dict[str, CreditProfile] = {}
        self.loans: dict[str, list[Loan]] = {}
        self.loan_applications: dict[str, list[LoanApplication]] = {}
        self.disputes: dict[str, list[Dispute]] = {}
        self._seq = itertools.count(5001)
        self._seed((now or datetime.now()).replace(second=0, microsecond=0))

    def next_id(self, prefix: str) -> str:
        with self.lock:
            return f"{prefix}-{next(self._seq)}"

    # ------------------------------------------------------------------ seed data
    def _tx(self, account, tid, ts, desc, merchant, category, amount, direction, channel, location, country, card=None):
        self.transactions.setdefault(account, []).append(Transaction(
            tid, account, ts, desc, merchant, category, D(amount), direction, channel, location, country, card))

    def _seed(self, now: datetime) -> None:
        def at(days_ago: int, hour: int) -> datetime:
            return (now - timedelta(days=days_ago)).replace(hour=hour)

        today = now.date()

        # ---- Priya: healthy profile, but a card-testing fraud pattern on her credit card
        self.customers["CUST1001"] = Customer("CUST1001", "Priya Raman", "priya.raman@example.com", "+91-98400-11223",
                                              "Chennai", "Salaried - Premium", date(2017, 6, 12), "VERIFIED")
        self.accounts["ACC10011001"] = Account("ACC10011001", "CUST1001", "SAVINGS", "Chennai - T Nagar",
                                               D("184250.75"), "INR", "ACTIVE")
        self.accounts["ACC10011002"] = Account("ACC10011002", "CUST1001", "FIXED_DEPOSIT", "Chennai - T Nagar",
                                               D("300000.00"), "INR", "ACTIVE")
        self.cards["CARD-1001-D"] = Card("CARD-1001-D", "CUST1001", "DEBIT", "VISA", "4821", "ACTIVE", D("100000"), "ACC10011001")
        self.cards["CARD-1001-C"] = Card("CARD-1001-C", "CUST1001", "CREDIT", "MASTERCARD", "7712", "ACTIVE", D("250000"), "ACC10011001")
        a1 = "ACC10011001"
        self._tx(a1, "TXN-1001-01", at(26, 10), "Salary - Zenith Software", "Zenith Software Pvt Ltd", "SALARY", "95000", "CREDIT", "NEFT", "Chennai", "IN")
        self._tx(a1, "TXN-1001-02", at(25, 9), "House rent - UPI", "K. Suresh (Landlord)", "RENT", "22000", "DEBIT", "UPI", "Chennai", "IN")
        self._tx(a1, "TXN-1001-03", at(21, 20), "Saravana Stores", "Saravana Stores", "SHOPPING", "4380", "DEBIT", "POS", "Chennai", "IN", "CARD-1001-D")
        self._tx(a1, "TXN-1001-04", at(18, 13), "Swiggy order", "Swiggy", "FOOD", "640", "DEBIT", "UPI", "Chennai", "IN")
        self._tx(a1, "TXN-1001-05", at(15, 11), "TNEB electricity bill", "TANGEDCO", "UTILITIES", "1820", "DEBIT", "ONLINE", "Chennai", "IN")
        self._tx(a1, "TXN-1001-06", at(12, 19), "Amazon.in", "Amazon India", "SHOPPING", "3499", "DEBIT", "ONLINE", "Bengaluru", "IN", "CARD-1001-C")
        self._tx(a1, "TXN-1001-07", at(10, 8), "Car loan EMI LN-2001", "AgentBank Loans", "EMI", "8500", "DEBIT", "AUTO_DEBIT", "Chennai", "IN")
        self._tx(a1, "TXN-1001-08", at(7, 18), "BigBasket", "BigBasket", "GROCERIES", "2310", "DEBIT", "UPI", "Chennai", "IN")
        self._tx(a1, "TXN-1001-09", at(5, 9), "Indian Oil - fuel", "Indian Oil", "FUEL", "2000", "DEBIT", "POS", "Chennai", "IN", "CARD-1001-D")
        self._tx(a1, "TXN-1001-10", at(3, 21), "PVR Cinemas", "PVR Cinemas", "ENTERTAINMENT", "780", "DEBIT", "ONLINE", "Chennai", "IN", "CARD-1001-C")
        self._tx(a1, "TXN-1001-11", at(2, 12), "Transfer to Amma", "Lakshmi Raman", "TRANSFER", "10000", "DEBIT", "IMPS", "Chennai", "IN")
        # card-testing pattern: two micro charges, then a large foreign purchase at 3 AM
        night = at(1, 3).replace(minute=4)
        self._tx(a1, "TXN-1001-12", night, "VRFY*ONLINE SVCS", "VRFY Online Services", "OTHER", "1", "DEBIT", "ONLINE", "Dubai", "AE", "CARD-1001-C")
        self._tx(a1, "TXN-1001-13", night + timedelta(minutes=3), "VRFY*ONLINE SVCS", "VRFY Online Services", "OTHER", "10", "DEBIT", "ONLINE", "Dubai", "AE", "CARD-1001-C")
        self._tx(a1, "TXN-1001-14", night + timedelta(minutes=9), "ELECTRO GADGETS FZE", "Electro Gadgets FZE", "ELECTRONICS", "78999", "DEBIT", "ONLINE", "Dubai", "AE", "CARD-1001-C")
        self.beneficiaries["CUST1001"] = [
            Beneficiary("Lakshmi Raman (Amma)", "ACC77002211", "AgentBank", "Mother"),
            Beneficiary("Karthik Raman", "ACC55009988", "HDFC Bank", "Brother"),
        ]
        self.credit_profiles["CUST1001"] = CreditProfile("CUST1001", 768, "CIBIL", D("95000"), D("8500"), "SALARIED", 6, 0)
        self.loans["CUST1001"] = [Loan("LN-2001", "CUST1001", "CAR", D("450000"), D("212400"), 9.1, 60, D("8500"),
                                       "ACTIVE", today + timedelta(days=20))]

        # ---- Arjun: high existing obligations, average score -> loan constraints
        self.customers["CUST1002"] = Customer("CUST1002", "Arjun Mehta", "arjun.mehta@example.com", "+91-99001-44556",
                                              "Bengaluru", "Self-employed", date(2020, 1, 20), "VERIFIED")
        self.accounts["ACC10021001"] = Account("ACC10021001", "CUST1002", "CURRENT", "Bengaluru - Indiranagar",
                                               D("42300.40"), "INR", "ACTIVE")
        self.cards["CARD-1002-D"] = Card("CARD-1002-D", "CUST1002", "DEBIT", "RUPAY", "3390", "ACTIVE", D("50000"), "ACC10021001")
        a2 = "ACC10021001"
        self._tx(a2, "TXN-1002-01", at(24, 11), "Client payment - Orbit Retail", "Orbit Retail LLP", "BUSINESS_INCOME", "140000", "CREDIT", "NEFT", "Bengaluru", "IN")
        self._tx(a2, "TXN-1002-02", at(22, 8), "Home loan EMI LN-2101", "AgentBank Loans", "EMI", "32000", "DEBIT", "AUTO_DEBIT", "Bengaluru", "IN")
        self._tx(a2, "TXN-1002-03", at(20, 8), "Personal loan EMI LN-2102", "AgentBank Loans", "EMI", "9000", "DEBIT", "AUTO_DEBIT", "Bengaluru", "IN")
        self._tx(a2, "TXN-1002-04", at(16, 15), "Office supplies", "Croma", "BUSINESS_EXPENSE", "18450", "DEBIT", "POS", "Bengaluru", "IN", "CARD-1002-D")
        self._tx(a2, "TXN-1002-05", at(9, 19), "Zomato", "Zomato", "FOOD", "1120", "DEBIT", "UPI", "Bengaluru", "IN")
        self._tx(a2, "TXN-1002-06", at(4, 17), "ATM withdrawal", "AgentBank ATM", "CASH", "10000", "DEBIT", "ATM", "Bengaluru", "IN", "CARD-1002-D")
        self._tx(a2, "TXN-1002-07", at(1, 14), "GST payment", "GSTN", "TAX", "21500", "DEBIT", "ONLINE", "Bengaluru", "IN")
        self.beneficiaries["CUST1002"] = [Beneficiary("Mehta Traders", "ACC66001122", "ICICI Bank", "Supplier")]
        self.credit_profiles["CUST1002"] = CreditProfile("CUST1002", 672, "CIBIL", D("120000"), D("41000"), "SELF_EMPLOYED", 5, 1)
        self.loans["CUST1002"] = [
            Loan("LN-2101", "CUST1002", "HOME", D("3500000"), D("3120000"), 8.7, 240, D("32000"), "ACTIVE", today + timedelta(days=8)),
            Loan("LN-2102", "CUST1002", "PERSONAL", D("350000"), D("188000"), 13.5, 48, D("9000"), "ACTIVE", today + timedelta(days=10)),
        ]
        self.loan_applications["CUST1002"] = [LoanApplication(
            "LAPP-3002", "CUST1002", "BUSINESS", D("500000"), 36, 14.5, D("17211"), "UNDER_REVIEW",
            ["Awaiting last 2 years ITR documents"], now - timedelta(days=6))]

        # ---- Kavya: early career, thin file, low balance
        self.customers["CUST1003"] = Customer("CUST1003", "Kavya Iyer", "kavya.iyer@example.com", "+91-90030-77889",
                                              "Coimbatore", "Salaried - Young Professional", date(2024, 7, 1), "VERIFIED")
        self.accounts["ACC10031001"] = Account("ACC10031001", "CUST1003", "SAVINGS", "Coimbatore - RS Puram",
                                               D("8940.00"), "INR", "ACTIVE")
        self.cards["CARD-1003-D"] = Card("CARD-1003-D", "CUST1003", "DEBIT", "VISA", "6604", "ACTIVE", D("25000"), "ACC10031001")
        a3 = "ACC10031001"
        self._tx(a3, "TXN-1003-01", at(27, 10), "Salary - Kovai Analytics", "Kovai Analytics", "SALARY", "38000", "CREDIT", "NEFT", "Coimbatore", "IN")
        self._tx(a3, "TXN-1003-02", at(26, 9), "PG rent", "Sri Lakshmi PG", "RENT", "9000", "DEBIT", "UPI", "Coimbatore", "IN")
        self._tx(a3, "TXN-1003-03", at(19, 20), "Myntra", "Myntra", "SHOPPING", "2799", "DEBIT", "ONLINE", "Bengaluru", "IN", "CARD-1003-D")
        self._tx(a3, "TXN-1003-04", at(11, 13), "Udemy course", "Udemy", "EDUCATION", "499", "DEBIT", "ONLINE", "San Francisco", "US", "CARD-1003-D")
        self._tx(a3, "TXN-1003-05", at(6, 18), "Mobile recharge", "Jio", "UTILITIES", "349", "DEBIT", "UPI", "Coimbatore", "IN")
        self._tx(a3, "TXN-1003-06", at(2, 20), "Swiggy Instamart", "Swiggy", "GROCERIES", "1260", "DEBIT", "UPI", "Coimbatore", "IN")
        self.beneficiaries["CUST1003"] = []
        self.credit_profiles["CUST1003"] = CreditProfile("CUST1003", 712, "CIBIL", D("38000"), D("0"), "SALARIED", 1, 0)
        self.loans["CUST1003"] = []
