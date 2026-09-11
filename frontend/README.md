# UniAssist — frontend

React + Vite + TypeScript, no other runtime dependencies. The dev server
proxies `/api` and `/health` to the backend on `http://localhost:8000`.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # type-check + production bundle in dist/
```

Sign in with any synthetic account (password `uniassist`); the sign-in page
lists one per role. The **Trace** toggle in the top bar shows, under every
answer, which path the turn took, which tools ran (and which were refused),
and the token cost — for the viva, off by default.

Source map:

| file | what it is |
|---|---|
| `src/api.ts` | fetch wrapper: bearer token, `ApiError{status, retryAfter}` |
| `src/session.ts` | the signed-in session in `localStorage` |
| `src/App.tsx` | sign-in gate; loads `/api/me` |
| `src/Login.tsx` | sign-in form + demo accounts |
| `src/Chat.tsx` | turns, send / confirm / cancel, one-shot retry on 429, the Trace toggle |
| `src/Rail.tsx` | suggested prompts per role, conversation history |
| `src/Message.tsx` | prose with `[n]` → footnotes, confirm card |
| `src/Cards.tsx` | attendance / marks / timetable / student table / denied cards |
| `src/Trace.tsx` | the dev trace panel |
| `src/index.css` | the one stylesheet (tokens at the top) |
