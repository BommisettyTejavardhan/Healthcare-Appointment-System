## Design Rationale

### Color System
- `Primary`: `#5b4df7` with darker action state `#4533d4` drives the main call-to-action and key focus moments.
- `Secondary`: `#0f766e` supports informative and utility interactions without competing with the primary path.
- `Accent`: `#b4235a` is reserved for vibrant emphasis and visual richness in gradients and highlights.
- `Text`: `#10233d` and `#27415f` preserve strong readability against light surfaces.
- `Status colors`: darker success, warning, danger, and info tones were selected so labels and interactive states stay comfortably within WCAG 2.1 AA contrast targets on their paired backgrounds.

### Visual Choices
- The interface uses layered glass-like surfaces, rounded corners, and soft elevation to create a more modern healthcare aesthetic while keeping content blocks clearly separated.
- Typography shifts toward stronger hierarchy with large headline scales, compact eyebrow labels, and generous spacing to improve scanning across dashboards and forms.
- Motion remains subtle: buttons lift slightly, cards elevate on hover, forms show strong focus rings, and submission states display a lightweight spinner for feedback.
- Responsive layouts rely on grid-based sections that collapse cleanly from desktop to tablet and mobile without losing action priority.
- Accessibility improvements include a skip link, stronger visible focus treatment, clearer labels, reduced-motion support, and higher-contrast surfaces for colorful elements.

### Browser Readiness
- The CSS relies on broadly supported features such as gradients, grid, flexbox, backdrop blur with a graceful fallback surface, and standard transitions.
- Manual multi-browser rendering still needs to be verified in a real browser matrix such as Chrome, Edge, Firefox, and Safari.
