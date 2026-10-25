-- New feature tables must be in public so the managed Publish diff includes them.
-- Existing coach identities/passwords remain in ch.coaches.
CREATE TABLE IF NOT EXISTS public.coach_auth_state (
    coach_id INTEGER PRIMARY KEY REFERENCES ch.coaches(id),
    auth_version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS public.coach_password_setups (
    id BIGSERIAL PRIMARY KEY,
    coach_id INTEGER NOT NULL REFERENCES ch.coaches(id),
    requested_by INTEGER NOT NULL REFERENCES ch.coaches(id),
    token_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (delivery_status IN ('pending', 'sent', 'failed')),
    sent_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS coach_password_setups_coach_idx
    ON public.coach_password_setups (coach_id, created_at DESC);