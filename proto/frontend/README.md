# Prototype frontend

React + TypeScript (Vite) UI for the LLM-security assistant: a chat, a CVE dashboard, a settings page and a dev panel. Built from [SPEC.md](../SPEC.md) (U1–U10) and the backend API.

```bash
npm install
npm run dev        # http://localhost:5173, talks to VITE_API_URL (default http://localhost:8000)
npm run build      # type-check + production build
npm run lint
```

The backend's allowed origins come from `CORS_ORIGINS` (default ports 5173 and 5174).

## Files

- `src/api.ts`: typed client for `/chat`, `/dashboard`, `/cves`, `/watchlist`. Types written by hand from `backend/app/schemas.py`.
- `src/App.tsx`: the page switch (Dashboard, Settings, Dev), "Ask about this", Ctrl/Cmd+K.
- `src/components/Chat.tsx`: messages with inline details, suggestions and examples, input, spinner, the injection flag notice.
- `SourcesPanel`, `ToolCallCard` (CVE, weakness and watchlist cards), `QueryPanel`, `UsageLine`, `SeverityBadge`.
- `src/components/Dashboard.tsx`: tiles, charts, the CVE table with actions, watchlist editor, incidents, data freshness.
- `src/components/Settings.tsx`: alert settings (saved for the refresh worker), delivery with a mocked test alert, data and reset.
- `src/components/DevPanel.tsx`: model, agent and search settings (live), index facts, the search playground.
- `src/components/ModelCheck.tsx`: runs the 11 questions against the chosen model, shows each check, and keeps past runs for comparison.
- `src/components/EmbeddingMap.tsx`: every chunk on a 2D PCA map, with the playground's query, rewrites and final sources drawn on top. PCA, not t-SNE or UMAP, because it is linear: a query is placed by the same formula as the chunks. The axes keep only ~9% of the variation, and the map says so.
- `useSettings.ts` and `SaveBar.tsx`: load, edit, save or discard the shared settings.
- `src/App.tsx`: the shell and the chat layout: the bubble, which pins beside the page when enlarged.
- `src/designs.css` and `src/components/Icons.tsx`: the Playful design (the sidebar shell, candy tiles, motion) and the light/dark toggle. Tokens hang off `<html data-design="playful">` (set in `index.html`, with the fonts), and `data-theme="dark"` adds the dark ones. `Robot.tsx` is Patch, the chat button and the face of the chat, with moods for idle, thinking, happy and alert; `hooks/useMood.ts` reads the mood from the chat.
- `src/hooks/useChat.ts`: the one conversation, kept when the chat is pinned or unpinned.
- `ChatSurface.tsx` and `ChatDetails.tsx`: the chat as it appears over a page, with an answer's sources, tool calls and query plan as inline tabs.
- `src/components/charts.tsx`: plain-SVG charts drawn at the container's width, with hover and focus tooltips and a table view each.

## Colour

- Severity is an ordered scale, so it uses one hue in four steps, not four unrelated colours. Light mode runs light to dark; dark mode runs dark to light, so worse is always more contrast. Both ramps pass the dataviz skill's validator (`--ordinal`).
- Severity is always shown as text too, never by colour alone.

## UI check

`e2e/check_ui.py` clicks through the chat, dashboard, settings and dev panel in Firefox, in light and dark, and checks that nothing is wider than a 420px phone screen. It marks CVEs fixed and changes settings, so run it against a second pair of servers with a throwaway state file, never your own:

```bash
cd ../backend && STATE_PATH=/tmp/ui-state.json uv run uvicorn app.main:app --port 8001
cd ../frontend && VITE_API_URL=http://localhost:8001 npx vite --port 5174
UI_URL=http://localhost:5174 uv run --with playwright python e2e/check_ui.py
```

Last run 2026-10-13: 35 of 35 checks passed (including the bubble, pin and unpin, a phone-width chat, and the design in light and dark at desktop and phone width). `ONLY=designs` runs just the design checks. `ONLY=layouts` runs just the layout checks. Screenshots in `screenshots/`.
