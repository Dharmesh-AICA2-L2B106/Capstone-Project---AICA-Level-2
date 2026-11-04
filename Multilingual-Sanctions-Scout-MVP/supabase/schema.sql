-- Starter schema only. Review RLS and authorization before deploying.
create extension if not exists pgcrypto;

create type public.app_role as enum ('Admin', 'Analyst', 'Reviewer');
create type public.case_status as enum ('Pending Review', 'False Positive', 'Confirmed Identity Match', 'Escalated');

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null,
  role public.app_role not null default 'Analyst',
  created_at timestamptz not null default now()
);

create table public.datasets (
  id uuid primary key default gen_random_uuid(),
  publisher text not null,
  official_source_url text not null,
  import_status text not null check (import_status in ('staged','active','failed','retired')),
  record_count integer not null default 0,
  publication_date date,
  last_attempt_at timestamptz not null default now(),
  last_success_at timestamptz,
  checksum_sha256 text,
  version text,
  private_object_path text,
  activated_by uuid references public.profiles(id),
  created_at timestamptz not null default now()
);

create unique index one_active_sdn_dataset on public.datasets ((import_status)) where import_status = 'active';

create table public.list_records (
  dataset_id uuid not null references public.datasets(id) on delete cascade,
  source_record_id text not null,
  entity_type text,
  listed_name text not null,
  aliases jsonb not null default '[]'::jsonb,
  original_script_name text,
  dates_of_birth jsonb not null default '[]'::jsonb,
  nationalities jsonb not null default '[]'::jsonb,
  identifiers jsonb not null default '[]'::jsonb,
  listing_reason text,
  source_url text,
  raw_record jsonb not null default '{}'::jsonb,
  primary key (dataset_id, source_record_id)
);

create table public.screenings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id),
  submitted_identity jsonb not null,
  source_name text not null,
  threshold integer not null check (threshold between 50 and 100),
  matching_engine_version text not null,
  dataset_id uuid references public.datasets(id),
  candidates jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create table public.review_cases (
  id uuid primary key default gen_random_uuid(),
  screening_id uuid not null references public.screenings(id),
  source_record_id text not null,
  assigned_to uuid references public.profiles(id),
  status public.case_status not null default 'Pending Review',
  decision_rationale text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (screening_id, source_record_id)
);

create table public.review_events (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null references public.review_cases(id),
  actor_id uuid not null references public.profiles(id),
  event_type text not null,
  event_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create function public.prevent_review_event_mutation() returns trigger language plpgsql as $$
begin raise exception 'review_events are append-only'; end; $$;
create trigger review_events_append_only before update or delete on public.review_events for each row execute function public.prevent_review_event_mutation();

create table public.access_audit (
  id uuid primary key default gen_random_uuid(),
  actor_id uuid references public.profiles(id),
  action text not null,
  object_type text not null,
  object_id text,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;
alter table public.datasets enable row level security;
alter table public.list_records enable row level security;
alter table public.screenings enable row level security;
alter table public.review_cases enable row level security;
alter table public.review_events enable row level security;
alter table public.access_audit enable row level security;

-- Policies are intentionally not permissive by default. Deployment must add role-aware
-- policies and server-side authorization before enabling application access.
