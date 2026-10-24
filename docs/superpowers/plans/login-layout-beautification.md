# Login Layout Beautification Implementation Plan

**Goal:** Make the jellyfish fully visible in a separate showcase and keep authentication clear in both themes and on narrow screens.

**Architecture:** Retain the existing session, registration and portal policies. Restructure only the login composition into a shared appearance toolbar, an isolated illustration column and a semantic-color form. User subsequently approved restoring clear liquid glass: translucent card, bounded decorative highlights and stable opaque input surfaces. Extend the existing jellyfish with an optional motion mode; default behavior in other routes stays unchanged.

**Tech Stack:** Vue 3, existing Canvas/SVG effects, semantic CSS variables, Node tests and Playwright.

**Spec:** User-approved design in this conversation: left showcase/right 420–460px form, watermarked OPS, jellyfish foreground/whale background, responsive single-column layout, consistent themes and reduced motion.

## Constraints

- No new dependencies, backend/database changes, credentials changes or real authentication submissions during visual testing.
- No Three.js on the login route. Keep role assignment and administrator registration restrictions unchanged.
- Preserve unrelated dirty workspace changes. No commits or branches.

## Steps

- [ ] Add failing layout/contrast checks for user, admin and registration states; update obsolete composition assertions.
- [ ] Build the split layout and appearance controls; deduplicate guidance and use semantic form styling.
- [ ] Isolate the illustration geometry; connect balanced/lightweight/reduced-motion without covering inputs.
- [ ] Verify desktop/tablet/mobile, short viewport, theme switching, keyboard controls and registration/security regressions.
- [ ] Run full frontend tests/build and production-browser checks; record evidence and remaining limits.
- [ ] Restore the approved liquid-glass material without reverting layout: theme-specific surfaces, bounded highlights, pointer-only light tracking, static low-motion fallback and no form movement.

## Review Focus

- Registration and API errors can increase height: no fixed-height clipping or horizontal scroll.
- Jellyfish animation drift must stay inside its stage, not just its initial SVG box.
- Theme switching must not reveal low-contrast placeholder/footer/button text.
- Reduced-motion must stop SVG transforms without removing the jellyfish.
- Appearance selectors stay outside the auth form and never become role-selection fields.
