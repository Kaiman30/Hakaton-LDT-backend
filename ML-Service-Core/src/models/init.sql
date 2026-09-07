-- ============================================================================
-- Database initialization script for MailAnalysisWorker
-- ============================================================================

-- Create operation_logs table for task tracking
CREATE TABLE IF NOT EXISTS operation_logs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(255) NOT NULL,
    trace_id VARCHAR(255) NOT NULL,
    operation VARCHAR(100) NOT NULL,
    metadata JSONB DEFAULT '{}',
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_operation_logs_task_id ON operation_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_operation_logs_trace_id ON operation_logs(trace_id);
CREATE INDEX IF NOT EXISTS idx_operation_logs_timestamp ON operation_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_operation_logs_operation ON operation_logs(operation);

-- Create task_results table for storing final results
CREATE TABLE IF NOT EXISTS task_results (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(255) NOT NULL UNIQUE,
    trace_id VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL,
    result JSONB,
    error TEXT,
    tokens_used INTEGER DEFAULT 0,
    processing_time_ms FLOAT DEFAULT 0,
    worker_id VARCHAR(100),
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_task_results_task_id ON task_results(task_id);
CREATE INDEX IF NOT EXISTS idx_task_results_trace_id ON task_results(trace_id);
CREATE INDEX IF NOT EXISTS idx_task_results_status ON task_results(status);
CREATE INDEX IF NOT EXISTS idx_task_results_completed_at ON task_results(completed_at);

-- Create metrics table for monitoring (optional, for future metrics export)
CREATE TABLE IF NOT EXISTS worker_metrics (
    id SERIAL PRIMARY KEY,
    worker_id VARCHAR(100),
    metric_name VARCHAR(100),
    metric_value FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_worker_metrics_worker_id ON worker_metrics(worker_id);
CREATE INDEX IF NOT EXISTS idx_worker_metrics_timestamp ON worker_metrics(timestamp);

-- Grant permissions (adjust user as needed)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;