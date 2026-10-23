BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE rfqs (
    id SERIAL NOT NULL, 
    reference_id VARCHAR(40) NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    description TEXT, 
    origin VARCHAR(120), 
    destination VARCHAR(120), 
    currency VARCHAR(3) NOT NULL, 
    pickup_date DATE NOT NULL, 
    bid_start_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    bid_close_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    current_close_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    forced_close_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    is_british_auction BOOLEAN NOT NULL, 
    trigger_window_minutes INTEGER, 
    extension_minutes INTEGER, 
    trigger_type VARCHAR(32), 
    status VARCHAR(32) NOT NULL, 
    extension_count INTEGER NOT NULL, 
    closed_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_rfq_british_config_complete CHECK (NOT is_british_auction OR (forced_close_at > bid_close_at AND trigger_window_minutes > 0 AND extension_minutes > 0 AND trigger_type IS NOT NULL)), 
    CONSTRAINT ck_rfq_close_after_start CHECK (bid_close_at > bid_start_at), 
    CONSTRAINT ck_rfq_current_close_within_bounds CHECK (current_close_at >= bid_close_at AND current_close_at <= forced_close_at), 
    CONSTRAINT ck_rfq_forced_not_before_close CHECK (forced_close_at >= bid_close_at), 
    UNIQUE (reference_id), 
    CONSTRAINT trigger_type CHECK (trigger_type IN ('BID_RECEIVED', 'ANY_RANK_CHANGE', 'L1_CHANGE')), 
    CONSTRAINT auction_status CHECK (status IN ('SCHEDULED', 'ACTIVE', 'CLOSED', 'FORCE_CLOSED'))
);

CREATE INDEX ix_rfqs_status_close ON rfqs (status, current_close_at);

CREATE TABLE suppliers (
    id SERIAL NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    contact_email VARCHAR(254), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (name)
);

CREATE TABLE bids (
    id SERIAL NOT NULL, 
    rfq_id INTEGER NOT NULL, 
    supplier_id INTEGER NOT NULL, 
    revision INTEGER NOT NULL, 
    carrier_name VARCHAR(120) NOT NULL, 
    freight_charges NUMERIC(14, 2) NOT NULL, 
    origin_charges NUMERIC(14, 2) NOT NULL, 
    destination_charges NUMERIC(14, 2) NOT NULL, 
    total_amount NUMERIC(14, 2) NOT NULL, 
    transit_time_days INTEGER NOT NULL, 
    quote_validity_date DATE NOT NULL, 
    remarks TEXT, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_bid_charges_non_negative CHECK (freight_charges >= 0 AND origin_charges >= 0 AND destination_charges >= 0), 
    CONSTRAINT ck_bid_total_positive CHECK (total_amount > 0), 
    CONSTRAINT ck_bid_transit_positive CHECK (transit_time_days > 0), 
    FOREIGN KEY(rfq_id) REFERENCES rfqs (id) ON DELETE CASCADE, 
    FOREIGN KEY(supplier_id) REFERENCES suppliers (id)
);

CREATE INDEX ix_bids_rfq_supplier_created ON bids (rfq_id, supplier_id, created_at);

CREATE INDEX ix_bids_rfq_total ON bids (rfq_id, total_amount);

CREATE TABLE auction_events (
    id SERIAL NOT NULL, 
    rfq_id INTEGER NOT NULL, 
    event_type VARCHAR(32) NOT NULL, 
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    supplier_id INTEGER, 
    bid_id INTEGER, 
    message TEXT NOT NULL, 
    reason TEXT, 
    previous_close_at TIMESTAMP WITH TIME ZONE, 
    new_close_at TIMESTAMP WITH TIME ZONE, 
    details JSONB, 
    PRIMARY KEY (id), 
    FOREIGN KEY(bid_id) REFERENCES bids (id), 
    FOREIGN KEY(rfq_id) REFERENCES rfqs (id) ON DELETE CASCADE, 
    FOREIGN KEY(supplier_id) REFERENCES suppliers (id), 
    CONSTRAINT event_type CHECK (event_type IN ('RFQ_CREATED', 'AUCTION_STARTED', 'BID_SUBMITTED', 'AUCTION_EXTENDED', 'EXTENSION_CAPPED', 'AUCTION_CLOSED', 'AUCTION_FORCE_CLOSED'))
);

CREATE INDEX ix_events_rfq_id ON auction_events (rfq_id, id);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

