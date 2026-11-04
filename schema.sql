PRAGMA foreign_keys = ON;

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
