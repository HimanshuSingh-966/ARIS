-- =============================================================================
-- ARIS — Supabase schema (DESTRUCTIVE REBUILD)
-- =============================================================================
--
-- ############################################################################
-- ##  THIS SCRIPT DROPS public.documents, public.doc_metadata AND            ##
-- ##  public.forms, INCLUDING EVERY ROW IN THEM. THERE IS NO UNDO.           ##
-- ##                                                                         ##
-- ##  It exists because changing the chunk size means re-embedding the whole ##
-- ##  corpus from scratch — the old chunks are not migratable, they are      ##
-- ##  simply wrong. If that is NOT what you are doing, do not run this.      ##
-- ############################################################################
--
-- WHY A REBUILD RATHER THAN `create table if not exists`
--   `create table if not exists` is a total no-op against an existing table. It
--   does not add columns, it does not add constraints, and it reports success.
--   Every earlier revision of this file was therefore unable to fix the defects
--   below on a database that already had these tables.
--
-- WHAT THIS FIXES relative to the pre-rebuild live schema
--   1. NOT NULL DEFAULT '' on the text columns the API returns.
--      documents.section / b2_key / doc_id / source_url / section_tag were
--      nullable. api/models.SourceCitation declares them as plain `str`, and a
--      Pydantic v2 default only fires when the KEY IS ABSENT — a present-but-NULL
--      value is passed straight through and fails validation. Because
--      api/routes/chat.py builds ChatResponse INSIDE its try block, that surfaced
--      as HTTP 502 "The assistant is temporarily unavailable", which points at
--      the LLM rather than at a null column.
--   2. A unique index on forms (form_number, source_pdf).
--      pipeline/extract_forms_from_master_pdfs.py upserts with
--      on_conflict="form_number,source_pdf". Without a matching unique
--      constraint Postgres raises "there is no unique or exclusion constraint
--      matching the ON CONFLICT specification" — and that script's except clause
--      only calls log.error before printing "Done", so EVERY form silently
--      failed to save.
--   3. source_pdf NOT NULL DEFAULT ''. A unique index treats NULLs as distinct,
--      so a nullable source_pdf would let the narrow writer
--      (vector_store.save_form_metadata, which omits the column) insert
--      unlimited duplicates of the same form.
--   4. A unique index on doc_metadata.b2_key AND on doc_metadata.doc_id.
--      ingestor.py checks-then-inserts, which is racy, and any join from
--      documents to doc_metadata on b2_key is non-deterministic while duplicates
--      exist (UPDATE ... FROM picks an arbitrary matching row).
--   5. RLS enabled with zero policies. See the note at the bottom — this is free
--      and it closes anon-key access to every row.
--   6. No ivfflat index. See the note above the commented HNSW block.
--
-- HOW TO RUN
--   Paste the whole thing into the Supabase SQL editor and run it. It is wrapped
--   in BEGIN/COMMIT, so it either fully applies or fully rolls back. The
--   verification queries at the bottom run after COMMIT — run them and read the
--   output before re-ingesting.
--
-- AFTER RUNNING
--   The tables are empty. Re-ingest with:
--       python pipeline/ingestor.py --dry-run     (validates, writes nothing)
--       python pipeline/ingestor.py
--       python pipeline/extract_forms_from_master_pdfs.py
--   You do NOT need supabase/backfill_doc_id.sql — that repairs rows written
--   before the chunker fix, and a fresh ingest writes doc_id correctly.
-- =============================================================================


begin;


-- -----------------------------------------------------------------------------
-- Extensions
-- -----------------------------------------------------------------------------
create extension if not exists vector;

-- Required by the trigram indexes further down: search_forms_keyword uses
-- leading-wildcard ILIKE, which no btree index can serve.
create extension if not exists pg_trgm;


-- -----------------------------------------------------------------------------
-- Drop the RPCs — by resolved signature, not by a guessed argument list
-- -----------------------------------------------------------------------------
-- `drop function public.match_documents(vector, float, int, text, text, text)`
-- only works if you name the CURRENT signature exactly. Get one argument type
-- wrong and the drop silently matches nothing, the later CREATE adds a second
-- OVERLOAD, and PostgREST then fails every call with
-- PGRST203 "could not choose the best candidate function" — an error that looks
-- nothing like its cause.
--
-- Enumerating pg_proc and dropping by oid::regprocedure cannot miss, and handles
-- the case where several overloads already exist.
do $do$
declare
    fn record;
begin
    for fn in
        select p.oid::regprocedure as sig
        from   pg_proc p
        join   pg_namespace n on n.oid = p.pronamespace
        where  n.nspname = 'public'
          and  p.proname in (
                   'match_documents',
                   'search_forms_semantic',
                   'search_forms_keyword',
                   'distinct_sections'
               )
    loop
        execute format('drop function if exists %s cascade', fn.sig);
        raise notice 'dropped function %', fn.sig;
    end loop;
end
$do$;


-- -----------------------------------------------------------------------------
-- Drop the tables
-- -----------------------------------------------------------------------------
-- CASCADE also removes the indexes, constraints and any view that depended on
-- them. Owned sequences go with the table; the explicit drops below only matter
-- if a previous run left an orphaned sequence behind, which would otherwise make
-- the bigserial default collide.
drop table if exists public.documents    cascade;
drop table if exists public.doc_metadata cascade;
drop table if exists public.forms        cascade;

drop sequence if exists public.documents_id_seq    cascade;
drop sequence if exists public.doc_metadata_id_seq cascade;
drop sequence if exists public.forms_id_seq        cascade;


-- =============================================================================
-- documents — chunked page text + embeddings (the RAG corpus)
-- =============================================================================
-- Written by pipeline/vector_store.save_chunks (one row per chunk).
-- Read by the match_documents RPC below.
--
-- NOTE the section/section_tag asymmetry, which is load-bearing:
--   section     — the in-document heading detected by pipeline/chunker.py
--   section_tag — the category slug from pipeline/ingestor.classify_section
-- rag/prompt.build_sources reports `section` to the user; the API filters browse
-- views on `section_tag`. Conflating them was audit finding #18.
--
-- Every text column the API can return is NOT NULL DEFAULT '' — see fix (1) in
-- the header. save_chunks already supplies '' for each of them, so this
-- constraint costs the writer nothing and removes a whole class of 502.
create table public.documents (
    id          bigserial   primary key,
    source      text        not null,                      -- 'cdsco' | 'fda' | 'ema'
    country     text        not null,                      -- 'India' | 'USA' | 'Europe'
    doc_name    text        not null,
    section     text        not null default '',           -- in-document heading
    section_tag text        not null default '',           -- category slug
    doc_id      text        not null default '',           -- md5(b2_key)
    content     text        not null,
    embedding   vector(384),
    b2_key      text        not null default '',
    source_url  text        not null default '',
    char_start  integer     not null default 0,
    char_end    integer     not null default 0,
    created_at  timestamptz not null default now()
);

-- vector_store.chunk_exists / doc_already_ingested filter on these.
create index documents_b2_key_idx            on public.documents (b2_key);
create index documents_b2_key_char_start_idx on public.documents (b2_key, char_start);

-- match_documents applies these filters before ranking.
create index documents_doc_id_idx  on public.documents (doc_id);
create index documents_source_idx  on public.documents (source);
create index documents_country_idx on public.documents (country);

-- -----------------------------------------------------------------------------
-- NO APPROXIMATE-NEAREST-NEIGHBOUR INDEX. This is deliberate.
-- -----------------------------------------------------------------------------
-- Earlier revisions of this file created an ivfflat index here. That was wrong
-- for this application, and the failure mode is nasty.
--
-- ivfflat visits `probes` clusters (default: 1) and only THEN applies the WHERE
-- clause. match_documents is usually called with filter_doc_id set — the
-- per-document chat panel — which is highly selective. If the one cluster probed
-- happens to hold few or no chunks of that document, the query returns fewer
-- rows than requested, or none at all. The user sees "I could not find relevant
-- information": indistinguishable from the doc_id bug this project just fixed,
-- and it would come and go depending on the question.
--
-- Without any ANN index, pgvector does an exact scan. That is slower in theory
-- and correct in practice; a corpus in the tens of thousands of chunks answers
-- comfortably inside a request. Measure before optimising.
--
-- If you do outgrow the exact scan, use HNSW rather than ivfflat: it degrades
-- far better under selective filters, and it does not need to be rebuilt as the
-- table grows. Build it AFTER ingesting — an ANN index built on an empty table
-- has no data to cluster.
--
--   create index documents_embedding_hnsw_idx
--       on public.documents
--       using hnsw (embedding vector_cosine_ops)
--       with (m = 16, ef_construction = 64);
--
-- Then raise recall per-session if needed: set hnsw.ef_search = 100;


-- =============================================================================
-- doc_metadata — one row per source PDF (browse/explore views)
-- =============================================================================
-- Written by pipeline/vector_store.save_doc_metadata.
-- Read by api/routes/explore.py, and it holds the AUTHORITATIVE doc_id.
--
-- `section` here is the category slug — the same value as documents.section_tag,
-- NOT documents.section. save_doc_metadata stores the slug under this name.
create table public.doc_metadata (
    id         bigserial   primary key,
    doc_id     text        not null,
    source     text        not null,
    country    text        not null default '',
    section    text        not null default '',        -- category slug
    doc_name   text        not null,
    b2_key     text        not null,
    file_size  integer     not null default 0,         -- KB (PdfList renders it as such)
    page_count integer     not null default 0,
    created_at timestamptz not null default now()
);

-- Both of these are unique, for different reasons.
--
-- b2_key: ingestor.py checks for an existing row and then inserts, which is
-- racy, and anything joining documents to this table on b2_key needs exactly one
-- match to be deterministic.
--
-- doc_id: it is the value the frontend routes with (/documents/{doc_id}/stream)
-- and the value match_documents filters on. Two rows sharing a doc_id would make
-- "open this document" ambiguous.
create unique index doc_metadata_b2_key_key on public.doc_metadata (b2_key);
create unique index doc_metadata_doc_id_key on public.doc_metadata (doc_id);

create index doc_metadata_source_section_idx on public.doc_metadata (source, section);


-- =============================================================================
-- forms — individual regulatory forms sliced out of the master rule PDFs
-- =============================================================================
-- Written by pipeline/extract_forms_from_master_pdfs.py (the full column set).
--
-- pipeline/vector_store.save_form_metadata also writes here, but only a narrow
-- subset — and critically NO embedding, so rows it creates can never be returned
-- by search_forms_semantic (which requires `embedding is not null`). Prefer the
-- master-PDF extractor; it is the path that produces a complete, searchable row.
create table public.forms (
    id              bigserial   primary key,
    form_number     text        not null default '',   -- 'FORM CT-04'
    form_number_raw text        not null default '',   -- 'CT-04'
    form_name       text        not null default '',
    title           text        not null default '',
    rule_reference  text        not null default '',
    form_type       text        not null default '',   -- classify_form(): Manufacturing / Import / ...
    description     text        not null default '',
    country         text        not null default '',
    source          text        not null default '',
    source_doc      text        not null default '',
    source_pdf      text        not null default '',   -- master PDF filename; see fix (3)
    source_pdf_year text        not null default '',   -- written as a string, e.g. '2024'
    b2_key          text        not null default '',
    page_start      integer,
    page_end        integer,
    content_text    text        not null default '',
    embedding       vector(384),
    created_at      timestamptz not null default now()
);

-- REQUIRED by extract_forms_from_master_pdfs.py's
-- on_conflict="form_number,source_pdf". Its absence is why the forms table was
-- empty — see fix (2) in the header.
create unique index forms_form_number_source_pdf_key
    on public.forms (form_number, source_pdf);

create index forms_b2_key_idx on public.forms (b2_key);
create index forms_type_idx   on public.forms (form_type);
create index forms_source_idx on public.forms (source);

-- Trigram indexes for search_forms_keyword's leading-wildcard ILIKE patterns.
-- Without these that search is a full table scan.
create index forms_title_trgm_idx       on public.forms using gin (title       gin_trgm_ops);
create index forms_form_number_trgm_idx on public.forms using gin (form_number gin_trgm_ops);

-- The forms table is small (hundreds of rows), so an exact scan over its
-- embeddings is cheap and an ivfflat index here would only reintroduce the
-- recall problem described above for no measurable gain.


-- =============================================================================
-- RPC: match_documents — the core retrieval call
-- =============================================================================
-- Called by rag/retriever.retrieve with exactly these parameter names.
--
-- The three filters are null-permissive: `filter_x is null or col = filter_x`.
-- That is what makes global chat (no filters) and per-document chat (doc_id set)
-- the same query. Passing a non-null doc_id that matches nothing returns zero
-- rows — which is why audit finding #2 (the frontend sending the literal string
-- "Global Mode" as doc_id) made global chat answer "I could not find relevant
-- information" every single time.
--
-- Similarity is 1 - cosine_distance, so it rises with relevance and
-- `1 - (embedding <=> query) > match_threshold` is the natural filter.
create function public.match_documents(
    query_embedding vector(384),
    match_threshold double precision default 0.3,
    match_count     integer          default 5,
    filter_source   text             default null,
    filter_country  text             default null,
    filter_doc_id   text             default null
)
returns table (
    id          bigint,
    source      text,
    country     text,
    doc_name    text,
    section     text,
    section_tag text,
    doc_id      text,
    content     text,
    b2_key      text,
    source_url  text,
    char_start  integer,
    char_end    integer,
    similarity  double precision
)
language sql
stable
as $$
    select
        d.id,
        d.source,
        d.country,
        d.doc_name,
        d.section,
        d.section_tag,
        d.doc_id,
        d.content,
        d.b2_key,
        d.source_url,
        d.char_start,
        d.char_end,
        1 - (d.embedding <=> query_embedding) as similarity
    from public.documents d
    where d.embedding is not null
      and (filter_source  is null or filter_source  = '' or d.source  = filter_source)
      and (filter_country is null or filter_country = '' or d.country = filter_country)
      and (filter_doc_id  is null or filter_doc_id  = '' or d.doc_id  = filter_doc_id)
      and 1 - (d.embedding <=> query_embedding) > match_threshold
    order by d.embedding <=> query_embedding
    limit match_count;
$$;


-- =============================================================================
-- RPC: search_forms_semantic
-- =============================================================================
-- Called by api/routes/forms.py and rag/retriever.search_forms_semantic.
-- Returns both `title` and `form_name` so the route's
-- `.get("title") or .get("form_name")` fallbacks have both available.
create function public.search_forms_semantic(
    query_embedding vector(384),
    match_threshold double precision default 0.25,
    match_count     integer          default 60
)
returns table (
    id              bigint,
    form_number     text,
    form_name       text,
    title           text,
    rule_reference  text,
    form_type       text,
    description     text,
    country         text,
    source          text,
    b2_key          text,
    source_pdf_year text,
    similarity      double precision
)
language sql
stable
as $$
    select
        f.id,
        f.form_number,
        f.form_name,
        f.title,
        f.rule_reference,
        f.form_type,
        f.description,
        f.country,
        f.source,
        f.b2_key,
        f.source_pdf_year,
        1 - (f.embedding <=> query_embedding) as similarity
    from public.forms f
    where f.embedding is not null
      and 1 - (f.embedding <=> query_embedding) > match_threshold
    order by f.embedding <=> query_embedding
    limit match_count;
$$;


-- =============================================================================
-- RPC: search_forms_keyword
-- =============================================================================
-- Called with a single `query_text` parameter. Exact-ish matches rank first in
-- api/routes/forms.py's merge, so this deliberately returns only high-confidence
-- hits: the form number, the title, the form name and the rule reference.
--
-- The literal is escaped before interpolation so a query containing % or _ is
-- treated as text rather than as wildcards.
create function public.search_forms_keyword(
    query_text text
)
returns table (
    id              bigint,
    form_number     text,
    form_name       text,
    title           text,
    rule_reference  text,
    form_type       text,
    description     text,
    country         text,
    source          text,
    b2_key          text,
    source_pdf_year text
)
language sql
stable
as $$
    select
        f.id,
        f.form_number,
        f.form_name,
        f.title,
        f.rule_reference,
        f.form_type,
        f.description,
        f.country,
        f.source,
        f.b2_key,
        f.source_pdf_year
    from public.forms f
    where coalesce(query_text, '') <> ''
      and (
            f.form_number    ilike '%' || replace(replace(query_text, '%', '\%'), '_', '\_') || '%'
         or f.title          ilike '%' || replace(replace(query_text, '%', '\%'), '_', '\_') || '%'
         or f.form_name      ilike '%' || replace(replace(query_text, '%', '\%'), '_', '\_') || '%'
         or f.rule_reference ilike '%' || replace(replace(query_text, '%', '\%'), '_', '\_') || '%'
      )
    order by f.form_number
    limit 60;
$$;


-- =============================================================================
-- RPC: distinct_sections
-- =============================================================================
-- Called by api/routes/explore.get_sections. The route previously selected every
-- doc_metadata row and deduplicated in Python, which silently dropped categories
-- once a source exceeded Supabase's 1000-row response cap (audit finding #16).
-- The route still falls back to that behaviour if this function is absent, and
-- logs a warning saying so.
create function public.distinct_sections(
    filter_source text
)
returns table (section text)
language sql
stable
as $$
    select distinct m.section
    from public.doc_metadata m
    where m.source = filter_source
      and m.section is not null
      and m.section <> ''
    order by 1;
$$;


-- =============================================================================
-- Row Level Security — ENABLED, with NO policies
-- =============================================================================
-- Supabase exposes the `public` schema through PostgREST, and the built-in `anon`
-- role holds table grants. With RLS off, anyone holding the project's anon key —
-- which is designed to be public — has read AND write access to every row in
-- these three tables. That is the single largest exposure in this project.
--
-- Enabling RLS with zero policies denies anon everything, and costs this
-- application nothing: the backend connects with SUPABASE_SERVICE_KEY, which
-- BYPASSES RLS entirely, and the browser holds no Supabase credentials at all
-- (it calls same-origin /api/*, which a Vercel Edge function forwards to the
-- backend with an API key the client never sees).
--
-- So: no policies. Do NOT add `create policy "anon read" ... to anon using
-- (true)` — an earlier revision of this file suggested exactly that, which would
-- reopen the read side of what this closes for no benefit to any current caller.
-- Add a policy only when a real anon-key client exists, and scope it to that
-- client's needs.
--
-- Note the RPCs above are `security invoker` by default, so they respect the
-- caller's policies rather than bypassing them. The service key bypasses RLS, so
-- the backend's calls are unaffected.
alter table public.documents    enable row level security;
alter table public.doc_metadata enable row level security;
alter table public.forms        enable row level security;


commit;


-- =============================================================================
-- VERIFICATION — run these after COMMIT and read the output
-- =============================================================================

-- 1. Tables exist and are empty.
select
    (select count(*) from public.documents)    as documents,
    (select count(*) from public.doc_metadata) as doc_metadata,
    (select count(*) from public.forms)        as forms;

-- 2. The vector columns are 384-dimensional.
--
--    Do NOT check this via information_schema — it renders vector(384) as
--    'USER-DEFINED' and hides the dimension entirely. format_type() on
--    pg_attribute is the only way to see it.
--
--    EXPECTED: both rows show vector(384). A vector(768) column is a leftover
--    from the old Gemini embeddings; the current FastEmbed model emits 384 and
--    every insert would fail.
select
    c.relname   as table_name,
    a.attname   as column_name,
    format_type(a.atttypid, a.atttypmod) as declared_type
from   pg_attribute a
join   pg_class     c on c.oid = a.attrelid
join   pg_namespace n on n.oid = c.relnamespace
where  n.nspname = 'public'
  and  c.relname in ('documents', 'forms')
  and  a.attname = 'embedding'
  and  a.attnum > 0
  and  not a.attisdropped;

-- 3. Exactly four RPCs, each with exactly ONE overload.
--
--    EXPECTED: 4 rows, every overloads = 1. A count above 1 means a stale
--    signature survived and PostgREST will fail with PGRST203.
select
    p.proname                        as function_name,
    count(*)                         as overloads,
    string_agg(p.oid::regprocedure::text, ' | ') as signatures
from   pg_proc p
join   pg_namespace n on n.oid = p.pronamespace
where  n.nspname = 'public'
  and  p.proname in ('match_documents', 'search_forms_semantic',
                     'search_forms_keyword', 'distinct_sections')
group by p.proname
order by p.proname;

-- 4. RLS is on for all three tables, with zero policies.
--    EXPECTED: three rows, rls_enabled = true, policies = 0.
select
    c.relname                                   as table_name,
    c.relrowsecurity                            as rls_enabled,
    (select count(*) from pg_policies pol
      where pol.schemaname = 'public'
        and pol.tablename  = c.relname)         as policies
from   pg_class     c
join   pg_namespace n on n.oid = c.relnamespace
where  n.nspname = 'public'
  and  c.relname in ('documents', 'doc_metadata', 'forms')
order by c.relname;

-- 5. The constraint that was missing, and why forms stayed empty.
--    EXPECTED: forms_form_number_source_pdf_key present and is_unique = true.
select
    i.relname   as index_name,
    idx.indisunique as is_unique,
    pg_get_indexdef(idx.indexrelid) as definition
from   pg_index idx
join   pg_class i on i.oid = idx.indexrelid
join   pg_class t on t.oid = idx.indrelid
join   pg_namespace n on n.oid = t.relnamespace
where  n.nspname = 'public'
  and  t.relname = 'forms'
order by i.relname;
-- =============================================================================
