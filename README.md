# Smart Parking Lot Management System

**Technology:** Python 3, SQLite, OOP  
**Interface:** Menu-driven command-line application  
**Storage:** Persistent local SQL database (`parking.db`)

## Problem statement
Manual parking management can cause inefficient slot allocation, inaccurate availability records, inconsistent fee calculation, and difficulty maintaining payment records. This system automates vehicle entry/exit, slot assignment, availability tracking, fee calculation, and receipt generation using an object-oriented Python application backed by an SQL database.

## Objectives
- Allocate a compatible free slot when a car or bike arrives.
- Track occupied and available slots.
- Calculate fees by vehicle type and parking duration.
- Generate a receipt and persist payment details.
- Keep vehicle, slot, and payment records in SQLite.
- Demonstrate OOP principles, validation, and exception handling.

## Fee policy
- Car: Rs. 40 per started hour.
- Bike: Rs. 20 per started hour.
- Minimum charge: one hour.
- A fraction of an hour is rounded up to the next billable hour.
- This is a classroom fee policy and can be adjusted in `Car.get_hourly_rate()` / `Bike.get_hourly_rate()`.

## Requirements
Python 3.10 or later. SQLite is included in Python; no third-party package is required.

## Run
1. Extract the project ZIP.
2. Open a terminal in this folder.
3. Run:

   ```bash
   python parking_system.py
   ```

4. Choose a menu option. The database is created automatically on first run.

## Menu
1. Park a car
2. Park a bike
3. Remove vehicle / Generate receipt
4. View slot availability
5. View parked vehicles
6. View all parking slots
7. View payment history
0. Exit

## Database
The application creates `parking.db` in the project folder. `schema.sql` contains the database schema. The database stores:
- `Vehicles`: registration, type, entry/exit timestamps, assigned slot, status.
- `ParkingSlots`: slot type, occupancy, associated vehicle.
- `Payments`: duration, amount, timestamp, and payment status.

Default capacity is 5 car slots and 10 bike slots. To change it, edit the `ParkingLot(db)` initialization in `run_menu()`.

## OOP mapping
- **Abstraction:** `Vehicle` is an abstract base class with abstract `get_hourly_rate()`.
- **Inheritance:** `Car` and `Bike` inherit from `Vehicle`.
- **Overriding:** each subclass implements its own hourly rate.
- **Polymorphism:** `calculate_fee()` calls the overridden rate method.
- **Encapsulation:** vehicle number, slot data, and payment fields use private attributes and properties.
- **Composition/aggregation:** `ParkingLot` manages a collection of `ParkingSlot` objects.
- **Exception handling:** custom parking exceptions and SQLite/input error handling prevent invalid operations.

## Important notes
- This academic prototype records a payment as `PAID` when checkout is processed; it does not connect to a real payment gateway.
- The database file is persistent. For a clean demo, close the application and remove `parking.db`; it will be recreated.
- Use unique registration numbers for active vehicles.
