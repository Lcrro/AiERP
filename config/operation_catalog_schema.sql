-- Agent Runtime v0.4 relational operation catalog.
-- PostgreSQL is the target store; Python executor keys remain in source code.

CREATE TABLE IF NOT EXISTS information_slot (
    slot_id VARCHAR(120) PRIMARY KEY,
    serial INTEGER NOT NULL UNIQUE CHECK (serial > 0),
    label VARCHAR(140) NOT NULL,
    data_type VARCHAR(40) NOT NULL,
    entity_type VARCHAR(140),
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operation_template (
    operation_id VARCHAR(160) PRIMARY KEY,
    capability_id VARCHAR(160) NOT NULL,
    label VARCHAR(200) NOT NULL,
    module VARCHAR(60) NOT NULL,
    tool_name VARCHAR(220) NOT NULL,
    is_write BOOLEAN NOT NULL DEFAULT TRUE,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS operation_slot (
    operation_id VARCHAR(160) NOT NULL REFERENCES operation_template(operation_id),
    slot_id VARCHAR(120) NOT NULL REFERENCES information_slot(slot_id),
    position INTEGER NOT NULL CHECK (position > 0),
    scope VARCHAR(20) NOT NULL CHECK (scope IN ('document', 'item')),
    target_path VARCHAR(240) NOT NULL,
    source_type VARCHAR(40) NOT NULL,
    source_path VARCHAR(240),
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    resolver_key VARCHAR(120),
    fixed_value_json JSONB,
    derived_from_slot_id VARCHAR(120) REFERENCES information_slot(slot_id),
    constraint_text TEXT,
    PRIMARY KEY (operation_id, slot_id),
    UNIQUE (operation_id, position)
);

CREATE TABLE IF NOT EXISTS operation_rule (
    rule_id VARCHAR(160) PRIMARY KEY,
    operation_id VARCHAR(160) NOT NULL REFERENCES operation_template(operation_id),
    label VARCHAR(160) NOT NULL,
    expression_key VARCHAR(200) NOT NULL,
    user_message TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_operation_slot_slot ON operation_slot(slot_id);
CREATE INDEX IF NOT EXISTS idx_operation_template_capability ON operation_template(capability_id);
