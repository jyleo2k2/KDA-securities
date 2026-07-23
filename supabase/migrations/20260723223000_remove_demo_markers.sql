update public.demo_user_financial_context
set nickname = replace(nickname, '(가상)', '')
where nickname like '%(가상)%';

update public.user_profiles
set nickname = replace(nickname, '(가상)', '')
where nickname like '%(가상)%';

update public.chat_messages
set content = replace(
    replace(
        replace(
            replace(content, '(가상)', ''),
            '가상 목데이터', '계좌 정보'
        ),
        '목데이터', '계좌 정보'
    ),
    '가상 고객', '고객 유형'
)
where role = 'assistant'
  and (
      content like '%(가상)%'
      or content like '%목데이터%'
      or content like '%가상 고객%'
  );
