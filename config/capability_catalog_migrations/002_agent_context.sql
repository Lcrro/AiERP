ALTER TABLE nexterp_manual.capability_node
    ADD COLUMN IF NOT EXISTS operation_mode VARCHAR(20) NOT NULL DEFAULT 'write'
        CHECK (operation_mode IN ('read', 'analyze', 'write')),
    ADD COLUMN IF NOT EXISTS business_object VARCHAR(80) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS intent_kind VARCHAR(80) NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS nexterp_manual.agent_role_profile (
    role_code VARCHAR(80) PRIMARY KEY,
    role_name VARCHAR(120) NOT NULL,
    mission TEXT NOT NULL,
    boundaries TEXT NOT NULL DEFAULT '',
    escalation_guidance TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nexterp_manual.agent_role_responsibility (
    responsibility_id VARCHAR(140) PRIMARY KEY,
    role_code VARCHAR(80) NOT NULL REFERENCES nexterp_manual.agent_role_profile(role_code) ON DELETE CASCADE,
    label VARCHAR(180) NOT NULL,
    summary TEXT NOT NULL,
    responsibility_type VARCHAR(30) NOT NULL
        CHECK (responsibility_type IN ('own', 'collaborate', 'escalate', 'avoid')),
    priority INTEGER NOT NULL DEFAULT 100,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS nexterp_manual.agent_context_guide (
    guide_id VARCHAR(140) PRIMARY KEY,
    topic VARCHAR(40) NOT NULL CHECK (topic IN (
        'responsibilities', 'collaboration', 'project', 'recent_documents', 'inbox', 'process_position'
    )),
    label VARCHAR(180) NOT NULL,
    summary TEXT NOT NULL,
    guide TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nexterp_manual.agent_role_context (
    role_code VARCHAR(80) NOT NULL REFERENCES nexterp_manual.agent_role_profile(role_code) ON DELETE CASCADE,
    guide_id VARCHAR(140) NOT NULL REFERENCES nexterp_manual.agent_context_guide(guide_id) ON DELETE CASCADE,
    relevance INTEGER NOT NULL DEFAULT 100,
    PRIMARY KEY (role_code, guide_id)
);

CREATE TABLE IF NOT EXISTS nexterp_manual.agent_role_capability (
    role_code VARCHAR(80) NOT NULL REFERENCES nexterp_manual.agent_role_profile(role_code) ON DELETE CASCADE,
    node_id VARCHAR(180) NOT NULL REFERENCES nexterp_manual.capability_node(node_id) ON DELETE CASCADE,
    relevance INTEGER NOT NULL DEFAULT 100,
    PRIMARY KEY (role_code, node_id)
);

CREATE TABLE IF NOT EXISTS nexterp_manual.agent_session_context (
    external_subject VARCHAR(240) NOT NULL,
    agent_id VARCHAR(180) NOT NULL DEFAULT '',
    session_key VARCHAR(240) NOT NULL,
    employee_user VARCHAR(240) NOT NULL,
    project_code VARCHAR(180) NOT NULL,
    current_goal TEXT NOT NULL DEFAULT '',
    intent_mode VARCHAR(20) NOT NULL DEFAULT 'read' CHECK (intent_mode IN ('read', 'analyze', 'write')),
    confirmed_entities_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    unresolved_fields_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    active_capability VARCHAR(180),
    loaded_context_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    recent_documents_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    pending_operation VARCHAR(80),
    last_successful_progress VARCHAR(180),
    search_miss_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (external_subject, agent_id, session_key)
);

CREATE INDEX IF NOT EXISTS idx_role_responsibility_role
    ON nexterp_manual.agent_role_responsibility(role_code, priority);
CREATE INDEX IF NOT EXISTS idx_context_guide_topic
    ON nexterp_manual.agent_context_guide(topic, is_active);
CREATE INDEX IF NOT EXISTS idx_agent_session_employee
    ON nexterp_manual.agent_session_context(employee_user, project_code, updated_at DESC);
