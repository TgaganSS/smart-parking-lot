# Test Cases and Results

The following functional cases can be performed from the menu. For automated tests, use a temporary database to avoid altering demo data.

| ID | Test | Expected result |
|---|---|---|
| TC01 | Park a valid car | Allocated a free car slot; record saved |
| TC02 | Park a valid bike | Allocated a free bike slot; record saved |
| TC03 | Park same vehicle twice without checkout | Rejected as already parked |
| TC04 | Enter blank vehicle number | Rejected with validation message |
| TC05 | Fill all car slots, then park another car | No available car slot message |
| TC06 | Checkout a parked vehicle | Payment saved, receipt generated, slot released |
| TC07 | Checkout unknown/not-parked vehicle | Rejected with “not currently parked” |
| TC08 | View availability | Correct total, occupied, and available counts |
| TC09 | Exit and relaunch application | Database records persist |
| TC10 | Enter invalid menu choice | Invalid-choice message; menu continues |
| TC11 | Car fee for 1.0 hour | Rs. 40.00 |
| TC12 | Bike fee for 1.2 hours | Rs. 40.00 (2 billable hours) |

## Expected fee examples
| Vehicle | Duration | Billable hours | Fee |
|---|---:|---:|---:|
| Car | 0.2 h | 1 | Rs. 40 |
| Car | 1.0 h | 1 | Rs. 40 |
| Car | 1.1 h | 2 | Rs. 80 |
| Bike | 2.0 h | 2 | Rs. 40 |
| Bike | 2.4 h | 3 | Rs. 60 |

## Results
The expected results above follow the implemented pricing and allocation rules. Record screenshots of actual execution during the project demonstration.
