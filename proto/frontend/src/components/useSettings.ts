import { useCallback, useEffect, useState } from "react";
import { ApiError, getSettings, saveSettings, type AppSettings, type SettingsReply } from "../api";

// Shared by the settings page and the dev panel: load, edit a draft, save or discard.
export function useSettings() {
  const [reply, setReply] = useState<SettingsReply | null>(null);
  const [draft, setDraft] = useState<AppSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  const load = useCallback(() => {
    getSettings()
      .then((r) => { setReply(r); setDraft(r.settings); })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Couldn't load the settings."));
  }, []);
  useEffect(load, [load]);

  const dirty = !!reply && !!draft && JSON.stringify(reply.settings) !== JSON.stringify(draft);

  async function save() {
    if (!draft || !reply) return;
    setSaving(true);
    setError(null);
    try {
      const r = await saveSettings(draft);
      setReply({ ...reply, settings: r.settings });
      setDraft(r.settings);
      setSavedAt(Date.now());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't save the settings.");
    } finally {
      setSaving(false);
    }
  }

  function patch<K extends keyof AppSettings>(part: K, values: Partial<AppSettings[K]>) {
    setDraft((d) => (d ? { ...d, [part]: { ...d[part], ...values } } : d));
    setSavedAt(null);
  }

  return { reply, draft, dirty, saving, error, savedAt, save, discard: () => reply && setDraft(reply.settings), patch, reload: load };
}
