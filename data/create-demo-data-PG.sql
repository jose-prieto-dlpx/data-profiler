CREATE TABLE customers (
    customer_id integer PRIMARY KEY,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    email_address VARCHAR(255),
    national_identifier VARCHAR(50)
);
 
CREATE TABLE claims (
    claim_id int PRIMARY KEY,
    customer_id int,
    claim_amount int,
    medical_notes TEXT
);

INSERT INTO customers VALUES (
    1001,
    'Emma',
    'Jensen',
    'emma.jensen@example.com',
    '120378-1234'
);
 
INSERT INTO customers VALUES (
    1002,
    'Michael',
    'Andersen',
    'michael.andersen@example.com',
    '150682-5678'
);
 
INSERT INTO customers VALUES (
    1003,
    'Sarah',
    'Nielsen',
    'sarah.nielsen@example.com',
    '040990-1122'
);

INSERT INTO claims VALUES (
    5001,
    1001,
    42000.00,
    'Patient diagnosed with chronic cardiac condition and referred to specialist.'
);
 
INSERT INTO claims VALUES (
    5002,
    1002,
    12500.00,
    'Customer underwent outpatient treatment and submitted supporting documentation.'
);
 
INSERT INTO claims VALUES (
    5003,
    1003,
    7800.00,
    'Medical review completed. Follow-up consultation recommended.'
);
