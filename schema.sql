-- Smart Parking Lot Management System : database schema (SQLite)
-- Loaded automatically by parking_system.py (Database.initialize).
-- Can also be run by hand:  sqlite3 parking.db < schema.sql

PRAGMA foreign_keys = ON;

-- One row per physical vehicle (the plate is the natural key).
CREATE TABLE IF NOT EXISTS Vehicles (
    vehicle_number TEXT PRIMARY KEY,
    vehicle_type   TEXT NOT NULL CHECK(vehicle_type IN ('Car','Bike')),
    registered_at  TEXT NOT NULL
);

-- Physical slots. is_occupied is kept in sync by the triggers below.
CREATE TABLE IF NOT EXISTS ParkingSlots (
    slot_id     INTEGER PRIMARY KEY,
    slot_type   TEXT NOT NULL CHECK(slot_type IN ('Car','Bike','Any')),
    is_occupied INTEGER NOT NULL DEFAULT 0 CHECK(is_occupied IN (0,1))
);

-- One row per parking session ("ticket"). A vehicle can have many visits,
-- so re-parking never overwrites earlier history.
CREATE TABLE IF NOT EXISTS Visits (
    visit_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_number TEXT    NOT NULL,
    slot_id        INTEGER NOT NULL,
    entry_time     TEXT    NOT NULL,
    exit_time      TEXT,                       -- NULL while the vehicle is parked
    FOREIGN KEY(vehicle_number) REFERENCES Vehicles(vehicle_number),
    FOREIGN KEY(slot_id)        REFERENCES ParkingSlots(slot_id),
    CHECK(exit_time IS NULL OR exit_time >= entry_time)
);

-- Integrity rules enforced by the database itself:
-- a vehicle can be parked only once at a time, and a slot holds one vehicle.
CREATE UNIQUE INDEX IF NOT EXISTS idx_open_visit_per_vehicle
    ON Visits(vehicle_number) WHERE exit_time IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_open_visit_per_slot
    ON Visits(slot_id) WHERE exit_time IS NULL;

-- Exactly one payment per completed visit.
CREATE TABLE IF NOT EXISTS Payments (
    payment_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id       INTEGER NOT NULL UNIQUE,
    duration_hours REAL    NOT NULL CHECK(duration_hours >= 0),
    amount         REAL    NOT NULL CHECK(amount >= 0),
    payment_time   TEXT    NOT NULL,
    payment_status TEXT    NOT NULL CHECK(payment_status IN ('PAID','FAILED')),
    FOREIGN KEY(visit_id) REFERENCES Visits(visit_id)
);

-- Triggers: slot occupancy follows the visit lifecycle automatically.
CREATE TRIGGER IF NOT EXISTS trg_visit_start
AFTER INSERT ON Visits
WHEN NEW.exit_time IS NULL
BEGIN
    UPDATE ParkingSlots SET is_occupied = 1 WHERE slot_id = NEW.slot_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_visit_end
AFTER UPDATE OF exit_time ON Visits
WHEN OLD.exit_time IS NULL AND NEW.exit_time IS NOT NULL
BEGIN
    UPDATE ParkingSlots SET is_occupied = 0 WHERE slot_id = NEW.slot_id;
END;

-- Views: reusable reports.
CREATE VIEW IF NOT EXISTS v_free_slots AS
    SELECT slot_id, slot_type
    FROM ParkingSlots
    WHERE is_occupied = 0;

CREATE VIEW IF NOT EXISTS v_daily_revenue AS
    SELECT date(p.payment_time)  AS day,
           v.vehicle_type        AS vehicle_type,
           COUNT(*)              AS payments,
           ROUND(SUM(p.amount), 2) AS revenue
    FROM Payments p
    JOIN Visits   vi ON vi.visit_id       = p.visit_id
    JOIN Vehicles v  ON v.vehicle_number  = vi.vehicle_number
    WHERE p.payment_status = 'PAID'
    GROUP BY date(p.payment_time), v.vehicle_type;
