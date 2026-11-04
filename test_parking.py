"""Automated tests for the Smart Parking Lot Management System.

Run:  python -m unittest -v test_parking
Every test uses a temporary database and temporary folders, so real data is never touched.
"""
import csv
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from parking_system import (
    Bike, Car, Database, InvalidInputError, NoAvailableSlotError, ParkingLot,
    ParkingSlot, Payment, Vehicle, VehicleNotParkedError, TIME_FORMAT,
)

T0 = datetime(2026, 11, 4, 10, 0, 0)


class ParkingTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db = Database(self.tmp / "test.db")
        self.lot = ParkingLot(self.db, total_car_slots=2, total_bike_slots=2,
                              receipt_dir=self.tmp / "receipts", export_dir=self.tmp / "exports")

    def tearDown(self):
        self._tmp.cleanup()

    def scalar(self, sql, params=()):
        with self.db.session() as conn:
            return conn.execute(sql, params).fetchone()[0]


class TestFunctionalCases(ParkingTestCase):
    """TC01-TC12 from docs/TEST_CASES.md."""

    def test_tc01_park_valid_car(self):
        slot, entry = self.lot.park_vehicle(Car("TS09AB1234"), T0)
        self.assertEqual(slot, 1)
        self.assertEqual(entry, T0)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM Visits WHERE exit_time IS NULL"), 1)
        self.assertEqual(self.scalar("SELECT is_occupied FROM ParkingSlots WHERE slot_id=1"), 1)

    def test_tc02_park_valid_bike(self):
        slot, _ = self.lot.park_vehicle(Bike("KA01XY9999"), T0)
        self.assertEqual(slot, 3)  # slots 1-2 are car slots, 3-4 are bike slots
        self.assertEqual(self.scalar("SELECT vehicle_type FROM Vehicles WHERE vehicle_number='KA01XY9999'"), "Bike")

    def test_tc03_duplicate_parking_rejected(self):
        self.lot.park_vehicle(Car("TS09AB1234"), T0)
        with self.assertRaises(InvalidInputError):
            self.lot.park_vehicle(Car("ts09 ab-1234"), T0)  # same plate, different formatting

    def test_tc04_blank_vehicle_number_rejected(self):
        for bad in ("", "   ", "!!!", "A" * 16):
            with self.subTest(bad=bad), self.assertRaises(InvalidInputError):
                Car(bad)

    def test_tc05_full_car_slots(self):
        self.lot.park_vehicle(Car("CAR1"), T0)
        self.lot.park_vehicle(Car("CAR2"), T0)
        with self.assertRaises(NoAvailableSlotError):
            self.lot.park_vehicle(Car("CAR3"), T0)
        # bike slots are unaffected
        self.lot.park_vehicle(Bike("BIKE1"), T0)

    def test_tc06_checkout_saves_payment_receipt_and_frees_slot(self):
        self.lot.park_vehicle(Car("TS09AB1234"), T0)
        receipt = self.lot.remove_vehicle("TS09AB1234", T0 + timedelta(minutes=125))
        self.assertEqual(receipt.amount, 120.0)  # 2.08 h -> 3 billable hours * 40
        self.assertIn("Rs. 120.00", receipt.render())
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM Payments"), 1)
        self.assertEqual(self.scalar("SELECT is_occupied FROM ParkingSlots WHERE slot_id=1"), 0)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM Visits WHERE exit_time IS NULL"), 0)

    def test_tc07_checkout_unknown_vehicle(self):
        with self.assertRaises(VehicleNotParkedError):
            self.lot.remove_vehicle("NOTHERE1")

    def test_tc08_availability_counts(self):
        self.lot.park_vehicle(Car("CAR1"), T0)
        counts = {r["type"]: r for r in self.lot.get_availability()}
        self.assertEqual((counts["Car"]["total"], counts["Car"]["occupied"], counts["Car"]["available"]), (2, 1, 1))
        self.assertEqual((counts["Bike"]["total"], counts["Bike"]["occupied"], counts["Bike"]["available"]), (2, 0, 2))

    def test_tc09_data_persists_between_runs(self):
        self.lot.park_vehicle(Car("TS09AB1234"), T0)
        reopened = ParkingLot(Database(self.tmp / "test.db"), 2, 2,
                              receipt_dir=self.tmp / "receipts", export_dir=self.tmp / "exports")
        parked = reopened.list_parked_vehicles()
        self.assertEqual([r["vehicle_number"] for r in parked], ["TS09AB1234"])
        self.assertEqual(len(reopened.slots), 4)  # slots were not duplicated by re-seeding

    def test_tc10_invalid_menu_choice(self):
        import io
        from contextlib import redirect_stdout
        from unittest import mock
        import parking_system
        buffer = io.StringIO()
        with mock.patch.object(parking_system, "Database", return_value=self.db), \
             mock.patch.object(parking_system, "ParkingLot", return_value=self.lot), \
             mock.patch("builtins.input", side_effect=["99", "abc", "0"]), \
             redirect_stdout(buffer):
            parking_system.run_menu()
        output = buffer.getvalue()
        self.assertEqual(output.count("Invalid menu choice"), 2)
        self.assertIn("Thank you", output)  # menu kept running until option 0

    def test_tc11_car_fee_one_hour(self):
        self.assertEqual(Car("C1").calculate_fee(1.0), 40.0)

    def test_tc12_bike_fee_1_2_hours(self):
        self.assertEqual(Bike("B1").calculate_fee(1.2), 40.0)


class TestFees(unittest.TestCase):
    def test_fee_table(self):
        cases = [(Car("C"), 0.2, 40), (Car("C"), 1.0, 40), (Car("C"), 1.1, 80),
                 (Bike("B"), 2.0, 40), (Bike("B"), 2.4, 60), (Bike("B"), 0.0, 20)]
        for vehicle, hours, expected in cases:
            with self.subTest(vehicle=vehicle.vehicle_type, hours=hours):
                self.assertEqual(vehicle.calculate_fee(hours), expected)

    def test_floating_point_noise_is_not_billed_as_extra_hour(self):
        self.assertEqual(Car("C").calculate_fee(3.0000000000001), 120.0)

    def test_negative_or_non_numeric_duration_rejected(self):
        for bad in (-0.5, float("nan"), "2", None, True):
            with self.subTest(bad=bad), self.assertRaises(InvalidInputError):
                Car("C").calculate_fee(bad)

    def test_polymorphism_and_abstraction(self):
        with self.assertRaises(TypeError):
            Vehicle("X1")  # abstract class cannot be instantiated
        self.assertEqual([v.get_hourly_rate() for v in (Car("C"), Bike("B"))], [40.0, 20.0])


class TestEncapsulation(unittest.TestCase):
    def test_vehicle_number_setter_validates_and_normalizes(self):
        car = Car("ts09ab1234")
        self.assertEqual(car.vehicle_number, "TS09AB1234")
        car.vehicle_number = "tn 01-cd 5678"
        self.assertEqual(car.vehicle_number, "TN01CD5678")
        with self.assertRaises(InvalidInputError):
            car.vehicle_number = ""
        self.assertEqual(car.vehicle_number, "TN01CD5678")  # failed update changed nothing

    def test_slot_type_setter_validates(self):
        slot = ParkingSlot(1, "Car")
        slot.slot_type = "Bike"
        self.assertEqual(slot.slot_type, "Bike")
        with self.assertRaises(InvalidInputError):
            slot.slot_type = "Truck"
        self.assertEqual(slot.slot_type, "Bike")
        with self.assertRaises(InvalidInputError):
            ParkingSlot(0, "Car")

    def test_slot_accepts(self):
        self.assertTrue(ParkingSlot(1, "Car").accepts(Car("C")))
        self.assertFalse(ParkingSlot(1, "Car").accepts(Bike("B")))
        self.assertTrue(ParkingSlot(1, "Any").accepts(Bike("B")))

    def test_payment_amount_setter_validates(self):
        payment = Payment(1, 1.0, 40)
        with self.assertRaises(InvalidInputError):
            payment.amount = -1
        with self.assertRaises(InvalidInputError):
            payment.status = "MAYBE"
        self.assertEqual(payment.amount, 40.0)

    def test_private_attributes_not_directly_writable(self):
        with self.assertRaises(AttributeError):
            Car("C1").vehicle_type = "Bike"  # read-only property


class TestDatabaseAndSql(ParkingTestCase):
    def test_reparking_same_vehicle_keeps_history(self):
        self.lot.park_vehicle(Car("TS09AB1234"), T0)
        self.lot.remove_vehicle("TS09AB1234", T0 + timedelta(hours=1))
        self.lot.park_vehicle(Car("TS09AB1234"), T0 + timedelta(hours=5))
        self.lot.remove_vehicle("TS09AB1234", T0 + timedelta(hours=7))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM Visits"), 2)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM Payments"), 2)
        history = self.lot.visit_history("ts09ab1234")
        self.assertEqual([r["amount"] for r in history], [40.0, 80.0])

    def test_vehicle_type_can_change_for_same_plate(self):
        self.lot.park_vehicle(Car("SWAP1"), T0)
        self.lot.remove_vehicle("SWAP1", T0 + timedelta(hours=1))
        self.lot.park_vehicle(Bike("SWAP1"), T0 + timedelta(hours=2))
        row = self.lot.list_parked_vehicles()[0]
        self.assertEqual((row["vehicle_type"], row["slot_id"]), ("Bike", 3))

    def test_database_enforces_one_open_visit_per_vehicle_and_slot(self):
        self.lot.park_vehicle(Car("CAR1"), T0)
        with self.assertRaises(sqlite3.IntegrityError), self.db.session(write=True) as conn:
            conn.execute("INSERT INTO Visits(vehicle_number,slot_id,entry_time) VALUES('CAR1',2,?)",
                         (T0.strftime(TIME_FORMAT),))
        self.lot.park_vehicle(Car("CAR2"), T0)
        # slot 1 is held by CAR1; a second open visit in it must fail
        with self.assertRaises(sqlite3.IntegrityError), self.db.session(write=True) as conn:
            conn.execute("INSERT INTO Vehicles VALUES('OTHER','Car',?)", (T0.strftime(TIME_FORMAT),))
            conn.execute("INSERT INTO Visits(vehicle_number,slot_id,entry_time) VALUES('OTHER',1,?)",
                         (T0.strftime(TIME_FORMAT),))

    def test_check_constraints_and_foreign_keys(self):
        with self.assertRaises(sqlite3.IntegrityError), self.db.session(write=True) as conn:
            conn.execute("INSERT INTO ParkingSlots(slot_id,slot_type) VALUES(99,'Truck')")
        with self.assertRaises(sqlite3.IntegrityError), self.db.session(write=True) as conn:
            conn.execute("INSERT INTO Payments VALUES(NULL,12345,1,10,'2026-01-01 00:00:00','PAID')")

    def test_failed_operation_rolls_back(self):
        self.lot.park_vehicle(Car("CAR1"), T0)
        self.lot.park_vehicle(Car("CAR2"), T0)
        with self.assertRaises(NoAvailableSlotError):
            self.lot.park_vehicle(Car("CAR3"), T0)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM Vehicles WHERE vehicle_number='CAR3'"), 0)

    def test_triggers_free_slot_on_exit(self):
        self.lot.park_vehicle(Bike("B1"), T0)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM v_free_slots WHERE slot_type='Bike'"), 1)
        self.lot.remove_vehicle("B1", T0 + timedelta(minutes=30))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM v_free_slots WHERE slot_type='Bike'"), 2)

    def test_connections_are_closed(self):
        with self.db.session() as conn:
            pass
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_payment_history_join_and_revenue_report(self):
        self.lot.park_vehicle(Car("CAR1"), T0)
        self.lot.park_vehicle(Bike("BIKE1"), T0)
        self.lot.remove_vehicle("CAR1", T0 + timedelta(hours=2))                      # Rs. 80
        self.lot.remove_vehicle("BIKE1", T0 + timedelta(hours=1, minutes=1))          # Rs. 40
        self.lot.park_vehicle(Car("CAR1"), T0 + timedelta(days=1))
        self.lot.remove_vehicle("CAR1", T0 + timedelta(days=1, minutes=10))           # Rs. 40, next day
        history = self.lot.payment_history()
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["vehicle_number"], "CAR1")  # newest first, vehicle comes from JOIN
        rows, total = self.lot.daily_revenue()
        self.assertEqual(total, 160.0)
        by_key = {(r["day"], r["vehicle_type"]): (r["payments"], r["revenue"]) for r in rows}
        self.assertEqual(by_key[("2026-11-04", "Car")], (1, 80.0))
        self.assertEqual(by_key[("2026-11-04", "Bike")], (1, 40.0))
        self.assertEqual(by_key[("2026-11-05", "Car")], (1, 40.0))

    def test_legacy_database_is_backed_aside(self):
        legacy = self.tmp / "old.db"
        conn = sqlite3.connect(legacy)
        conn.execute("CREATE TABLE Vehicles (vehicle_number TEXT PRIMARY KEY, entry_time TEXT)")
        conn.commit()
        conn.close()
        db = Database(legacy)
        self.assertIsNotNone(db.legacy_backup)
        self.assertTrue(db.legacy_backup.exists())
        with db.session() as c:
            columns = {r[1] for r in c.execute("PRAGMA table_info(Vehicles)")}
        self.assertNotIn("entry_time", columns)


class TestFileHandling(ParkingTestCase):
    def test_receipt_text_file_is_written(self):
        self.lot.park_vehicle(Car("TS09AB1234"), T0)
        receipt = self.lot.remove_vehicle("TS09AB1234", T0 + timedelta(hours=2))
        path = self.tmp / "receipts" / f"receipt_{receipt.receipt_id:04d}.txt"
        self.assertEqual(receipt.file_path, path)
        text = path.read_text(encoding="utf-8")
        self.assertIn("SMART PARKING RECEIPT", text)
        self.assertIn("TS09AB1234", text)
        self.assertIn("Rs. 80.00", text)

    def test_receipt_file_failure_does_not_undo_payment(self):
        blocker = self.tmp / "not_a_folder"
        blocker.write_text("x")
        lot = ParkingLot(self.db, 2, 2, receipt_dir=blocker / "sub", export_dir=self.tmp / "exports")
        lot.park_vehicle(Car("CAR1"), T0)
        receipt = lot.remove_vehicle("CAR1", T0 + timedelta(hours=1))
        self.assertIsNone(receipt.file_path)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM Payments"), 1)

    def test_csv_export(self):
        self.lot.park_vehicle(Car("CAR1"), T0)
        self.lot.remove_vehicle("CAR1", T0 + timedelta(hours=2))
        self.lot.park_vehicle(Bike("BIKE1"), T0)
        self.lot.remove_vehicle("BIKE1", T0 + timedelta(minutes=20))
        path = self.lot.export_payments_csv()
        self.assertEqual(path, self.tmp / "exports" / "payments.csv")
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["vehicle_number"]: r["amount"] for r in rows}, {"CAR1": "80.00", "BIKE1": "20.00"})

    def test_csv_export_with_no_payments_has_header_only(self):
        path = self.lot.export_payments_csv()
        self.assertEqual(len(path.read_text(encoding="utf-8").strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
