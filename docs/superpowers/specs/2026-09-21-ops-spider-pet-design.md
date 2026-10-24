# Ops Spider Pet Design

## Goal

Add a persistent, lightweight Ops Spider desktop pet to the Personal Operations System. It is an interactive Kubernetes-sentinel companion, not a floating dashboard or a decorative spider icon.

## Visual Model

The pet is a 68px translucent dark orb containing a cyan Kubernetes topology core, eight asymmetric curved routes, endpoint nodes, and a sparse micro-stellar field. The routes represent Node, Pod, Service, Ingress, Deployment, Network, Storage, and Observability. It uses the existing stellar palette and motion language: quiet breathing, local drift, node pulse, and sparse routing particles. It never rotates as a whole, bounces, uses cartoon eyes, or imitates a real spider.

The orb uses the existing `KubernetesSpider` SVG rather than a second WebGL canvas. Pet-specific route articulation is scoped behind a `pet` prop, so existing inline Spider usages stay unchanged.

## State And Real Data Boundary

`OpsSpiderState` is one of `idle`, `observing`, `thinking`, `executing`, `warning`, `error`, `recovering`, or `sleeping`.

The first release derives it only from existing real application state:

- Agent route: `thinking`
- Inspector and Connections routes: `observing`
- Other routes: `idle`
- Thirty minutes without pointer, keyboard, touch, focus, or visibility-resume activity: `sleeping`

No Kubernetes API, cluster, node, Pod, or alert API exists in the current application. The expanded status therefore says `集群 未接入` and never invents quantities, health values, or alerts. A future telemetry adapter may supply explicit real cluster values; the rendering component will consume only an already-resolved snapshot.

## Interaction

The pet is fixed above application content. Its outer position has one owner: Pointer Events with pointer capture update the latest pointer reference, and one `requestAnimationFrame` writes `translate3d(x, y, 0)` to the outer shell. Pinia is updated only on release, not per pointer frame. It can be dragged after a 6px movement threshold and retains the exact released position, constrained only to the visible safe page bounds. Four corner choices are also available from its context menu for keyboard and non-drag use. Position is persisted as a non-sensitive `localStorage` preference.

During drag, container transitions are disabled and the outer orb has no floating offset. Its inner topology, core pulse, and sparse particle motion remain independent. Pointer up, pointer cancel, lost pointer capture, and window blur all end a drag and release capture. After release, only positions within 48px of a safe edge use a 190ms transform settle; free positions stop immediately.

Hover or keyboard focus opens a restrained information panel with the real Agent state and the cluster-not-connected state. Clicking the core toggles a four-action radial menu. Its actions only navigate to existing routes:

- Agent: `/agent`
- Cluster: `/servers`
- Terminal: `/connections`
- Knowledge: `/knowledge`

Right click opens an application context menu with the same navigation actions, corner placement choices, sleep/wake, and hide. Escape closes open menus. The controls use button semantics, visible labels, focus states, and an action alternative to dragging.

## Avoidance And Responsive Rules

The fixed layer is below modal and toast layers, but above normal page content. It is inset from edges and safe areas. On the Connections route it automatically uses a 52px compact form and lower opacity so the terminal stays primary. Desktop defaults to 68px, tablet to 60px, and mobile to 52px. Expanded panels move inward from the nearest edge, preventing viewport overflow.

## Motion And Performance

At normal motion, the orb uses transform-only drift and a low-frequency 5-8 second breath. Each route has a different transform origin, phase, duration, and amplitude. A 2-4 second core pulse and occasional routing particles convey topology activity. State changes alter only route posture, local accent, and particle speed. Warning and error apply an amber/local disconnected branch only; the entire orb does not flash red.

The component uses one animation frame loop only while visible and not reduced-motion. Idle rendering is throttled to 30fps; active hover or action state can render at 60fps. `prefers-reduced-motion` removes drift, particle flow, and articulated route animation while retaining an intelligible static state. Document-hidden frames are cancelled.

## Components

- `components/common/opsSpiderState.js`: pure state, storage, corner and safe-position helpers.
- `stores/opsSpider.js`: position, hidden/menu state, inactivity clock, and navigation-independent interaction state.
- `components/common/OpsSpiderPet.vue`: fixed pet UI, pointer and keyboard interaction, status panel, radial menu, and menu rendering.
- `components/common/KubernetesSpider.vue`: optional pet-mode route articulation and state accents.
- `layouts/MainLayout.vue`: derives the current application state, renders the pet, and retains the existing whale, jellyfish, and stellar layers.

## Testing

Unit tests cover route-to-pet state mapping, exact 30-minute sleeping behavior, corner snap positions, clamping against viewport bounds, and compact Connections sizing. Existing visual quality tests continue to cover reduced motion and organism cadence. The build is run after lint, typecheck, and the full frontend test suite.

## Non-Goals

- No fabricated Kubernetes telemetry, alerts, node counts, or Pod counts
- No Kubernetes operation, command execution, remote connection, or alert acknowledgement
- No background API polling or extra WebGL renderer
- No full desktop-window placement outside the browser application
- No secret or credential storage
