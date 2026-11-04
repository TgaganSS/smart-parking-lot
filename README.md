# Smart Parking Lot Management System

**Technology:** Python 3, SQLite (SQL), OOP, text/CSV file handling
**Interface:** Menu-driven command-line application
**Storage:** SQLite database (`parking.db`), receipts as text files, payment history as CSV

## Problem statement
Manual parking management causes inefficient slot allocation, inaccurate availability records, inconsistent fee calculation and poor payment records. This system automates vehicle entry/exit, slot assignment, availability tracking, fee calculation and receipt generation using an object-oriented Python application backed by an SQL database.

## Objectives
- Allocate a compatible free slot when a car or bike arrives.
- Track occupied and available slots.
- Calculate fees by vehicle type and parking duration.
- Generate a receipt (printed **and saved as a text file**) and persist payment details.
- Keep vehicle, slot, visit and payment records in SQLite, with a full history of every visit.
- Report revenue with SQL (`JOIN`, `GROUP BY`, views) and export payments to **CSV**.
- Demonstrate OOP principles, validation and exception handling.

## Project layout
```
parking_system.py     application: all classes + menu
schema.sql            database schema (tables, indexes, triggers, views); loaded by the program
test_parking.py       automated tests (unittest, temporary database)
docs/
  PROJECT_REPORT.md   full report (problem, design, algorithms, results)
  TEST_CASES.md       test cases with actual results
  TEST_RESULTS.txt    raw output of the automated test run
  diagrams/           UML class diagram + ER diagram (PNG, PDF, SVG, Graphviz source)
  screenshots/        sample input/output screenshots
  sample_run/         transcript, receipts and CSV produced by that run
receipts/             created at run time: receipt_0001.txt, ...
exports/              created at run time: payments.csv
```

## Requirements
Python 3.10 or later. SQLite is included in Python; no third-party packages are needed.
## Screenshots

### Parking and input validation
<img src="docs/screenshots/01_parking_and_validation.png" width="650" alt="Parking and validation">

### Availability and slot map
<img src="docs/screenshots/02_availability_and_slots.png" width="650" alt="Availability and slots">

### Checkout, receipt and payment history
<img src="docs/screenshots/03_checkout_receipt_history.png" width="650" alt="Checkout and receipt">

### Revenue report, CSV export and exit
<img src="docs/screenshots/04_reports_export_exit.png" width="650" alt="Reports and export">

## Diagrams

### UML class diagram
![UML class diagram](docs/diagrams/class_diagram.png)

### ER diagram
![ER diagram](docs/diagrams/er_diagram.png)

## Run
```bash
python parking_system.py
```
The database, `receipts/` and `exports/` are created automatically.

## Run the tests
```bash
python -m unittest -v test_parking
```
The tests use a temporary database and never touch your real data.

## Menu
| # | Option |
|---|---|
| 1 | Park a car |
| 2 | Park a bike |
| 3 | Remove vehicle / generate receipt (prints it and saves `receipts/receipt_<id>.txt`) |
| 4 | View slot availability |
| 5 | View parked vehicles |
| 6 | View all parking slots |
| 7 | View payment history (JOIN of Payments, Visits and Vehicles) |
| 8 | Daily revenue report (`SUM ... GROUP BY` day and vehicle type, plus total) |
| 9 | Vehicle visit history (one vehicle or all) |
| 10 | Export payment history to `exports/payments.csv` |
| 0 | Exit |

## Fee policy
- Car: Rs. 40 per started hour. Bike: Rs. 20 per started hour.
- Minimum charge: one hour. Any part of an hour is rounded up (`math.ceil`).
- Rates are defined in `Car.get_hourly_rate()` / `Bike.get_hourly_rate()`.

## Registration numbers
Input is upper-cased and spaces/hyphens are removed, so `tn 09-ab 1234` and `TN09AB1234` are the same vehicle. Only letters and digits are accepted (1 to 15 characters).

## Database (`schema.sql`)
| Table | Purpose |
|---|---|
| `Vehicles` | one row per vehicle (plate = primary key), its type |
| `ParkingSlots` | slot id, slot type, occupied flag (kept in sync by triggers) |
| `Visits` | one row per parking session: vehicle, slot, entry time, exit time (`NULL` while parked) |
| `Payments` | one payment per completed visit: duration, amount, time, status |

Other database features:
- Foreign keys, `CHECK` constraints and **partial unique indexes** (a vehicle can only have one open visit; a slot can only hold one open visit).
- **Triggers** `trg_visit_start` / `trg_visit_end` mark a slot occupied/free automatically.
- **Views** `v_free_slots` and `v_daily_revenue`.
- Every operation runs in one transaction (commit or rollback), and every connection is closed afterwards.
- Because each parking session is its own row in `Visits`, parking the same vehicle again never overwrites its earlier history.

Default capacity is 5 car slots and 10 bike slots (change it in the `ParkingLot(db)` call in `run_menu()`).

If you used the first version of this project, the old `parking.db` has a different structure. The program detects this, renames it to `parking_legacy_<timestamp>.bak` and starts a fresh database.

## File handling
- **Text files:** each receipt is saved as `receipts/receipt_<id>.txt` (id zero-padded to 4 digits).
- **CSV:** menu option 10 writes `exports/payments.csv` (opens directly in Excel).
- If a receipt file cannot be written, the payment stays recorded and the user gets a warning.

## OOP mapping
- **Abstraction:** `Vehicle` is an abstract base class with abstract `get_hourly_rate()`.
- **Inheritance:** `Car` and `Bike` inherit from `Vehicle`.
- **Method overriding:** each subclass implements its own hourly rate.
- **Polymorphism:** `calculate_fee()` works on any `Vehicle` and calls the overridden rate; `Vehicle.create()` builds the right subclass from a database row.
- **Encapsulation:** private attributes with properties; **validating setters** on `Vehicle.vehicle_number`, `ParkingSlot.slot_type`, `Payment.amount` and `Payment.status` reject bad updates and leave the old value unchanged.
- **Composition:** `ParkingLot` owns a list of `ParkingSlot` objects (rebuilt from the database on start-up) and uses `ParkingSlot.accepts()` to choose a slot.
- **Exception handling:** `ParkingError` and its subclasses (`InvalidInputError`, `NoAvailableSlotError`, `VehicleNotParkedError`), plus handling of SQLite, file and keyboard errors so the menu never crashes.

## Documentation
Everything required by the submission checklist is in `docs/`: problem statement and objectives (this README and the report), UML class diagram (`docs/diagrams/class_diagram.png` / `.pdf`), ER diagram, source code, screenshots, test cases and results.

## Notes
- A payment is recorded as `PAID` at checkout; there is no real payment gateway.
- The screenshots in `docs/screenshots/` were rendered from the captured output of a real run (`docs/sample_run/session_transcript.txt`). Earlier days in that run were pre-loaded through the program's own API with explicit timestamps so the revenue report shows several dates. To submit your own screenshots instead, run the program and capture your terminal.
- For a clean demo, close the program and delete `parking.db`, `receipts/` and `exports/`.

## Design decisions

**Why SQLite?**
The assignment asks for SQL storage of vehicles, slots and payments. SQLite ships with Python, needs no server or installation, and still supports real SQL features (foreign keys, triggers, views, transactions).

**Why a separate `Visits` table?**
A vehicle can park many times. Storing entry and exit times in `Vehicles` would overwrite earlier history. Each parking session is its own `Visits` row, so every visit and payment is preserved.

**Why enforce rules in the database as well as in Python?**
Partial unique indexes guarantee that a vehicle has at most one open visit and a slot holds at most one open visit. Even if the Python code had a bug, the database would reject the invalid state. Triggers keep `is_occupied` in sync with the visit lifecycle, so the flag cannot drift.

**Why one transaction per operation?**
Parking and checkout each run inside a single commit-or-rollback transaction (`Database.session()`). A failure halfway never leaves a half-written vehicle, visit or payment.

**Why is the receipt file written after the commit?**
The payment is the important record. If the receipt file cannot be written (for example, a permissions error), the payment stays saved and the user gets a warning instead of losing the transaction.

**Why is `Vehicle` abstract?**
A generic "vehicle" has no hourly rate, so `get_hourly_rate()` is abstract. `Car` and `Bike` override it, and `calculate_fee()` works on any `Vehicle` through polymorphism. Adding a new type (for example, a Truck) needs only a new subclass and one entry in `VEHICLE_TYPES`.

**Why round up to started hours?**
This is the common parking-lot billing rule: any part of an hour is charged as a full hour, with a one-hour minimum. `round(duration, 6)` is applied first so floating-point noise (for example, 1.0000000000002 hours) is not billed as an extra hour.

**Why normalise registration numbers?**
`tn 09-ab 1234` and `TN09AB1234` are the same vehicle. Normalising on input prevents duplicate records and false "not parked" errors at checkout.

**Why SQLite plus text and CSV files?**
SQLite is the source of truth for all data. Text receipts and the CSV export satisfy the file-handling requirement and give the user human-readable output.

## Limitations and future work
- Single-user, local application (no concurrent multi-gate access).
- Slot allocation picks the first free compatible slot; it does not consider distance to the exit.
- Payment is recorded as `PAID` at checkout; there is no real payment gateway.
- Possible extensions: reserved slots, monthly passes, peak-hour pricing, a GUI or web front end.
