-- Make the intentional browser denial explicit for RLS auditing.  The API uses
-- a server-side role; authenticated browser sessions have neither a grant nor
-- a permissive policy for this replay ledger.
create policy chat_request_idempotency_deny_client_access
    on public.chat_request_idempotency
    for all to authenticated
    using (false)
    with check (false);
