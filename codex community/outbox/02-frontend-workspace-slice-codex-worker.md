# Task 02: Frontend Workspace Slice

## Findings

Best single slice to implement now: extract the workspace body rendering from `MarkdownViewer.tsx` into a new `WorkspacePanels.tsx`.

Why this slice:

- `MarkdownViewer.tsx` has already shed the heavy Markdown rendering into `MarkdownDocument`, and loading/failure states into `WorkspaceStatusView` / `TaskFailureView`.
- It still owns three different responsibilities: version/content selection state, global workspace command handling, and actual panel layout/rendering for map, cards, markdown, transcript, and chat.
- The panel JSX is a clean extraction boundary: it starts at the `viewMode === 'map' ? ...` branch and only needs explicit props.
- This is lower risk than dynamic imports because it does not change loading behavior, suspense boundaries, or chunk timing.

Current evidence:

- `MarkdownViewer.tsx` still statically imports `TranscriptViewer`, `MarkmapEditor`, `ChatPanel`, `KnowledgeCardsView`, and `MarkdownDocument`.
- `MarkdownViewer.tsx` still stores `showTranscribe`, `showChat`, and `viewMode`, and renders all panel branches inline.
- Markmap already has a manual Vite chunk, but it is still statically imported by the workspace path. Dynamic import can be a follow-up after panel extraction.

## Recommended Patch

Create `fastread-frontend/src/pages/HomePage/components/WorkspacePanels.tsx`.

Recommended props:

```ts
type WorkspaceViewMode = 'map' | 'preview' | 'cards'
type WorkspaceChatMode = false | 'half' | 'full'

interface WorkspacePanelsProps {
  viewMode: WorkspaceViewMode
  selectedContent: string
  currentTask?: TaskLike
  showTranscribe: boolean
  showChat: WorkspaceChatMode
  setShowChat: (mode: WorkspaceChatMode) => void
}
```

The local `TaskLike` can be narrow instead of importing the full store type:

```ts
interface TaskLike {
  id: string
  audioMeta?: { title?: string }
  formData?: { video_url?: string }
  insights?: NoteInsights
}
```

Move these rendering branches into `WorkspacePanels`:

- `viewMode === 'map'`: `MarkmapEditor`
- `viewMode === 'cards'`: `KnowledgeCardsView`
- preview branch:
  - empty/loading content handling
  - full-screen `ChatPanel`
  - `MarkdownDocument`
  - optional `TranscriptViewer`
  - half-screen `ChatPanel`

Keep these in `MarkdownViewer` for now:

- version selection and `selectedContent` derivation
- copy/download handlers
- `fastread:workspace-command` event listener
- `MarkdownHeader`
- loading/idle/failed top-level status branches

Exact files likely to change:

- `fastread-frontend/src/pages/HomePage/components/MarkdownViewer.tsx`
- `fastread-frontend/src/pages/HomePage/components/WorkspacePanels.tsx`

Follow-up, not in this slice:

- After `WorkspacePanels` exists, consider `React.lazy`/dynamic import for `MarkmapComponent`, `ChatPanel`, and maybe `KnowledgeCardsView`.
- Extract `VersionSelector` only after the panel extraction; `MarkdownHeader` currently mixes version display, badges, and controls, but it is not the most pressing size issue.

## Risks

- `showChat` typing must allow `false | 'half' | 'full'`; `ChatPanel` itself only accepts `'half' | 'full'`, so branches must keep the existing guards.
- The empty content guard must preserve current sentinel behavior for `'loading'` and `'empty'`.
- `MarkdownDocument` relies on `audioMeta` and `videoUrl`; keep optional chaining unchanged.
- Do not move the workspace command listener in the same patch. It is cross-component event plumbing and should be handled separately.

## Verification

Suggested verification:

```powershell
cd fastread-frontend
pnpm run build
```

Optional after build:

```powershell
pnpm run lint
```

Commands run for this report:

- `rg --files fastread-frontend/src/pages/HomePage/components fastread-frontend/src/hooks fastread-frontend/src/services fastread-frontend/src/store`
- `rg -n "import\\(|MarkmapEditor|ChatPanel|KnowledgeCardsView|TranscriptViewer|viewMode|showChat|showTranscribe|WorkspaceCommand|MarkdownHeader|currentVerId|selectedContent" fastread-frontend/src/pages/HomePage/components/MarkdownViewer.tsx`
- `rg -n "markmap|lottie|manualChunks|chunkSizeWarningLimit|dynamic import|React\\.lazy|lazy\\(" fastread-frontend/src fastread-frontend/vite.config.ts fastread-frontend/package.json`
- Read-only inspection of the files listed below.

Tests were not run; this was a read-only worker investigation.

## Files Inspected

- `readme/refactor-plan-2026-06-04.md`
- `fastread-frontend/src/pages/HomePage/components/MarkdownViewer.tsx`
- `fastread-frontend/src/pages/HomePage/components/MarkdownHeader.tsx`
- `fastread-frontend/src/pages/HomePage/components/MarkdownDocument.tsx`
- `fastread-frontend/src/pages/HomePage/components/MarkmapComponent.tsx`
- `fastread-frontend/src/pages/HomePage/components/ChatPanel.tsx`
- `fastread-frontend/src/pages/HomePage/components/KnowledgeCardsView.tsx`
- `fastread-frontend/vite.config.ts`
- `fastread-frontend/package.json`
