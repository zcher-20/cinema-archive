-- ============================================================
-- Cinema Archive – Supabase schema setup
-- Paste this into the Supabase SQL Editor and click Run.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.films (
  id           uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  list         text NOT NULL CHECK (list IN ('archive','watchlist')),
  title        text NOT NULL,
  caption_html text,
  image_url    text,
  gradient     text DEFAULT 'linear-gradient(140deg,#111 0%,#1a1a1a 100%)',
  summary      text DEFAULT '',
  date_watched text DEFAULT '',
  rating_seb   smallint DEFAULT 0 CHECK (rating_seb BETWEEN 0 AND 5),
  rating_zay   smallint DEFAULT 0 CHECK (rating_zay BETWEEN 0 AND 5),
  sort_order   int DEFAULT 0,
  created_at   timestamptz DEFAULT now(),
  updated_at   timestamptz DEFAULT now()
);

ALTER TABLE public.films ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "public_all" ON public.films;
CREATE POLICY "public_all" ON public.films FOR ALL TO anon USING (true) WITH CHECK (true);

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('film-images', 'film-images', true, 52428800, ARRAY['image/jpeg','image/png','image/webp','image/gif'])
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS "img_read"   ON storage.objects;
DROP POLICY IF EXISTS "img_insert" ON storage.objects;
DROP POLICY IF EXISTS "img_update" ON storage.objects;
DROP POLICY IF EXISTS "img_delete" ON storage.objects;

CREATE POLICY "img_read"   ON storage.objects FOR SELECT TO anon USING (bucket_id = 'film-images');
CREATE POLICY "img_insert" ON storage.objects FOR INSERT TO anon WITH CHECK (bucket_id = 'film-images');
CREATE POLICY "img_update" ON storage.objects FOR UPDATE TO anon USING (bucket_id = 'film-images');
CREATE POLICY "img_delete" ON storage.objects FOR DELETE TO anon USING (bucket_id = 'film-images');
