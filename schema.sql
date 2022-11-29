CREATE TABLE IF NOT EXISTS program (
	id TEXT PRIMARY KEY,
	name TEXT NOT NULL,
	source TEXT NOT NULL,
	build_schedule TEXT,
	created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_program_name ON program (name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_program_source ON program(source);
CREATE INDEX IF NOT EXISTS idx_program_build_schedule ON program (build_schedule);

CREATE TABLE IF NOT EXISTS build (
	id TEXT PRIMARY KEY,
	program_id TEXT NOT NULL,
	commit_sha TEXT,
	status TEXT,
	artifact BLOB,
	created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	finished TIMESTAMP,
	FOREIGN KEY (program_id) REFERENCES program(id)
);

CREATE INDEX IF NOT EXISTS idx_build_program_id_commit_sha ON build (program_id, commit_sha);
