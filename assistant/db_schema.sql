-- Messages table
create table if not exists messages (
  id serial primary key,
  user_id text,
  conversation_id text,
  type text,
  message_id text,
  message_type text,
  message_text text,
  raw_event jsonb,
  created_at timestamp with time zone default current_timestamp
);

-- Attachments table
create table if not exists attachments (
  id serial primary key,
  message_id text,
  type text,
  url text,
  content_type text,
  size integer,
  created_at timestamp with time zone default current_timestamp
);

-- Extractions table
create table if not exists extractions (
  id serial primary key,
  message_id text,
  schema text,
  data jsonb,
  confidence numeric,
  created_at timestamp with time zone default current_timestamp
);
