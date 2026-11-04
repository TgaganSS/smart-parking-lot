"""Smart Parking Lot Management System
Python OOP + SQLite + text/CSV file handling | Menu-driven academic project
Run: python parking_system.py
"""
from __future__ import annotations

import csv
import math
import re
import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "parking.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
RECEIPT_DIR = BASE_DIR / "receipts"
EXPORT_DIR = BASE_DIR / "exports"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class ParkingError(Exception):
    """Base exception for parking application errors."""


class InvalidInputError(ParkingError):
    """Raised when user input is invalid."""


class NoAvailableSlotError(ParkingError):
    """Raised when no compatible slot is available."""


class VehicleNotParkedError(ParkingError):
    """Raised when an exit is requested for a vehicle not currently parked."""


# --------------------------------------------------------------------------- #
# Database access
# --------------------------------------------------------------------------- #
class Database:
    """Encapsulates SQLite connections and schema initialization.

    Every unit of work runs inside ``session()``, which opens a connection,
    wraps the work in one transaction (commit on success, rollback on error)
    and always closes the connection afterwards.
    """

    def __init__(self, path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH):
        self.path = Path(path)
        self.schema_path = Path(schema_path)
        self.legacy_backup: Optional[Path] = None
        self._backup_legacy_database()
        self.initialize()

    @contextmanager
    def session(self, write: bool = False):
        conn = sqlite3.connect(self.path, isolation_level=None)  # manual transactions
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        """Create all tables, triggers and views from schema.sql."""
        if not self.schema_path.is_file():
            raise ParkingError(f"Schema file not found: {self.schema_path}")
        script = self.schema_path.read_text(encoding="utf-8")
        conn = sqlite3.connect(self.path)
        try:
            conn.executescript(script)
            conn.commit()
        finally:
            conn.close()

    def _backup_legacy_database(self) -> None:
        """Version 1 stored entry/exit times in Vehicles; move such a file aside."""
        if not self.path.is_file():
            return
        conn = sqlite3.connect(self.path)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(Vehicles)")}
        finally:
            conn.close()
        if "entry_time" in columns:
            stamp = datetime.now().strftime("%Y%m%d%H%M%S")
            self.legacy_backup = self.path.with_name(f"{self.path.stem}_legacy_{stamp}.bak")
            self.path.replace(self.legacy_backup)


# --------------------------------------------------------------------------- #
# Vehicles (abstraction, inheritance, polymorphism, encapsulation)
# --------------------------------------------------------------------------- #
class Vehicle(ABC):
    """Abstract base class for all supported vehicles."""

    _PLATE_PATTERN = re.compile(r"^[A-Z0-9]{1,15}$")

    def __init__(self, vehicle_number: str):
        self.vehicle_number = vehicle_number  # goes through the validating setter

    @staticmethod
    def normalize_number(raw: str) -> str:
        """Upper-case a plate and drop spaces/hyphens ('tn 09-ab 1234' -> 'TN09AB1234')."""
        if not isinstance(raw, str):
            raise InvalidInputError("Vehicle number must be text.")
        number = re.sub(r"[\s-]", "", raw).upper()
        if not Vehicle._PLATE_PATTERN.match(number):
            raise InvalidInputError(
                "Vehicle number must be 1-15 letters/digits (spaces and hyphens are ignored)."
            )
        return number

    @property
    def vehicle_number(self) -> str:
        return self.__vehicle_number

    @vehicle_number.setter
    def vehicle_number(self, value: str) -> None:
        self.__vehicle_number = self.normalize_number(value)

    @property
    def vehicle_type(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def get_hourly_rate(self) -> float:
        """Return hourly parking rate."""

    @staticmethod
    def billable_hours(duration_hours: float) -> int:
        """Every started hour is charged; the minimum charge is one hour."""
        if isinstance(duration_hours, bool) or not isinstance(duration_hours, (int, float)):
            raise InvalidInputError("Parking duration must be a number.")
        if math.isnan(duration_hours) or duration_hours < 0:
            raise InvalidInputError("Parking duration cannot be negative.")
        # round() absorbs floating-point noise such as 1.0000000000002 hours
        return max(1, math.ceil(round(duration_hours, 6)))

    def calculate_fee(self, duration_hours: float) -> float:
        # Polymorphism: the rate comes from whichever subclass this object is.
        return round(self.billable_hours(duration_hours) * self.get_hourly_rate(), 2)

    @staticmethod
    def create(vehicle_type: str, vehicle_number: str) -> "Vehicle":
        """Factory used when rebuilding a vehicle from a database row."""
        try:
            return VEHICLE_TYPES[vehicle_type](vehicle_number)
        except KeyError:
            raise InvalidInputError(f"Unsupported vehicle type: {vehicle_type!r}") from None

    def __str__(self):
        return f"{self.vehicle_type} ({self.vehicle_number})"


class Car(Vehicle):
    """Car implementation with overridden hourly rate."""

    def get_hourly_rate(self) -> float:
        return 40.0


class Bike(Vehicle):
    """Bike implementation with overridden hourly rate."""

    def get_hourly_rate(self) -> float:
        return 20.0


VEHICLE_TYPES = {"Car": Car, "Bike": Bike}


# --------------------------------------------------------------------------- #
# Slots, payments, receipts
# --------------------------------------------------------------------------- #
class ParkingSlot:
    """One parking slot. The database holds occupancy; this object holds identity and type."""

    VALID_TYPES = ("Car", "Bike", "Any")

    def __init__(self, slot_id: int, slot_type: str = "Any"):
        if isinstance(slot_id, bool) or not isinstance(slot_id, int) or slot_id < 1:
            raise InvalidInputError("Slot id must be a positive integer.")
        self.__slot_id = slot_id
        self.slot_type = slot_type  # validating setter

    @property
    def slot_id(self) -> int:
        return self.__slot_id

    @property
    def slot_type(self) -> str:
        return self.__slot_type

    @slot_type.setter
    def slot_type(self, value: str) -> None:
        if value not in self.VALID_TYPES:
            raise InvalidInputError("Slot type must be Car, Bike, or Any.")
        self.__slot_type = value

    def accepts(self, vehicle: Vehicle) -> bool:
        return self.slot_type == "Any" or self.slot_type == vehicle.vehicle_type

    def __str__(self):
        return f"Slot {self.slot_id} [{self.slot_type}]"


class Payment:
    """A payment for one completed visit."""

    VALID_STATUSES = ("PAID", "FAILED")

    def __init__(self, visit_id: int, duration_hours: float, amount: float, status: str = "PAID"):
        self.__visit_id = visit_id
        self.__duration_hours = duration_hours
        self.amount = amount  # validating setter
        self.status = status  # validating setter
        self.__payment_id: Optional[int] = None

    @property
    def amount(self) -> float:
        return self.__amount

    @amount.setter
    def amount(self, value: float) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise InvalidInputError("Payment amount must be a non-negative number.")
        self.__amount = round(float(value), 2)

    @property
    def status(self) -> str:
        return self.__status

    @status.setter
    def status(self, value: str) -> None:
        if value not in self.VALID_STATUSES:
            raise InvalidInputError("Payment status must be PAID or FAILED.")
        self.__status = value

    @property
    def payment_id(self) -> Optional[int]:
        return self.__payment_id

    def process_payment(self, conn: sqlite3.Connection, paid_at: datetime) -> int:
        """Insert this payment using the caller's transaction and return its id."""
        cur = conn.execute(
            "INSERT INTO Payments(visit_id,duration_hours,amount,payment_time,payment_status) "
            "VALUES(?,?,?,?,?)",
            (self.__visit_id, self.__duration_hours, self.amount,
             paid_at.strftime(TIME_FORMAT), self.status),
        )
        self.__payment_id = cur.lastrowid
        return self.__payment_id


class Receipt:
    """Formats a parking receipt and saves it as a text file."""

    def __init__(self, receipt_id: int, vehicle: Vehicle, slot_id: int,
                 entry: datetime, exit_time: datetime, duration: float, amount: float):
        self.receipt_id = receipt_id
        self.vehicle = vehicle
        self.slot_id = slot_id
        self.entry = entry
        self.exit_time = exit_time
        self.duration = duration
        self.amount = amount
        self.file_path: Optional[Path] = None

    def render(self) -> str:
        line = "=" * 42
        return "\n".join([
            line,
            "          SMART PARKING RECEIPT",
            line,
            f"Receipt / Payment ID : {self.receipt_id}",
            f"Vehicle              : {self.vehicle.vehicle_number}",
            f"Vehicle type         : {self.vehicle.vehicle_type}",
            f"Parking slot         : {self.slot_id}",
            f"Entry time           : {self.entry.strftime(TIME_FORMAT)}",
            f"Exit time            : {self.exit_time.strftime(TIME_FORMAT)}",
            f"Duration             : {self.duration:.2f} hour(s)",
            f"Billable hours       : {Vehicle.billable_hours(self.duration)} "
            f"@ Rs. {self.vehicle.get_hourly_rate():.2f}/hr",
            f"Amount paid          : Rs. {self.amount:.2f}",
            line,
        ])

    def save(self, directory: Path) -> Path:
        """Write receipts/receipt_0001.txt (text-file persistence)."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"receipt_{self.receipt_id:04d}.txt"
        path.write_text(self.render() + "\n", encoding="utf-8")
        self.file_path = path
        return path

    def __str__(self):
        return self.render()


# --------------------------------------------------------------------------- #
# Parking lot (composition: ParkingLot owns ParkingSlot objects)
# --------------------------------------------------------------------------- #
class ParkingLot:
    """Coordinates slots, vehicle allocation, checkout, reports and file output."""

    def __init__(self, db: Database, total_car_slots: int = 5, total_bike_slots: int = 10,
                 receipt_dir: Path = RECEIPT_DIR, export_dir: Path = EXPORT_DIR):
        for count in (total_car_slots, total_bike_slots):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise InvalidInputError("Slot counts must be non-negative integers.")
        self.db = db
        self.receipt_dir = Path(receipt_dir)
        self.export_dir = Path(export_dir)
        self.__slots: list[ParkingSlot] = []
        self._seed_slots(total_car_slots, total_bike_slots)
        self._load_slots()

    # -- setup -------------------------------------------------------------- #
    def _seed_slots(self, cars: int, bikes: int) -> None:
        layout = [(i, "Car") for i in range(1, cars + 1)]
        layout += [(i, "Bike") for i in range(cars + 1, cars + bikes + 1)]
        with self.db.session(write=True) as conn:
            conn.executemany("INSERT OR IGNORE INTO ParkingSlots(slot_id,slot_type) VALUES(?,?)", layout)

    def _load_slots(self) -> None:
        """The database is authoritative: build ParkingSlot objects from its rows."""
        with self.db.session() as conn:
            rows = conn.execute("SELECT slot_id, slot_type FROM ParkingSlots ORDER BY slot_id").fetchall()
        self.__slots = [ParkingSlot(r["slot_id"], r["slot_type"]) for r in rows]

    @property
    def slots(self) -> tuple[ParkingSlot, ...]:
        return tuple(self.__slots)

    # -- core operations ------------------------------------------------------ #
    def park_vehicle(self, vehicle: Vehicle, entry_time: Optional[datetime] = None) -> tuple[int, datetime]:
        entry = entry_time or datetime.now()
        stamp = entry.strftime(TIME_FORMAT)
        with self.db.session(write=True) as conn:
            if conn.execute("SELECT 1 FROM Visits WHERE vehicle_number=? AND exit_time IS NULL",
                            (vehicle.vehicle_number,)).fetchone():
                raise InvalidInputError("This vehicle is already parked.")
            free_ids = {r["slot_id"] for r in conn.execute("SELECT slot_id FROM v_free_slots")}
            slot = next((s for s in self.__slots if s.slot_id in free_ids and s.accepts(vehicle)), None)
            if slot is None:
                raise NoAvailableSlotError(f"No available slot for {vehicle.vehicle_type}.")
            conn.execute(
                "INSERT INTO Vehicles(vehicle_number,vehicle_type,registered_at) VALUES(?,?,?) "
                "ON CONFLICT(vehicle_number) DO UPDATE SET vehicle_type=excluded.vehicle_type",
                (vehicle.vehicle_number, vehicle.vehicle_type, stamp),
            )
            conn.execute("INSERT INTO Visits(vehicle_number,slot_id,entry_time) VALUES(?,?,?)",
                         (vehicle.vehicle_number, slot.slot_id, stamp))
            # trigger trg_visit_start marks the slot as occupied
        return slot.slot_id, entry

    def remove_vehicle(self, vehicle_number: str, exit_time: Optional[datetime] = None) -> Receipt:
        number = Vehicle.normalize_number(vehicle_number)
        exit_time = exit_time or datetime.now()
        with self.db.session(write=True) as conn:
            row = conn.execute(
                "SELECT vi.visit_id, vi.slot_id, vi.entry_time, v.vehicle_type "
                "FROM Visits vi JOIN Vehicles v ON v.vehicle_number = vi.vehicle_number "
                "WHERE vi.vehicle_number=? AND vi.exit_time IS NULL", (number,)
            ).fetchone()
            if not row:
                raise VehicleNotParkedError("Vehicle is not currently parked.")
            entry = datetime.strptime(row["entry_time"], TIME_FORMAT)
            exit_time = max(exit_time, entry)  # never let a clock glitch produce a negative stay
            duration = (exit_time - entry).total_seconds() / 3600
            vehicle = Vehicle.create(row["vehicle_type"], number)
            payment = Payment(row["visit_id"], duration, vehicle.calculate_fee(duration))
            conn.execute("UPDATE Visits SET exit_time=? WHERE visit_id=?",
                         (exit_time.strftime(TIME_FORMAT), row["visit_id"]))
            # trigger trg_visit_end releases the slot
            payment_id = payment.process_payment(conn, exit_time)
        receipt = Receipt(payment_id, vehicle, row["slot_id"], entry, exit_time, duration, payment.amount)
        try:  # the payment is already committed; a file problem must not undo it
            receipt.save(self.receipt_dir)
        except OSError:
            receipt.file_path = None
        return receipt

    # -- queries / reports ---------------------------------------------------- #
    def get_availability(self) -> list[dict]:
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT slot_type, COUNT(*) AS total, SUM(is_occupied) AS occupied "
                "FROM ParkingSlots GROUP BY slot_type ORDER BY slot_type"
            ).fetchall()
        return [{"type": r["slot_type"], "total": r["total"], "occupied": r["occupied"] or 0,
                 "available": r["total"] - (r["occupied"] or 0)} for r in rows]

    def list_parked_vehicles(self) -> list[sqlite3.Row]:
        with self.db.session() as conn:
            return conn.execute(
                "SELECT vi.vehicle_number, v.vehicle_type, vi.slot_id, vi.entry_time "
                "FROM Visits vi JOIN Vehicles v ON v.vehicle_number = vi.vehicle_number "
                "WHERE vi.exit_time IS NULL ORDER BY vi.slot_id"
            ).fetchall()

    def list_slots(self) -> list[sqlite3.Row]:
        with self.db.session() as conn:
            return conn.execute(
                "SELECT s.slot_id, s.slot_type, s.is_occupied, vi.vehicle_number "
                "FROM ParkingSlots s "
                "LEFT JOIN Visits vi ON vi.slot_id = s.slot_id AND vi.exit_time IS NULL "
                "ORDER BY s.slot_id"
            ).fetchall()

    def payment_history(self) -> list[sqlite3.Row]:
        with self.db.session() as conn:
            return conn.execute(
                "SELECT p.payment_id, vi.vehicle_number, v.vehicle_type, vi.slot_id, "
                "       vi.entry_time, vi.exit_time, p.duration_hours, p.amount, "
                "       p.payment_time, p.payment_status "
                "FROM Payments p "
                "JOIN Visits   vi ON vi.visit_id      = p.visit_id "
                "JOIN Vehicles v  ON v.vehicle_number = vi.vehicle_number "
                "ORDER BY p.payment_id DESC"
            ).fetchall()

    def visit_history(self, vehicle_number: Optional[str] = None) -> list[sqlite3.Row]:
        """All visits (open and closed), optionally for one vehicle."""
        sql = ("SELECT vi.visit_id, vi.vehicle_number, v.vehicle_type, vi.slot_id, "
               "       vi.entry_time, vi.exit_time, p.amount "
               "FROM Visits vi "
               "JOIN Vehicles v ON v.vehicle_number = vi.vehicle_number "
               "LEFT JOIN Payments p ON p.visit_id = vi.visit_id ")
        params: tuple = ()
        if vehicle_number and vehicle_number.strip():
            sql += "WHERE vi.vehicle_number = ? "
            params = (Vehicle.normalize_number(vehicle_number),)
        sql += "ORDER BY vi.visit_id"
        with self.db.session() as conn:
            return conn.execute(sql, params).fetchall()

    def daily_revenue(self) -> tuple[list[sqlite3.Row], float]:
        """Revenue per day and vehicle type (view v_daily_revenue) plus the grand total."""
        with self.db.session() as conn:
            rows = conn.execute("SELECT day, vehicle_type, payments, revenue "
                                "FROM v_daily_revenue ORDER BY day, vehicle_type").fetchall()
            total = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM Payments WHERE payment_status='PAID'"
            ).fetchone()[0]
        return rows, float(total)

    # -- file handling -------------------------------------------------------- #
    def export_payments_csv(self, path: Optional[Path] = None) -> Path:
        """Write the payment history to exports/payments.csv."""
        path = Path(path) if path else self.export_dir / "payments.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = self.payment_history()
        header = ["payment_id", "vehicle_number", "vehicle_type", "slot_id", "entry_time",
                  "exit_time", "duration_hours", "amount", "payment_time", "payment_status"]
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(header)
            for r in rows:
                writer.writerow([r["payment_id"], r["vehicle_number"], r["vehicle_type"], r["slot_id"],
                                 r["entry_time"], r["exit_time"], f"{r['duration_hours']:.2f}",
                                 f"{r['amount']:.2f}", r["payment_time"], r["payment_status"]])
        return path


# --------------------------------------------------------------------------- #
# Menu interface
# --------------------------------------------------------------------------- #
MENU = """
========== SMART PARKING LOT ==========
 1. Park a car
 2. Park a bike
 3. Remove vehicle / Generate receipt
 4. View slot availability
 5. View parked vehicles
 6. View all parking slots
 7. View payment history
 8. Daily revenue report
 9. Vehicle visit history
10. Export payment history to CSV
 0. Exit
"""


def print_availability(lot: ParkingLot) -> None:
    print("\n--- Slot Availability ---")
    for item in lot.get_availability():
        print(f"{item['type']:>4}: {item['available']} available / {item['total']} total "
              f"({item['occupied']} occupied)")


def park_flow(lot: ParkingLot, vehicle_class: type) -> None:
    kind = vehicle_class.__name__.lower()
    vehicle = vehicle_class(input(f"Enter {kind} registration number: "))
    slot_id, entry = lot.park_vehicle(vehicle)
    print(f"SUCCESS: {vehicle.vehicle_type} {vehicle.vehicle_number} parked in slot {slot_id}.")
    print(f"Entry time: {entry.strftime(TIME_FORMAT)}")


def checkout_flow(lot: ParkingLot) -> None:
    receipt = lot.remove_vehicle(input("Enter vehicle registration number: "))
    print()
    print(receipt)
    if receipt.file_path:
        print(f"Receipt saved to: {receipt.file_path}")
    else:
        print("WARNING: payment recorded, but the receipt file could not be written.")


def show_parked(lot: ParkingLot) -> None:
    rows = lot.list_parked_vehicles()
    print("\n--- Parked Vehicles ---")
    if not rows:
        print("No vehicles are currently parked.")
    for r in rows:
        print(f"{r['vehicle_number']} | {r['vehicle_type']} | Slot {r['slot_id']} | Since {r['entry_time']}")


def show_slots(lot: ParkingLot) -> None:
    print("\n--- Parking Slots ---")
    for r in lot.list_slots():
        state = "OCCUPIED" if r["is_occupied"] else "AVAILABLE"
        print(f"Slot {r['slot_id']:02} | {r['slot_type']:<4} | {state}"
              + (f" | {r['vehicle_number']}" if r["vehicle_number"] else ""))


def show_payments(lot: ParkingLot) -> None:
    rows = lot.payment_history()
    print("\n--- Payment History ---")
    if not rows:
        print("No payment records.")
    for r in rows:
        print(f"#{r['payment_id']} | {r['vehicle_number']} ({r['vehicle_type']}) | Slot {r['slot_id']} | "
              f"{r['duration_hours']:.2f} hr | Rs. {r['amount']:.2f} | {r['payment_status']}")


def show_revenue(lot: ParkingLot) -> None:
    rows, total = lot.daily_revenue()
    print("\n--- Daily Revenue Report ---")
    if not rows:
        print("No revenue recorded yet.")
        return
    print(f"{'Date':<12} {'Type':<5} {'Payments':>8} {'Revenue':>12}")
    for r in rows:
        print(f"{r['day']:<12} {r['vehicle_type']:<5} {r['payments']:>8} {'Rs. ' + format(r['revenue'], '.2f'):>12}")
    print(f"{'TOTAL':<12} {'':<5} {sum(r['payments'] for r in rows):>8} {'Rs. ' + format(total, '.2f'):>12}")


def show_visits(lot: ParkingLot) -> None:
    number = input("Enter vehicle registration number (blank for all vehicles): ")
    rows = lot.visit_history(number)
    print("\n--- Visit History ---")
    if not rows:
        print("No visits found.")
    for r in rows:
        exit_text = r["exit_time"] or "still parked"
        fee = f"Rs. {r['amount']:.2f}" if r["amount"] is not None else "-"
        print(f"Visit {r['visit_id']} | {r['vehicle_number']} ({r['vehicle_type']}) | Slot {r['slot_id']} | "
              f"{r['entry_time']} -> {exit_text} | {fee}")


def run_menu() -> None:
    db = Database()
    if db.legacy_backup:
        print(f"NOTE: an old-format database was found and moved to {db.legacy_backup.name}. "
              "A fresh database has been created.")
    lot = ParkingLot(db)
    actions = {
        "1": lambda: park_flow(lot, Car),
        "2": lambda: park_flow(lot, Bike),
        "3": lambda: checkout_flow(lot),
        "4": lambda: print_availability(lot),
        "5": lambda: show_parked(lot),
        "6": lambda: show_slots(lot),
        "7": lambda: show_payments(lot),
        "8": lambda: show_revenue(lot),
        "9": lambda: show_visits(lot),
        "10": lambda: print(f"Exported to: {lot.export_payments_csv()}"),
    }
    while True:
        print(MENU)
        try:
            choice = input("Enter choice: ").strip()
            if choice == "0":
                print("Thank you for using Smart Parking Lot Management System.")
                break
            action = actions.get(choice)
            if action:
                action()
            else:
                print("Invalid menu choice. Enter a number from 0 to 10.")
        except (ParkingError, ValueError, sqlite3.Error, OSError) as exc:
            print(f"ERROR: {exc}")
        except KeyboardInterrupt:
            print("\nInterrupted. Returning to menu.")
        except EOFError:
            print("\nInput closed. Exiting.")
            break


if __name__ == "__main__":
    run_menu()
