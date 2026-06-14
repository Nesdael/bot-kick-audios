-- Ejecuta esto en Supabase > SQL Editor

-- Tabla de sonidos
CREATE TABLE IF NOT EXISTS sounds (
  id         SERIAL PRIMARY KEY,
  command    TEXT UNIQUE NOT NULL,
  filename   TEXT NOT NULL,
  audio_url  TEXT NOT NULL,
  active     BOOLEAN DEFAULT true,
  cooldown   INTEGER DEFAULT 10,
  subs_only  BOOLEAN DEFAULT false,
  vips_only  BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Bucket de audios (público para que OBS pueda reproducirlos)
INSERT INTO storage.buckets (id, name, public)
VALUES ('audios', 'audios', true)
ON CONFLICT (id) DO UPDATE SET public = true;

-- Política: cualquiera puede leer los audios
CREATE POLICY "Public read audios"
  ON storage.objects FOR SELECT
  USING (bucket_id = 'audios');

-- Política: solo service key puede subir/eliminar
CREATE POLICY "Service upload audios"
  ON storage.objects FOR INSERT
  WITH CHECK (bucket_id = 'audios');

CREATE POLICY "Service delete audios"
  ON storage.objects FOR DELETE
  USING (bucket_id = 'audios');
