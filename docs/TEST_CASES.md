# Test Cases and Results

Automated tests are in `test_parking.py` and use a temporary database. Run them with:

```bash
python -m unittest -v test_parking
```

**Result of the latest run: 34 tests, 34 passed, 0 failed** (raw output in `TEST_RESULTS.txt`).

## Functional test cases

| ID | Test | Expected result | Automated test | Actual result |
|---|---|---|---|---|
| TC01 | Park a valid car | Free car slot allocated; visit saved; slot marked occupied | `test_tc01_park_valid_car` | Pass: slot 1 allocated |
| TC02 | Park a valid bike | Free bike slot allocated; vehicle saved as Bike | `test_tc02_park_valid_bike` | Pass: first bike slot allocated |
| TC03 | Park same vehicle twice without checkout (even typed as `ts09 ab-1234`) | Rejected as already parked | `test_tc03_duplicate_parking_rejected` | Pass: `InvalidInputError` |
| TC04 | Blank, symbol-only or too-long vehicle number | Rejected with validation message | `test_tc04_blank_vehicle_number_rejected` | Pass: `InvalidInputError` for every bad input |
| TC05 | Fill all car slots, then park another car | "No available slot" error; bike slots unaffected | `test_tc05_full_car_slots` | Pass: `NoAvailableSlotError`; a bike still parks |
| TC06 | Check out a parked vehicle (2 h 5 min, car) | Payment saved, receipt generated, slot released | `test_tc06_checkout_saves_payment_receipt_and_frees_slot` | Pass: Rs. 120.00, slot free again |
| TC07 | Check out an unknown vehicle | "Not currently parked" error | `test_tc07_checkout_unknown_vehicle` | Pass: `VehicleNotParkedError` |
| TC08 | View availability | Correct total, occupied, available counts | `test_tc08_availability_counts` | Pass: Car 2/1/1, Bike 2/0/2 |
| TC09 | Close and reopen the program | Records persist; slots are not duplicated | `test_tc09_data_persists_between_runs` | Pass |
| TC10 | Enter invalid menu choices (`99`, `abc`) | Message shown; menu continues until `0` | `test_tc10_invalid_menu_choice` | Pass: 2 messages, then clean exit |
| TC11 | Car fee for 1.0 hour | Rs. 40.00 | `test_tc11_car_fee_one_hour` | Pass |
| TC12 | Bike fee for 1.2 hours | Rs. 40.00 (2 billable hours) | `test_tc12_bike_fee_1_2_hours` | Pass |

## Fee calculation (tested in `TestFees.test_fee_table`)
| Vehicle | Duration | Billable hours | Expected | Actual |
|---|---:|---:|---:|---:|
| Car | 0.2 h | 1 | Rs. 40 | Rs. 40 |
| Car | 1.0 h | 1 | Rs. 40 | Rs. 40 |
| Car | 1.1 h | 2 | Rs. 80 | Rs. 80 |
| Bike | 2.0 h | 2 | Rs. 40 | Rs. 40 |
| Bike | 2.4 h | 3 | Rs. 60 | Rs. 60 |
| Bike | 0.0 h | 1 (minimum) | Rs. 20 | Rs. 20 |

## Additional tests

| Area | What is checked | Result |
|---|---|---|
| Fees | Floating-point noise (3.0000000000001 h) is not billed as an extra hour; negative, NaN, text, `None`, `True` durations rejected | Pass |
| OOP | `Vehicle` cannot be instantiated; Car/Bike rates are 40 and 20 | Pass |
| Encapsulation | Validating setters on vehicle number, slot type, payment amount and status; a rejected update leaves the old value; `vehicle_type` is read-only | Pass |
| Database | Re-parking the same vehicle keeps both visits and both payments | Pass |
| Database | A plate can change type (Car then Bike) between visits | Pass |
| Database | Unique indexes stop a second open visit for one vehicle or one slot | Pass |
| Database | `CHECK` constraints and foreign keys reject invalid rows | Pass |
| Database | A failed operation rolls back (no partial vehicle row) | Pass |
| Database | Triggers free the slot at checkout; view `v_free_slots` updates | Pass |
| Database | Connections are closed after every session | Pass |
| SQL reports | Payment history uses a 3-table JOIN; daily revenue per day and type is correct (total Rs. 160 in the test data) | Pass |
| Migration | A version 1 database is renamed to `.bak` and replaced | Pass |
| Files | Receipt text file is written with the right content | Pass |
| Files | If the receipt folder is unwritable, the payment is still saved | Pass |
| Files | CSV export has the correct rows and amounts; with no payments it has only the header | Pass |

## Manual demonstration
A full menu session (parking, validation errors, checkout, receipt, history, revenue report, CSV export, invalid choice, exit) is recorded in `sample_run/session_transcript.txt`, with screenshots in `screenshots/`, the generated receipts in `sample_run/receipts/` and the exported CSV in `sample_run/payments.csv`.
