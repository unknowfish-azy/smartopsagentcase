CREATE TABLE IF NOT EXISTS registration_policy (
    id INT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO registration_policy(id,enabled) SELECT 1,TRUE WHERE NOT EXISTS (SELECT 1 FROM registration_policy WHERE id=1);
