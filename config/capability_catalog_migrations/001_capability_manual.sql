CREATE SCHEMA IF NOT EXISTS nexterp_manual;

CREATE TABLE IF NOT EXISTS nexterp_manual.capability_node (
    node_id VARCHAR(180) PRIMARY KEY,
    node_type VARCHAR(30) NOT NULL CHECK (node_type IN ('module', 'capability', 'operation', 'slot')),
    module VARCHAR(60) NOT NULL,
    label VARCHAR(200) NOT NULL,
    summary TEXT NOT NULL,
    guide TEXT NOT NULL,
    usage_conditions TEXT NOT NULL DEFAULT '',
    prohibitions TEXT NOT NULL DEFAULT '',
    examples_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    implementation_key VARCHAR(180),
    is_write BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nexterp_manual.capability_edge (
    source_node_id VARCHAR(180) NOT NULL REFERENCES nexterp_manual.capability_node(node_id) ON DELETE CASCADE,
    target_node_id VARCHAR(180) NOT NULL REFERENCES nexterp_manual.capability_node(node_id) ON DELETE CASCADE,
    relation_type VARCHAR(30) NOT NULL CHECK (relation_type IN ('contains', 'uses_slot', 'requires', 'next', 'alternative')),
    position INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (source_node_id, target_node_id, relation_type)
);

CREATE TABLE IF NOT EXISTS nexterp_manual.capability_alias (
    alias_id BIGSERIAL PRIMARY KEY,
    node_id VARCHAR(180) NOT NULL REFERENCES nexterp_manual.capability_node(node_id) ON DELETE CASCADE,
    alias_text VARCHAR(240) NOT NULL,
    alias_type VARCHAR(30) NOT NULL DEFAULT 'search',
    normalized_text VARCHAR(240) NOT NULL,
    UNIQUE (node_id, normalized_text)
);

CREATE TABLE IF NOT EXISTS nexterp_manual.operation_tool (
    operation_id VARCHAR(180) PRIMARY KEY REFERENCES nexterp_manual.capability_node(node_id) ON DELETE CASCADE,
    tool_name VARCHAR(240) NOT NULL,
    compiler_key VARCHAR(180) NOT NULL,
    resolver_key VARCHAR(180) NOT NULL,
    preflight_key VARCHAR(180) NOT NULL,
    verifier_key VARCHAR(180) NOT NULL,
    risk_level VARCHAR(10) NOT NULL DEFAULT 'L3',
    requires_confirmation BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS nexterp_manual.operation_slot (
    operation_id VARCHAR(180) NOT NULL REFERENCES nexterp_manual.capability_node(node_id) ON DELETE CASCADE,
    slot_id VARCHAR(180) NOT NULL REFERENCES nexterp_manual.capability_node(node_id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position > 0),
    scope VARCHAR(20) NOT NULL CHECK (scope IN ('document', 'item')),
    target_path VARCHAR(240) NOT NULL,
    source_type VARCHAR(40) NOT NULL,
    control_type VARCHAR(40) NOT NULL,
    is_user_editable BOOLEAN NOT NULL DEFAULT FALSE,
    lookup_doctype VARCHAR(140),
    format_hint VARCHAR(200),
    default_strategy TEXT,
    source_path VARCHAR(240),
    is_required BOOLEAN NOT NULL DEFAULT TRUE,
    resolver_key VARCHAR(120),
    fixed_value_json JSONB,
    derived_from_slot_id VARCHAR(180) REFERENCES nexterp_manual.capability_node(node_id),
    constraint_text TEXT,
    PRIMARY KEY (operation_id, slot_id),
    UNIQUE (operation_id, position)
);

CREATE TABLE IF NOT EXISTS nexterp_manual.operation_rule (
    rule_id VARCHAR(180) PRIMARY KEY,
    operation_id VARCHAR(180) NOT NULL REFERENCES nexterp_manual.capability_node(node_id) ON DELETE CASCADE,
    label VARCHAR(180) NOT NULL,
    implementation_key VARCHAR(180) NOT NULL,
    expression_text TEXT NOT NULL,
    user_message TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS nexterp_manual.external_identity (
    identity_id BIGSERIAL PRIMARY KEY,
    provider VARCHAR(60) NOT NULL DEFAULT 'openclaw',
    external_subject VARCHAR(240) NOT NULL,
    agent_id VARCHAR(180) NOT NULL DEFAULT '',
    employee_user VARCHAR(240) NOT NULL,
    profile_name VARCHAR(120) NOT NULL,
    default_project VARCHAR(180),
    allowed_projects_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (provider, external_subject, agent_id)
);

CREATE TABLE IF NOT EXISTS nexterp_manual.catalog_revision (
    revision_id VARCHAR(80) PRIMARY KEY,
    content_checksum VARCHAR(80) NOT NULL UNIQUE,
    schema_version INTEGER NOT NULL,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_catalog_revision_current
    ON nexterp_manual.catalog_revision (is_current) WHERE is_current;

CREATE TABLE IF NOT EXISTS nexterp_manual.prepared_operation (
    pending_id UUID PRIMARY KEY,
    operation_id VARCHAR(180) NOT NULL REFERENCES nexterp_manual.capability_node(node_id),
    employee_user VARCHAR(240) NOT NULL,
    project_code VARCHAR(180) NOT NULL,
    external_subject VARCHAR(240) NOT NULL,
    agent_id VARCHAR(180) NOT NULL DEFAULT '',
    session_key VARCHAR(240) NOT NULL,
    request_id VARCHAR(180) NOT NULL,
    catalog_revision_id VARCHAR(80) NOT NULL REFERENCES nexterp_manual.catalog_revision(revision_id),
    tool_call_json JSONB NOT NULL,
    tool_call_hash VARCHAR(80) NOT NULL,
    summary_json JSONB NOT NULL,
    status VARCHAR(30) NOT NULL CHECK (status IN ('pending', 'executing', 'completed', 'failed', 'rejected', 'expired')),
    result_json JSONB,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executed_at TIMESTAMPTZ,
    UNIQUE (employee_user, request_id)
);

CREATE INDEX IF NOT EXISTS idx_capability_alias_normalized ON nexterp_manual.capability_alias(normalized_text);
CREATE INDEX IF NOT EXISTS idx_capability_node_module ON nexterp_manual.capability_node(module, node_type, is_active);
CREATE INDEX IF NOT EXISTS idx_capability_edge_source ON nexterp_manual.capability_edge(source_node_id, relation_type, position);
CREATE INDEX IF NOT EXISTS idx_prepared_operation_status ON nexterp_manual.prepared_operation(status, expires_at);
