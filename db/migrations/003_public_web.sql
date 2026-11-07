-- Citizen web page: submissions are attributed to a system key whose secret nobody knows
-- (random hash), and rate limited per salted client fingerprint.
INSERT INTO api_keys (name, key_hash, scopes)
VALUES ('system:public-web',
        sha256(convert_to(gen_random_uuid()::text || clock_timestamp()::text, 'UTF8')),
        ARRAY['intake']);

ALTER TABLE requests ADD COLUMN client_fingerprint text;
CREATE INDEX requests_fingerprint_idx ON requests (client_fingerprint, created_at)
    WHERE client_fingerprint IS NOT NULL;
