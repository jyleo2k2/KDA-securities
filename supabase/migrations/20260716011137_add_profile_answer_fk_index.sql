-- Cover the composite FK used to verify that a selected option belongs to the
-- recorded question. Separate single-column indexes do not cover this exact FK.
create index investment_profile_answers_option_question_idx
    on public.investment_profile_answers (option_id, question_id);
