# CB-330 Fraud Detection and Transaction Monitoring Rules

## 1. Velocity Rules
More than 5 card-not-present transactions from a single account within a
10-minute window triggers a soft decline and a step-up authentication
challenge. More than 12 such transactions in one hour triggers an automatic
hard block pending analyst review.

## 2. Geographic Impossibility
Two card-present authorizations occurring more than 500 miles apart within a
2-hour window are flagged as geographically impossible and routed to the
fraud queue at Priority 1.

## 3. Dollar Thresholds
Any single wire transfer at or above $10,000 requires dual authorization.
Aggregate outbound wires at or above $50,000 within a rolling 24-hour period
require Treasury Operations sign-off in addition to dual authorization.

## 4. Analyst Service Levels
Priority 1 fraud alerts must receive analyst disposition within 15 minutes.
Priority 2 alerts must be dispositioned within 4 hours. Priority 3 alerts
must be dispositioned within 2 business days.

## 5. Customer Notification
Confirmed fraud on a consumer account requires customer notification within
24 hours and provisional credit within 10 business days under Regulation E.

## 6. Model Governance
All fraud scoring models must be revalidated annually by the independent
Model Risk Management function. Champion-challenger results must be retained
for seven years.
