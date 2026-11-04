"""Smart Parking Lot Management System
Python OOP + SQLite | Menu-driven academic project
Run: python parking_system.py
"""
from __future__ import annotations
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).with_name("parking.db")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class ParkingError(Exception):
    """Base exception for parking application errors."""


class InvalidInputError(ParkingError):
    """Raised when user input is invalid."""


class NoAvailableSlotError(ParkingError):
    """Raised when no compatible slot is available."""


class VehicleNotParkedError(ParkingError):
    """Raised when an exit is requested for a vehicle not currently parked."""


class Database:
    """Encapsulates SQLite connection and schema initialization."""
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.initialize()

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self):
        schema = """
        CREATE TABLE IF NOT EXISTS Vehicles (
            vehicle_number TEXT PRIMARY KEY,
            vehicle_type TEXT NOT NULL CHECK(vehicle_type IN ('Car','Bike')),
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            slot_id INTEGER,
            status TEXT NOT NULL CHECK(status IN ('PARKED','EXITED'))
        );
        CREATE TABLE IF NOT EXISTS ParkingSlots (
            slot_id INTEGER PRIMARY KEY,
            slot_type TEXT NOT NULL CHECK(slot_type IN ('Car','Bike','Any')),
            is_occupied INTEGER NOT NULL DEFAULT 0 CHECK(is_occupied IN (0,1)),
            vehicle_number TEXT UNIQUE,
            FOREIGN KEY(vehicle_number) REFERENCES Vehicles(vehicle_number)
        );
        CREATE TABLE IF NOT EXISTS Payments (
            payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_number TEXT NOT NULL,
            duration_hours REAL NOT NULL,
            amount REAL NOT NULL,
            payment_time TEXT NOT NULL,
            payment_status TEXT NOT NULL CHECK(payment_status IN ('PAID','FAILED')),
            FOREIGN KEY(vehicle_number) REFERENCES Vehicles(vehicle_number)
        );
        """
        with self.connect() as conn:
            conn.executescript(schema)


class Vehicle(ABC):
    """Abstract base class for all supported vehicles."""
    def __init__(self, vehicle_number: str):
        number = vehicle_number.strip().upper()
        if not number or len(number) > 20:
            raise InvalidInputError("Vehicle number must contain 1–20 characters.")
        self.__vehicle_number = number

    @property
    def vehicle_number(self) -> str:
        return self.__vehicle_number

    @abstractmethod
    def get_hourly_rate(self) -> float:
        """Return hourly parking rate."""

    def calculate_fee(self, duration_hours: float) -> float:
        if duration_hours < 0:
            raise InvalidInputError("Parking duration cannot be negative.")
        # Any started hour is charged as a full hour; minimum charge is one hour.
        billable_hours = max(1, int(duration_hours) if duration_hours.is_integer()
                            else int(duration_hours) + 1)
        return round(billable_hours * self.get_hourly_rate(), 2)

    def __str__(self):
        return f"{self.__class__.__name__} ({self.vehicle_number})"


class Car(Vehicle):
    """Car implementation with overridden hourly rate."""
    def get_hourly_rate(self) -> float:
        return 40.0


class Bike(Vehicle):
    """Bike implementation with overridden hourly rate."""
    def get_hourly_rate(self) -> float:
        return 20.0


class ParkingSlot:
    """Represents one parking slot; database state is authoritative."""
    def __init__(self, slot_id: int, slot_type: str = "Any"):
        if slot_type not in {"Car", "Bike", "Any"}:
            raise InvalidInputError("Slot type must be Car, Bike, or Any.")
        self.__slot_id = int(slot_id)
        self.__slot_type = slot_type

    @property
    def slot_id(self) -> int:
        return self.__slot_id

    @property
    def slot_type(self) -> str:
        return self.__slot_type

    def accepts(self, vehicle: Vehicle) -> bool:
        return self.slot_type == "Any" or self.slot_type == vehicle.__class__.__name__

    def __str__(self):
        return f"Slot {self.slot_id} [{self.slot_type}]"


class Payment:
    """Payment record and receipt data."""
    def __init__(self, vehicle_number: str, duration_hours: float, amount: float):
        self.__vehicle_number = vehicle_number
        self.__duration_hours = duration_hours
        self.__amount = amount

    @property
    def amount(self):
        return self.__amount

    def process_payment(self, db: Database) -> int:
        with db.connect() as conn:
            cur = conn.execute(
                """INSERT INTO Payments(vehicle_number,duration_hours,amount,payment_time,payment_status)
                   VALUES(?,?,?,?,?)""",
                (self.__vehicle_number, self.__duration_hours, self.__amount,
                 datetime.now().strftime(TIME_FORMAT), "PAID")
            )
            return cur.lastrowid


class Receipt:
    """Formats a parking payment receipt."""
    @staticmethod
    def generate(receipt_id: int, vehicle: Vehicle, slot_id: int,
                 entry: datetime, exit_time: datetime, duration: float, amount: float) -> str:
        return (
            "\n" + "=" * 42 + "\n"
            "          SMART PARKING RECEIPT\n"
            + "=" * 42 + "\n"
            f"Receipt / Payment ID : {receipt_id}\n"
            f"Vehicle              : {vehicle.vehicle_number}\n"
            f"Vehicle type         : {vehicle.__class__.__name__}\n"
            f"Parking slot         : {slot_id}\n"
            f"Entry time           : {entry.strftime(TIME_FORMAT)}\n"
            f"Exit time            : {exit_time.strftime(TIME_FORMAT)}\n"
            f"Duration             : {duration:.2f} hour(s)\n"
            f"Amount paid          : Rs. {amount:.2f}\n"
            + "=" * 42
        )


class ParkingLot:
    """Coordinates slots, vehicle allocation, checkout, and persistence."""
    def __init__(self, db: Database, total_car_slots: int = 5, total_bike_slots: int = 10):
        self.db = db
        self.__slots = [ParkingSlot(i, "Car") for i in range(1, total_car_slots + 1)]
        self.__slots += [ParkingSlot(i, "Bike")
                         for i in range(total_car_slots + 1, total_car_slots + total_bike_slots + 1)]
        self._seed_slots()

    def _seed_slots(self):
        with self.db.connect() as conn:
            for slot in self.__slots:
                conn.execute("INSERT OR IGNORE INTO ParkingSlots(slot_id,slot_type) VALUES(?,?)",
                             (slot.slot_id, slot.slot_type))

    def get_availability(self):
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT slot_type, COUNT(*) AS total, SUM(is_occupied) AS occupied "
                "FROM ParkingSlots GROUP BY slot_type ORDER BY slot_type"
            ).fetchall()
        return [{"type": r["slot_type"], "total": r["total"],
                 "occupied": r["occupied"] or 0, "available": r["total"] - (r["occupied"] or 0)}
                for r in rows]

    def park_vehicle(self, vehicle: Vehicle) -> tuple[int, datetime]:
        now = datetime.now()
        with self.db.connect() as conn:
            existing = conn.execute(
                "SELECT status FROM Vehicles WHERE vehicle_number=?", (vehicle.vehicle_number,)
            ).fetchone()
            if existing and existing["status"] == "PARKED":
                raise InvalidInputError("This vehicle is already parked.")
            slot = conn.execute(
                """SELECT slot_id FROM ParkingSlots
                   WHERE is_occupied=0 AND (slot_type=? OR slot_type='Any')
                   ORDER BY slot_id LIMIT 1""",
                (vehicle.__class__.__name__,)
            ).fetchone()
            if not slot:
                raise NoAvailableSlotError(f"No available slot for {vehicle.__class__.__name__}.")
            slot_id = slot["slot_id"]
            conn.execute(
                """INSERT INTO Vehicles(vehicle_number,vehicle_type,entry_time,exit_time,slot_id,status)
                   VALUES(?,?,?,NULL,?,'PARKED')
                   ON CONFLICT(vehicle_number) DO UPDATE SET
                   vehicle_type=excluded.vehicle_type, entry_time=excluded.entry_time,
                   exit_time=NULL, slot_id=excluded.slot_id, status='PARKED'""",
                (vehicle.vehicle_number, vehicle.__class__.__name__, now.strftime(TIME_FORMAT), slot_id)
            )
            conn.execute("UPDATE ParkingSlots SET is_occupied=1, vehicle_number=? WHERE slot_id=?",
                         (vehicle.vehicle_number, slot_id))
        return slot_id, now

    def remove_vehicle(self, vehicle_number: str, exit_time: Optional[datetime] = None):
        number = vehicle_number.strip().upper()
        if not number:
            raise InvalidInputError("Vehicle number cannot be empty.")
        exit_time = exit_time or datetime.now()
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM Vehicles WHERE vehicle_number=? AND status='PARKED'", (number,)
            ).fetchone()
            if not row:
                raise VehicleNotParkedError("Vehicle is not currently parked.")
            entry = datetime.strptime(row["entry_time"], TIME_FORMAT)
            duration = max(0.0, (exit_time - entry).total_seconds() / 3600)
            vehicle = Car(number) if row["vehicle_type"] == "Car" else Bike(number)
            amount = vehicle.calculate_fee(duration)
            payment = Payment(number, duration, amount)
            cur = conn.execute(
                """INSERT INTO Payments(vehicle_number,duration_hours,amount,payment_time,payment_status)
                   VALUES(?,?,?,?,?)""",
                (number, duration, amount, exit_time.strftime(TIME_FORMAT), "PAID")
            )
            payment_id = cur.lastrowid
            conn.execute("UPDATE Vehicles SET exit_time=?,status='EXITED' WHERE vehicle_number=?",
                         (exit_time.strftime(TIME_FORMAT), number))
            conn.execute("UPDATE ParkingSlots SET is_occupied=0,vehicle_number=NULL WHERE slot_id=?",
                         (row["slot_id"],))
        return Receipt.generate(payment_id, vehicle, row["slot_id"], entry, exit_time, duration, amount)

    def list_parked_vehicles(self):
        with self.db.connect() as conn:
            return conn.execute(
                """SELECT vehicle_number,vehicle_type,entry_time,slot_id
                   FROM Vehicles WHERE status='PARKED' ORDER BY slot_id"""
            ).fetchall()

    def list_slots(self):
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT slot_id,slot_type,is_occupied,vehicle_number FROM ParkingSlots ORDER BY slot_id"
            ).fetchall()

    def payment_history(self):
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT payment_id,vehicle_number,duration_hours,amount,payment_time,payment_status "
                "FROM Payments ORDER BY payment_id DESC"
            ).fetchall()


def print_availability(lot: ParkingLot):
    print("\n--- Slot Availability ---")
    for item in lot.get_availability():
        print(f"{item['type']:>4}: {item['available']} available / {item['total']} total "
              f"({item['occupied']} occupied)")


def run_menu():
    db = Database()
    lot = ParkingLot(db)
    menu = """
========== SMART PARKING LOT ==========
1. Park a car
2. Park a bike
3. Remove vehicle / Generate receipt
4. View slot availability
5. View parked vehicles
6. View all parking slots
7. View payment history
0. Exit
"""
    while True:
        print(menu)
        choice = input("Enter choice: ").strip()
        try:
            if choice == "1":
                number = input("Enter car registration number: ")
                slot_id, entry = lot.park_vehicle(Car(number))
                print(f"SUCCESS: Car {number.strip().upper()} parked in slot {slot_id}.")
                print(f"Entry time: {entry.strftime(TIME_FORMAT)}")
            elif choice == "2":
                number = input("Enter bike registration number: ")
                slot_id, entry = lot.park_vehicle(Bike(number))
                print(f"SUCCESS: Bike {number.strip().upper()} parked in slot {slot_id}.")
                print(f"Entry time: {entry.strftime(TIME_FORMAT)}")
            elif choice == "3":
                number = input("Enter vehicle registration number: ")
                print(lot.remove_vehicle(number))
            elif choice == "4":
                print_availability(lot)
            elif choice == "5":
                rows = lot.list_parked_vehicles()
                print("\n--- Parked Vehicles ---")
                if not rows:
                    print("No vehicles are currently parked.")
                for r in rows:
                    print(f"{r['vehicle_number']} | {r['vehicle_type']} | Slot {r['slot_id']} | "
                          f"Since {r['entry_time']}")
            elif choice == "6":
                print("\n--- Parking Slots ---")
                for r in lot.list_slots():
                    state = "OCCUPIED" if r["is_occupied"] else "AVAILABLE"
                    print(f"Slot {r['slot_id']:02} | {r['slot_type']:<4} | {state}"
                          + (f" | {r['vehicle_number']}" if r["vehicle_number"] else ""))
            elif choice == "7":
                rows = lot.payment_history()
                print("\n--- Payment History ---")
                if not rows:
                    print("No payment records.")
                for r in rows:
                    print(f"#{r['payment_id']} | {r['vehicle_number']} | "
                          f"{r['duration_hours']:.2f} hr | Rs. {r['amount']:.2f} | {r['payment_status']}")
            elif choice == "0":
                print("Thank you for using Smart Parking Lot Management System.")
                break
            else:
                print("Invalid menu choice. Enter a number from 0 to 7.")
        except (ParkingError, ValueError, sqlite3.Error) as exc:
            print(f"ERROR: {exc}")
        except KeyboardInterrupt:
            print("\nInterrupted. Returning to menu.")


if __name__ == "__main__":
    run_menu()
