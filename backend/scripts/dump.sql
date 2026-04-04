PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE saccos (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	email VARCHAR, 
	phone VARCHAR, 
	address VARCHAR, 
	registration_no VARCHAR, 
	website VARCHAR, 
	status VARCHAR, 
	created_at DATETIME, 
	membership_fee FLOAT, 
	shares_enabled BOOLEAN, 
	dividends_enabled BOOLEAN, 
	referred_by_id INTEGER, 
	referral_commission_paid FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(referred_by_id) REFERENCES users (id)
);
INSERT INTO saccos VALUES(1,'Test SACCO','test@sacco.com','+256700000000','Kampala, Uganda',NULL,NULL,'active','2026-04-04 11:40:43.452388',50000.0,0,0,NULL,0.0);
CREATE TABLE users (
	id INTEGER NOT NULL, 
	full_name VARCHAR, 
	username VARCHAR, 
	email VARCHAR NOT NULL, 
	password_hash VARCHAR NOT NULL, 
	role VARCHAR(14) NOT NULL, 
	sacco_id INTEGER, 
	created_at DATETIME, 
	is_active BOOLEAN, 
	password_reset_required BOOLEAN, 
	last_login DATETIME, 
	last_activity DATETIME, 
	login_count INTEGER, 
	profile_picture VARCHAR, 
	date_of_birth DATETIME, 
	national_id VARCHAR, 
	phone VARCHAR, 
	address VARCHAR, 
	is_staff BOOLEAN, 
	can_apply_for_loans BOOLEAN, 
	can_receive_dividends BOOLEAN, 
	requires_approval_for_loans BOOLEAN, 
	linked_member_account_id INTEGER, 
	linked_admin_id INTEGER, 
	referred_by_id INTEGER, 
	referral_code VARCHAR(20), 
	total_referrals INTEGER, 
	sacco_referral_code VARCHAR(20), 
	sacco_referral_earnings FLOAT, 
	sacco_referral_commission_rate FLOAT, 
	member_referral_code VARCHAR(20), 
	member_referral_earnings FLOAT, 
	member_referral_commission_rate FLOAT, 
	is_agent BOOLEAN, 
	agent_referral_code VARCHAR(20), 
	is_approved BOOLEAN, 
	approved_at DATETIME, 
	approved_by INTEGER, 
	rejection_reason VARCHAR(500), 
	PRIMARY KEY (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id), 
	FOREIGN KEY(referred_by_id) REFERENCES users (id), 
	UNIQUE (sacco_referral_code), 
	UNIQUE (member_referral_code), 
	UNIQUE (agent_referral_code), 
	FOREIGN KEY(approved_by) REFERENCES users (id)
);
INSERT INTO users VALUES(1,'Super Administrator','superadmin','superadmin@cheontec.com','$2b$12$zvbx9CURseBYhpACmeSzP.q1Gu5KISpeHO9SYc0YetTk0rgRSUUXO','SUPER_ADMIN',NULL,'2026-04-04 11:40:43.423477',1,0,'2026-04-04 11:42:04.866276','2026-04-04 11:42:04.866276',1,NULL,NULL,NULL,NULL,NULL,1,0,0,0,NULL,NULL,NULL,NULL,0,NULL,0.0,15.0,NULL,0.0,3.0,0,NULL,0,NULL,NULL,NULL);
INSERT INTO users VALUES(2,'Test Manager','test.manager','manager@test.com','$2b$12$p2ZTszT6oke.HH8QI3ccbu42Ngr925BbS2Ln6OIG.ua9L2jPyWyf6','MANAGER',1,'2026-04-04 11:40:43.896211',1,0,'2026-04-04 12:41:23.687670','2026-04-04 12:41:23.687670',2,NULL,NULL,NULL,NULL,NULL,1,0,1,0,3,NULL,NULL,NULL,0,NULL,0.0,15.0,NULL,0.0,3.0,0,NULL,0,NULL,NULL,NULL);
INSERT INTO users VALUES(3,'Test Manager (Member)','test.manager.member','manager_member@test.com','$2b$12$7Kk8i7iMcGWIcvQKeNzUG.YZM6deWugOTpd5Bnz0AjUax2ZvjssJ2','MEMBER',1,'2026-04-04 11:40:44.316659',1,0,NULL,NULL,0,NULL,NULL,NULL,NULL,NULL,1,1,1,1,NULL,2,NULL,NULL,0,NULL,0.0,15.0,NULL,0.0,3.0,0,NULL,0,NULL,NULL,NULL);
INSERT INTO users VALUES(4,'Test Accountant','test.accountant','accountant@test.com','$2b$12$MZqP6a32SrqsxWk4vVXcdOMCP42w3UVtghZzGu0LXSO3W5LRua1re','ACCOUNTANT',1,'2026-04-04 11:40:44.800313',1,0,'2026-04-04 11:43:46.066459','2026-04-04 11:43:46.066459',1,NULL,NULL,NULL,NULL,NULL,1,0,1,0,NULL,NULL,NULL,NULL,0,NULL,0.0,15.0,NULL,0.0,3.0,0,NULL,0,NULL,NULL,NULL);
INSERT INTO users VALUES(5,'Test Credit Officer','test.credit','creditofficer@test.com','$2b$12$uB8a/iENtVxrNtk3a065eeU7ai5EStt/QVcZ7z81Qk7hBG5ShHfgW','CREDIT_OFFICER',1,'2026-04-04 11:40:45.223463',1,0,'2026-04-04 11:44:55.003653','2026-04-04 11:44:55.003653',1,NULL,NULL,NULL,NULL,NULL,1,0,1,0,NULL,NULL,NULL,NULL,0,NULL,0.0,15.0,NULL,0.0,3.0,0,NULL,0,NULL,NULL,NULL);
INSERT INTO users VALUES(6,'Test Member','test.member','member@test.com','$2b$12$QjgFfmAGrUbjCy//2w3b1eBgnX8kVMu/bkYlenxchaltSFxZXfkJy','MEMBER',1,'2026-04-04 11:40:45.647278',1,0,'2026-04-04 12:32:47.276496','2026-04-04 12:32:47.276496',1,NULL,NULL,NULL,NULL,NULL,0,1,1,0,NULL,NULL,NULL,NULL,0,NULL,0.0,15.0,NULL,0.0,3.0,0,NULL,0,NULL,NULL,NULL);
CREATE TABLE system_settings (
	id INTEGER NOT NULL, 
	"key" VARCHAR, 
	value VARCHAR, 
	description VARCHAR, 
	PRIMARY KEY (id), 
	UNIQUE ("key")
);
CREATE TABLE pending_deposits (
	id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	amount FLOAT NOT NULL, 
	payment_method VARCHAR(50), 
	description VARCHAR(200), 
	reference_number VARCHAR(100), 
	status VARCHAR(20), 
	timestamp DATETIME, 
	approved_by INTEGER, 
	approved_at DATETIME, 
	approval_notes VARCHAR(500), 
	rejection_reason VARCHAR(500), 
	PRIMARY KEY (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id)
);
INSERT INTO pending_deposits VALUES(1,1,6,50000.0,'CASH','Test deposit','REF123456','approved','2026-04-04 11:40:46.324029',4,'2026-04-04 11:40:46.433985',NULL,NULL);
CREATE TABLE loans (
	id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	amount FLOAT NOT NULL, 
	term INTEGER, 
	interest_rate FLOAT, 
	purpose VARCHAR(200), 
	status VARCHAR, 
	timestamp DATETIME, 
	total_interest FLOAT, 
	total_payable FLOAT, 
	total_paid FLOAT, 
	approved_by INTEGER, 
	approved_at DATETIME, 
	approval_notes VARCHAR(500), 
	risk_score INTEGER, 
	risk_level VARCHAR(20), 
	last_risk_assessment DATETIME, 
	repayment_schedule JSON, 
	eligibility_score INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id)
);
INSERT INTO loans VALUES(1,1,6,100000.0,12,12.0,'Business','approved','2026-04-04 11:40:46.489131',12000.0,112000.0,9333.33333333333393,2,'2026-04-04 11:40:46.510425',NULL,0,'low',NULL,NULL,0);
CREATE TABLE logs (
	id INTEGER NOT NULL, 
	user_id INTEGER, 
	sacco_id INTEGER, 
	action VARCHAR NOT NULL, 
	details VARCHAR(500), 
	ip_address VARCHAR(45), 
	timestamp DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id)
);
INSERT INTO logs VALUES(1,2,NULL,'USER_LOGOUT','User logged out',NULL,'2026-04-04 11:41:34.709669');
INSERT INTO logs VALUES(2,1,NULL,'USER_LOGIN','User superadmin logged in','127.0.0.1','2026-04-04 11:42:04.887781');
INSERT INTO logs VALUES(3,1,NULL,'USER_LOGOUT','User logged out',NULL,'2026-04-04 11:42:31.312470');
INSERT INTO logs VALUES(4,2,1,'USER_LOGIN','User test.manager logged in','127.0.0.1','2026-04-04 11:42:52.110879');
INSERT INTO logs VALUES(5,2,NULL,'USER_LOGOUT','User logged out',NULL,'2026-04-04 11:43:27.945065');
INSERT INTO logs VALUES(6,4,1,'USER_LOGIN','User test.accountant logged in','127.0.0.1','2026-04-04 11:43:46.093586');
INSERT INTO logs VALUES(7,4,NULL,'USER_LOGOUT','User logged out',NULL,'2026-04-04 11:44:35.021477');
INSERT INTO logs VALUES(8,5,1,'USER_LOGIN','User test.credit logged in','127.0.0.1','2026-04-04 11:44:55.029512');
INSERT INTO logs VALUES(9,5,NULL,'USER_LOGOUT','User logged out',NULL,'2026-04-04 12:32:19.564662');
INSERT INTO logs VALUES(10,6,1,'USER_LOGIN','User test.member logged in','127.0.0.1','2026-04-04 12:32:47.398091');
INSERT INTO logs VALUES(11,6,NULL,'USER_LOGOUT','User logged out',NULL,'2026-04-04 12:41:08.421756');
INSERT INTO logs VALUES(12,2,1,'USER_LOGIN','User test.manager logged in','127.0.0.1','2026-04-04 12:41:23.773974');
CREATE TABLE external_loans (
	id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	amount FLOAT NOT NULL, 
	term INTEGER NOT NULL, 
	interest_rate FLOAT, 
	purpose VARCHAR(200), 
	status VARCHAR(20), 
	collateral_description VARCHAR(500) NOT NULL, 
	collateral_value FLOAT NOT NULL, 
	guarantor_id INTEGER NOT NULL, 
	borrower_name VARCHAR(200) NOT NULL, 
	borrower_contact VARCHAR(100) NOT NULL, 
	borrower_national_id VARCHAR(50) NOT NULL, 
	timestamp DATETIME, 
	total_interest FLOAT, 
	total_payable FLOAT, 
	total_paid FLOAT, 
	approved_by INTEGER, 
	approved_at DATETIME, 
	approval_notes VARCHAR(500), 
	PRIMARY KEY (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id), 
	FOREIGN KEY(guarantor_id) REFERENCES users (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id)
);
CREATE TABLE referral_commissions (
	id INTEGER NOT NULL, 
	referrer_id INTEGER NOT NULL, 
	referred_entity_type VARCHAR(20) NOT NULL, 
	referred_entity_id INTEGER NOT NULL, 
	referral_type VARCHAR(20) NOT NULL, 
	source VARCHAR(50) NOT NULL, 
	source_id INTEGER, 
	amount FLOAT NOT NULL, 
	percentage FLOAT NOT NULL, 
	status VARCHAR(20), 
	paid_at DATETIME, 
	paid_by INTEGER, 
	notes VARCHAR(500), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(referrer_id) REFERENCES users (id), 
	FOREIGN KEY(paid_by) REFERENCES users (id)
);
CREATE TABLE membership_fees (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	amount FLOAT NOT NULL, 
	payment_method VARCHAR(50) NOT NULL, 
	reference_number VARCHAR(100), 
	status VARCHAR(20), 
	paid_at DATETIME, 
	approved_by INTEGER, 
	approved_at DATETIME, 
	membership_number VARCHAR(50), 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id), 
	UNIQUE (membership_number)
);
CREATE TABLE membership_applications (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	application_date DATETIME, 
	status VARCHAR(10), 
	approved_by INTEGER, 
	approved_at DATETIME, 
	rejection_reason VARCHAR(500), 
	membership_number VARCHAR(50), 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id), 
	UNIQUE (membership_number)
);
CREATE TABLE share_types (
	id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	class_type VARCHAR(7), 
	par_value FLOAT NOT NULL, 
	minimum_shares INTEGER, 
	maximum_shares INTEGER, 
	is_voting BOOLEAN, 
	dividend_rate FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id)
);
INSERT INTO share_types VALUES(1,1,'Class A Shares','CLASS_A',10000.0,1,1000,1,8.0);
INSERT INTO share_types VALUES(2,1,'Class B Shares','CLASS_B',5000.0,5,500,0,6.0);
CREATE TABLE insight_logs (
	id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	insight_type VARCHAR(50) NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	description TEXT, 
	data JSON, 
	severity VARCHAR(20), 
	is_resolved BOOLEAN, 
	resolved_at DATETIME, 
	resolved_by INTEGER, 
	generated_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id), 
	FOREIGN KEY(resolved_by) REFERENCES users (id)
);
INSERT INTO insight_logs VALUES(1,1,'inactive_savers','2 Inactive Savers Detected','Members who haven''t saved in the last 30 days','[{"user_id": 3, "name": "Test Manager (Member)", "days_inactive": 0, "last_saving_date": null}, {"user_id": 6, "name": "Test Member", "days_inactive": 0, "last_saving_date": null}]','warning',0,NULL,NULL,'2026-04-04 11:40:46.205018');
INSERT INTO insight_logs VALUES(2,1,'inactive_savers','2 Inactive Savers Detected','Members who haven''t saved in the last 30 days','[{"user_id": 3, "name": "Test Manager (Member)", "days_inactive": 0, "last_saving_date": null}, {"user_id": 6, "name": "Test Member", "days_inactive": 0, "last_saving_date": null}]','warning',0,NULL,NULL,'2026-04-04 11:40:46.284556');
CREATE TABLE alert_rules (
	id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	rule_name VARCHAR(100) NOT NULL, 
	insight_type VARCHAR(50) NOT NULL, 
	threshold_days INTEGER, 
	threshold_amount FLOAT, 
	is_active BOOLEAN, 
	notify_admin BOOLEAN, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id)
);
CREATE TABLE weekly_summaries (
	id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	week_start DATETIME NOT NULL, 
	week_end DATETIME NOT NULL, 
	summary_data JSON NOT NULL, 
	sent_at DATETIME, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id)
);
INSERT INTO weekly_summaries VALUES(1,1,'2026-03-28 11:40:46.108356','2026-04-04 11:40:46.212347','{"week_start": "2026-03-28T11:40:46.108356", "week_end": "2026-04-04T11:40:46.212347", "metrics": {"new_members": 5, "new_savings_count": 0, "total_new_savings": 0, "new_loans": 0, "total_loans_amount": 0}, "top_insights": [{"type": "inactive_savers", "title": "2 Inactive Savers Detected", "description": "Members who haven''t saved in the last 30 days", "data": [{"user_id": 3, "name": "Test Manager (Member)", "days_inactive": 0, "last_saving_date": null}, {"user_id": 6, "name": "Test Member", "days_inactive": 0, "last_saving_date": null}], "severity": "warning"}]}',NULL,'2026-04-04 11:40:46.212347');
CREATE TABLE savings (
	id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	type VARCHAR NOT NULL, 
	amount FLOAT NOT NULL, 
	payment_method VARCHAR(13) NOT NULL, 
	description VARCHAR(200), 
	reference_number VARCHAR(100), 
	approved_by INTEGER, 
	approved_at DATETIME, 
	pending_deposit_id INTEGER, 
	timestamp DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id), 
	FOREIGN KEY(pending_deposit_id) REFERENCES pending_deposits (id)
);
INSERT INTO savings VALUES(1,1,6,'deposit',50000.0,'CASH','Test deposit','REF123456',4,'2026-04-04 11:40:46.432986',1,'2026-04-04 11:40:46.446053');
CREATE TABLE loan_payments (
	id INTEGER NOT NULL, 
	loan_id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	amount FLOAT NOT NULL, 
	payment_method VARCHAR(50), 
	timestamp DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(loan_id) REFERENCES loans (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
INSERT INTO loan_payments VALUES(1,1,1,6,9333.33333333333393,'SAVINGS','2026-04-04 11:40:46.540596');
CREATE TABLE external_loan_payments (
	id INTEGER NOT NULL, 
	external_loan_id INTEGER NOT NULL, 
	amount FLOAT NOT NULL, 
	payment_method VARCHAR(50), 
	reference_number VARCHAR(100), 
	notes VARCHAR(200), 
	recorded_by INTEGER, 
	timestamp DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(external_loan_id) REFERENCES external_loans (id), 
	FOREIGN KEY(recorded_by) REFERENCES users (id)
);
CREATE TABLE shares (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	share_type_id INTEGER NOT NULL, 
	quantity INTEGER, 
	total_value FLOAT, 
	is_active BOOLEAN, 
	last_updated DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id), 
	FOREIGN KEY(share_type_id) REFERENCES share_types (id)
);
INSERT INTO shares VALUES(1,6,1,1,10,100000.0,1,'2026-04-04 11:40:45.936990');
CREATE TABLE dividend_declarations (
	id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	share_type_id INTEGER, 
	declared_date DATETIME, 
	fiscal_year INTEGER NOT NULL, 
	rate FLOAT NOT NULL, 
	amount_per_share FLOAT NOT NULL, 
	total_dividend_pool FLOAT NOT NULL, 
	payment_date DATETIME, 
	declared_by INTEGER NOT NULL, 
	status VARCHAR(20), 
	PRIMARY KEY (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id), 
	FOREIGN KEY(share_type_id) REFERENCES share_types (id), 
	FOREIGN KEY(declared_by) REFERENCES users (id)
);
INSERT INTO dividend_declarations VALUES(1,1,1,'2026-04-04 11:40:46.026398',2026,8.0,800.0,8000.0,'2026-05-04 11:40:46.026946',1,'pending');
CREATE TABLE share_transactions (
	id INTEGER NOT NULL, 
	share_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	transaction_type VARCHAR(21) NOT NULL, 
	quantity INTEGER NOT NULL, 
	price_per_share FLOAT NOT NULL, 
	total_amount FLOAT NOT NULL, 
	payment_method VARCHAR(50), 
	reference_number VARCHAR(100), 
	transaction_date DATETIME, 
	approved_by INTEGER, 
	approved_at DATETIME, 
	notes VARCHAR(500), 
	PRIMARY KEY (id), 
	FOREIGN KEY(share_id) REFERENCES shares (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id), 
	FOREIGN KEY(approved_by) REFERENCES users (id)
);
INSERT INTO share_transactions VALUES(1,1,6,1,'SUBSCRIPTION',10,10000.0,100000.0,NULL,'SHARE-20260404114045','2026-04-04 11:40:45.947937',NULL,NULL,'Initial share purchase');
CREATE TABLE dividend_payments (
	id INTEGER NOT NULL, 
	declaration_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	sacco_id INTEGER NOT NULL, 
	share_id INTEGER NOT NULL, 
	shares_held INTEGER NOT NULL, 
	amount FLOAT NOT NULL, 
	payment_method VARCHAR(50), 
	paid_at DATETIME, 
	reference_number VARCHAR(100), 
	is_reinvested BOOLEAN, 
	PRIMARY KEY (id), 
	FOREIGN KEY(declaration_id) REFERENCES dividend_declarations (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(sacco_id) REFERENCES saccos (id), 
	FOREIGN KEY(share_id) REFERENCES shares (id)
);
INSERT INTO dividend_payments VALUES(1,1,6,1,1,10,8000.0,'bank','2026-04-04 11:40:46.062427','DIV-20260404114046',0);
CREATE INDEX ix_saccos_id ON saccos (id);
CREATE UNIQUE INDEX ix_saccos_name ON saccos (name);
CREATE UNIQUE INDEX ix_users_referral_code ON users (referral_code);
CREATE UNIQUE INDEX ix_users_username ON users (username);
CREATE INDEX ix_users_id ON users (id);
CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE INDEX ix_pending_deposits_id ON pending_deposits (id);
CREATE INDEX ix_loans_id ON loans (id);
CREATE INDEX ix_logs_id ON logs (id);
CREATE INDEX ix_external_loans_id ON external_loans (id);
CREATE INDEX ix_referral_commissions_id ON referral_commissions (id);
CREATE INDEX ix_membership_fees_id ON membership_fees (id);
CREATE INDEX ix_membership_applications_id ON membership_applications (id);
CREATE INDEX ix_share_types_id ON share_types (id);
CREATE INDEX ix_insight_logs_id ON insight_logs (id);
CREATE INDEX ix_alert_rules_id ON alert_rules (id);
CREATE INDEX ix_weekly_summaries_id ON weekly_summaries (id);
CREATE INDEX ix_savings_id ON savings (id);
CREATE INDEX ix_loan_payments_id ON loan_payments (id);
CREATE INDEX ix_external_loan_payments_id ON external_loan_payments (id);
CREATE INDEX ix_shares_id ON shares (id);
CREATE INDEX ix_dividend_declarations_id ON dividend_declarations (id);
CREATE INDEX ix_share_transactions_id ON share_transactions (id);
CREATE INDEX ix_dividend_payments_id ON dividend_payments (id);
COMMIT;
